"""Reconhecimento de dados: acha a linha de cabeçalho, sugere o conjunto e o mapeamento
coluna→campo, combinando semelhança do cabeçalho com compatibilidade dos valores."""
import re
from datetime import date, datetime
from pathlib import Path
from statistics import median

from .parse import CONVERSORES, compativel, norm, vazio
from .schemas import ESQUEMAS, Esquema

_SIN = {e: {c.nome: [norm(s) for s in c.sinonimos] for c in esq.campos} for e, esq in ESQUEMAS.items()}
_TODOS_L = sorted({s for e in _SIN.values() for ss in e.values() for s in ss})


_ABREV = [(re.compile(r"\b(t m|tm)\b"), "tempo medio"), (re.compile(r"\bqt\b"), "qtd"), (re.compile(r"\bserv\b"), "servico")]


def cab_norm(h) -> str:
    """Cabeçalho normalizado com abreviações comuns de relatórios expandidas ("T.M." → tempo medio)."""
    n = norm(h)
    for rx, por in _ABREV:
        n = rx.sub(por, n)
    return n


def _sim(h: str, sinonimos: list[str]) -> float:
    if not h:
        return 0.0
    best = 0.0
    for s in sinonimos:
        if h == s:
            return 1.0
        if len(s) >= 3 and f" {s} " in f" {h} ":
            best = max(best, 0.8)
        elif len(h) >= 3 and f" {h} " in f" {s} ":
            best = max(best, 0.6)
    return best


def acha_cabecalho(linhas: list[list]) -> int:
    melhor, idx = 0.0, 0
    for i, r in enumerate(linhas[:30]):
        pts = sum(_sim(cab_norm(c), _TODOS_L) for c in r if isinstance(c, str))
        if pts > melhor:
            melhor, idx = pts, i
    return idx


def separa(linhas: list[list]) -> tuple[list[str], list[list], list[int], int]:
    """Cabeçalho, linhas de dados (sem vazias nem cabeçalhos repetidos), nº original de
    cada linha (1-based, como na planilha) e índice do cabeçalho."""
    i = acha_cabecalho(linhas)
    cab = [str(c).strip() if not vazio(c) else f"Coluna {j + 1}" for j, c in enumerate(linhas[i])]
    chave, largura = [norm(c) for c in linhas[i]], len(cab)
    dados, nums = [], []
    for n, r in enumerate(linhas[i + 1:], start=i + 2):
        if all(vazio(c) for c in r) or [norm(c) for c in r] == chave:  # cabeçalho repetido por página
            continue
        dados.append(list(r[:largura]) + [None] * (largura - len(r)))
        nums.append(n)
    return cab, dados, nums, i


def mapeia(esq: Esquema, cab: list[str], dados: list[list]) -> dict[str, tuple[int, float]]:
    amostra = [[r[j] for r in dados[:300]] for j in range(len(cab))]
    comp = {}
    cand = []
    for c in esq.campos:
        for j, h in enumerate(cab):
            s = _sim(cab_norm(h), _SIN[esq.nome][c.nome])
            if not s:
                continue
            k = comp.setdefault((c.tipo, j), compativel(c.tipo, amostra[j]))
            score = s * (0.4 + 0.6 * k) * (0.5 if k < 0.5 else 1)
            cand.append((score, c.nome, j))
    usados_c, usados_j, out = set(), set(), {}
    for score, nome, j in sorted(cand, reverse=True):
        if nome in usados_c or j in usados_j:
            continue
        out[nome] = (j, round(score, 3))
        usados_c.add(nome)
        usados_j.add(j)
    # data sem cabeçalho reconhecível: usa a coluna cujos valores são datas
    if "data" not in out and "data_hora" not in out:
        for j in range(len(cab)):
            if j not in usados_j and compativel("data", amostra[j]) >= 0.9:
                out["data"] = (j, 0.5)
                break
    return out


def pontua(esq: Esquema, mapa: dict, arquivo: str, data_arquivo: date | None = None) -> float:
    """data_arquivo: data tirada do nome do arquivo, que supre a falta de coluna de data."""
    alt = {n: g for g in esq.alternativos for n in g}
    req = [c.nome for c in esq.campos if c.obrigatorio]
    cob = 0.0
    for n in req:
        grupo = alt.get(n, (n,))
        cob += max((mapa[g][1] for g in grupo if g in mapa), default=0.9 if n == "data" and data_arquivo else 0.0)
    opc = [c.nome for c in esq.campos if not c.obrigatorio and not any(c.nome in g for g in esq.alternativos)]
    s = 0.8 * cob / len(req) + (0.2 * sum(n in mapa for n in opc) / len(opc) if opc else 0.2)
    if any(d in norm(Path(arquivo).stem) for d in esq.dicas_arquivo):
        s += 0.15
    return round(min(s, 1.0), 3)


def unidades(esq: Esquema, mapa: dict, dados: list[list]) -> tuple[dict, list[str]]:
    """Durações numéricas são ambíguas (segundos ou minutos): sugere e avisa."""
    un, avisos = {}, []
    for c in esq.campos:
        if c.tipo != "duracao" or c.nome not in mapa:
            continue
        j = mapa[c.nome][0]
        nums = [r[j] for r in dados[:300] if isinstance(r[j], (int, float)) and not isinstance(r[j], bool)]
        if not nums:
            un[c.nome] = "s"
            continue
        frac = any(not float(v).is_integer() for v in nums)
        un[c.nome] = "min" if frac and median(nums) < 120 else "s"
        avisos.append(f"'{c.nome}' tem valores numéricos; assumido {'minutos' if un[c.nome] == 'min' else 'segundos'} — confirme.")
    return un, avisos


def analisa(arquivo: str, abas: list[dict], data_arquivo: date | None = None) -> dict:
    melhor = None
    for ai, aba in enumerate(abas):
        cab, dados, _, _ = separa(aba["linhas"])
        for nome, esq in ESQUEMAS.items():
            s = pontua(esq, mapeia(esq, cab, dados), arquivo, data_arquivo)
            if not melhor or s > melhor["confianca"]:
                melhor = {"aba": ai, "conjunto": nome, "confianca": s}
    if not melhor:
        return {"abas": [], "avisos": ["Arquivo sem dados legíveis."]}
    return detalha(arquivo, abas, melhor["aba"], melhor["conjunto"], None, data_arquivo)


def detalha(arquivo: str, abas: list[dict], aba: int, conjunto: str, forcar_mapa: dict | None,
            data_arquivo: date | None = None) -> dict:
    """Resultado completo para a tela de conferência (também usado ao trocar aba/conjunto)."""
    esq = ESQUEMAS[conjunto]
    cab, dados, _, hi = separa(abas[aba]["linhas"])
    mapa = mapeia(esq, cab, dados)
    ranking = sorted(((n, pontua(e, mapeia(e, cab, dados), arquivo, data_arquivo)) for n, e in ESQUEMAS.items()),
                     key=lambda x: -x[1])
    un, avisos = unidades(esq, mapa, dados)
    faltando = [c.nome for c in esq.campos if c.obrigatorio and c.nome not in mapa
                and not any(c.nome in g and any(x in mapa for x in g) for g in esq.alternativos)]
    if "data" in faltando and data_arquivo:
        faltando.remove("data")
        avisos.insert(0, f"Sem coluna de data: usado o dia do nome do arquivo ({data_arquivo:%d/%m/%Y}).")
    if faltando:
        avisos.insert(0, f"Campos obrigatórios sem coluna correspondente: {', '.join(faltando)}.")
    return {
        "abas": [{"nome": a["nome"], "linhas": len(a["linhas"])} for a in abas],
        "aba": aba, "linha_cabecalho": hi + 1, "colunas": cab, "total_linhas": len(dados),
        "amostra": [[_str(v) for v in r] for r in dados[:15]],
        "conjunto": conjunto, "confianca": dict(ranking)[conjunto], "ranking": ranking,
        "mapeamento": forcar_mapa if forcar_mapa is not None else {k: v[0] for k, v in mapa.items()},
        "confianca_campos": {k: v[1] for k, v in mapa.items()},
        "unidades": un, "avisos": avisos, "faltando": faltando,
        "data_arquivo": data_arquivo.isoformat() if data_arquivo else None,
        "campos": [{"nome": c.nome, "tipo": c.tipo, "obrigatorio": c.obrigatorio, "descricao": c.descricao} for c in esq.campos],
    }


def _str(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M:%S" if v.hour or v.minute or v.second else "%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def converte(conjunto: str, dados: list[list], mapa: dict[str, int], un: dict[str, str], nums: list[int],
             data_padrao: date | None = None):
    """Converte as linhas em registros tipados. Linhas com erro são descartadas e relatadas.
    data_padrao (do nome do arquivo) preenche a data quando não há coluna de data mapeada."""
    esq = ESQUEMAS[conjunto]
    alt = {n: g for g in esq.alternativos for n in g}
    regs, erros = [], []
    for i, r in enumerate(dados):
        rec, erro = {}, None
        for c in esq.campos:
            j = mapa.get(c.nome)
            v = r[j] if j is not None and j < len(r) else None
            if vazio(v):
                rec[c.nome] = None
                continue
            try:
                rec[c.nome] = CONVERSORES[c.tipo](v, un.get(c.nome, "s")) if c.tipo == "duracao" else CONVERSORES[c.tipo](v)
            except (ValueError, TypeError, OverflowError) as e:
                erro = {"linha": nums[i], "campo": c.nome, "valor": _str(v)[:60], "erro": str(e)}
                break
        if not erro:
            if rec.get("data") is None and data_padrao and "data" not in mapa:
                rec["data"] = data_padrao
            if rec.get("data_hora"):
                rec["data"] = rec["data"] or rec["data_hora"].date()
                if rec.get("hora") is None and "hora" in {c.nome for c in esq.campos}:
                    rec["hora"] = rec["data_hora"].hour
            for c in esq.campos:
                if c.obrigatorio and rec.get(c.nome) is None and not any(rec.get(x) is not None for x in alt.get(c.nome, ())):
                    erro = {"linha": nums[i], "campo": c.nome, "valor": "", "erro": "obrigatório vazio"}
                    break
        if erro:
            erros.append(erro)
        else:
            regs.append(rec)
    return regs, erros
