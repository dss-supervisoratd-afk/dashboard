"""Gravação no banco. Política: um arquivo substitui, no seu conjunto, os dias que ele
contém (reimportar o mesmo relatório é idempotente). Cada linha guarda o lote de origem."""
import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from ..models import FATOS, CadGuiche, Dia, FAtendimento, FTempo, ImportBatch
from .parse import norm
from .sga import Ocupacao, origem_de, resolvedor

_LOTE_SQL = 500


def dia_semana(d: date) -> int:
    return (d.weekday() + 1) % 7  # 0 = domingo


def tipo_final(d: date, origem: str | None) -> str:
    if dia_semana(d) in (0, 6):
        return "Fim de semana"
    return origem if origem and norm(origem) != "normal" else "Normal"


def garante_dias(db: Session, datas: set[date]) -> None:
    """Mantém dim_dia contínua entre o primeiro e o último dia conhecidos (séries diárias sem buracos)."""
    if not datas:
        return
    lo0, hi0 = db.execute(select(func.min(Dia.data), func.max(Dia.data))).one()
    lo, hi = min(datas | ({lo0} if lo0 else set())), max(datas | ({hi0} if hi0 else set()))
    existentes = set(db.scalars(select(Dia.data).where(Dia.data.between(lo, hi))).all())
    novos, d = [], lo
    while d <= hi:
        if d not in existentes:
            novos.append({"data": d, "ano_mes": d.strftime("%Y-%m"), "dia_semana": dia_semana(d),
                          "tipo": tipo_final(d, None), "tipo_origem": None})
        d += timedelta(days=1)
    for i in range(0, len(novos), _LOTE_SQL):
        db.execute(insert(Dia), novos[i:i + _LOTE_SQL])


def _agrega(regs: list[dict], chave: tuple[str, ...], soma: str) -> list[dict]:
    acc: dict[tuple, int] = defaultdict(int)
    for r in regs:
        acc[tuple(r[k] for k in chave)] += r.get(soma) or 1
    return [dict(zip(chave, k)) | {soma: v} for k, v in acc.items()]


def prepara(conjunto: str, regs: list[dict]) -> list[dict]:
    if conjunto == "ouvidoria":
        for r in regs:
            r["subsetor"] = r.get("subsetor") or "(não informado)"
        return _agrega(regs, ("data", "setor", "subsetor"), "qtd")
    if conjunto == "servicos":
        return _agrega(regs, ("data", "servico"), "qtd")
    if conjunto == "tempos":
        return [{k: r.get(k) for k in ("data", "atendente", "atendente_origem", "n", "tme", "tmd", "tma", "tot")} for r in regs]
    if conjunto == "atendimentos":
        return [{"data": r["data"], "hora": r.get("hora"), "servico": r["servico"], "atendente": r["atendente"],
                 "atendente_origem": r.get("atendente_origem"),
                 "dur": None if r.get("dur") is None else int(round(r["dur"])),
                 "perm": None if r.get("perm") is None else int(round(r["perm"]))} for r in regs]
    raise ValueError(conjunto)


def carrega(db: Session, conjunto: str, regs: list[dict], lote: ImportBatch) -> int:
    datas = {r["data"] for r in regs}
    garante_dias(db, datas)
    if conjunto == "calendario":
        for r in regs:
            dia = db.get(Dia, r["data"])
            dia.tipo_origem = r["tipo"]
            dia.tipo = tipo_final(r["data"], r["tipo"])
        return len(regs)
    if conjunto in ("tempos", "atendimentos"):
        resolve = resolvedor_db(db)
        for r in regs:
            if not r.get("atendente_origem"):
                r["atendente_origem"] = origem_de(r["atendente"]) or r["atendente"]
            if r["atendente_origem"]:
                # rótulo desconhecido do cadastro: mantém o nome que veio (o legado já vem resolvido)
                nome = resolve(r["atendente_origem"], r["data"])
                if nome != r["atendente_origem"]:
                    r["atendente"] = nome
    fato, linhas = FATOS[conjunto], prepara(conjunto, regs)
    ds = sorted(datas)
    for i in range(0, len(ds), _LOTE_SQL):
        db.execute(delete(fato).where(fato.data.in_(ds[i:i + _LOTE_SQL])))
    for r in linhas:
        r["lote_id"] = lote.id
    for i in range(0, len(linhas), _LOTE_SQL):
        db.execute(insert(fato), linhas[i:i + _LOTE_SQL])
    if conjunto in ("tempos", "atendimentos"):
        harmoniza_logins(db)
    return len(linhas)


def aplica_tipo_dia(db: Session, dia: date, tipo: str | None) -> None:
    """Tipo de dia vindo do nome do arquivo ("AAAA.MM.DD - Feriado - …")."""
    if not tipo:
        return
    garante_dias(db, {dia})
    d = db.get(Dia, dia)
    d.tipo_origem, d.tipo = tipo, tipo_final(dia, tipo)


def resolvedor_db(db: Session):
    cad = [Ocupacao(c.tipo, c.numero, c.atendente, c.grupo, c.vig_inicio, c.vig_fim) for c in db.scalars(select(CadGuiche))]
    return resolvedor(cad)


_LOGIN = re.compile(r"^[a-z]+(?:\.[a-z]+)+$")


def harmoniza_logins(db: Session) -> int:
    """Atendimentos concluídos trazem o login ('joao.couto'); o relatório de TMA, o nome de exibição
    ('João Couto'). Troca o login pelo nome do TMA (comparação sem acento) ou, sem par, por 'Joao Couto'."""
    conhecidos = {norm(n): n for n in db.scalars(select(FTempo.atendente).distinct()) if n and not _LOGIN.match(n)}
    alteradas = 0
    for fato in (FAtendimento, FTempo):
        logins = [o for o in db.scalars(select(fato.atendente_origem).distinct()) if o and _LOGIN.match(o)]
        for login in logins:
            nome = conhecidos.get(norm(login.replace(".", " "))) or " ".join(p.capitalize() for p in login.split("."))
            alteradas += db.execute(update(fato).where(fato.atendente_origem == login, fato.atendente != nome)
                                    .values(atendente=nome)).rowcount or 0
    return alteradas


def reaplica_nomes(db: Session) -> int:
    """Re-resolve os nomes de todos os atendimentos e tempos pelo cadastro atual (após importá-lo)."""
    resolve, alteradas = resolvedor_db(db), 0
    for fato in (FTempo, FAtendimento):
        pares = db.execute(select(fato.atendente_origem, fato.data).where(fato.atendente_origem.is_not(None)).distinct()).all()
        grupos: dict[tuple[str, str], list[date]] = defaultdict(list)
        for origem, dia in pares:
            grupos[(origem, resolve(origem, dia))].append(dia)
        for (origem, nome), dias in grupos.items():
            if nome == origem:
                continue
            for i in range(0, len(dias), _LOTE_SQL):
                alteradas += db.execute(update(fato).where(fato.atendente_origem == origem, fato.data.in_(dias[i:i + _LOTE_SQL]),
                                                           fato.atendente != nome).values(atendente=nome)).rowcount or 0
    return alteradas


def carrega_cadastro(db: Session, ocupacoes: list[Ocupacao], lote: ImportBatch) -> tuple[int, int]:
    """Substitui o cadastro de guichês inteiro e renomeia o histórico."""
    db.execute(delete(CadGuiche))
    db.add_all(CadGuiche(tipo=o.tipo, numero=o.numero, atendente=o.atendente, grupo=o.grupo,
                         vig_inicio=o.vig_inicio, vig_fim=o.vig_fim, lote_id=lote.id) for o in ocupacoes)
    db.flush()
    return len(ocupacoes), reaplica_nomes(db)


def carrega_legado(db: Session, raw: dict, arquivo: str, sha256: str, usuario_id: int | None) -> ImportBatch:
    regs = registros_legado(raw)
    lote = ImportBatch(conjunto="legado", arquivo=arquivo, sha256=sha256, usuario_id=usuario_id,
                       linhas_lidas=sum(map(len, regs.values())), mapeamento={"origem": "painel HTML (const RAW)"}, avisos=[])
    db.add(lote)
    db.flush()
    lote.linhas_carregadas = sum(carrega(db, c, regs[c], lote)
                                 for c in ("calendario", "ouvidoria", "servicos", "tempos", "atendimentos"))
    ds = [r["data"] for r in regs["calendario"]]
    lote.data_inicio, lote.data_fim = min(ds), max(ds)
    return lote


def registros_legado(raw: dict) -> dict[str, list[dict]]:
    """Converte o objeto RAW do painel HTML antigo nos registros de cada conjunto."""
    out: dict[str, list[dict]] = {"calendario": [], "ouvidoria": [], "servicos": [], "tempos": [], "atendimentos": []}
    for dia in raw["dias"]:
        d = date.fromisoformat(dia["d"])
        out["calendario"].append({"data": d, "tipo": dia.get("tipo")})
        # o gerador antigo gravava subsetor vazio como o texto 'nan' (pandas)
        out["ouvidoria"] += [{"data": d, "setor": s, "subsetor": None if sb in ("nan", "") else sb, "qtd": n}
                             for s, sb, n in dia.get("ouv") or []]
        out["servicos"] += [{"data": d, "servico": s, "qtd": n} for s, n in ((dia.get("svc") or {}).get("itens") or [])]
        out["tempos"] += [{"data": d, "atendente": a, "n": n, "tme": tme, "tmd": tmd, "tma": tma, "tot": tot}
                          for a, n, tme, tmd, tma, tot in dia.get("tma") or []]
        out["atendimentos"] += [{"data": d, "hora": int(h) if h not in (None, "") else None, "servico": s,
                                 "atendente": a, "dur": dur, "perm": perm} for h, s, a, dur, perm in dia.get("atd") or []]
    return out
