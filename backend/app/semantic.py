"""Camada semântica de BI: conjuntos, dimensões e medidas nomeadas.

O frontend nunca envia SQL; ele pede {conjunto, dims, medidas, filtros} e este módulo
monta a consulta só com nomes da lista abaixo. Filtros globais (setor, serviço,
atendente) atingem apenas os conjuntos que têm a coluna, reproduzindo o filtro
cruzado do painel HTML original.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from .models import Dia, FAtendimento, FOuvidoria, FServico, FTempo, ImportBatch


def _wavg(col, n):
    """Média ponderada pelo nº de atendimentos, ignorando médias nulas."""
    return func.sum(case((col.is_not(None), col * n))) / func.nullif(func.sum(case((col.is_not(None), n))), 0)


_dur = FAtendimento.dur
FAIXA_DURACAO = case(
    (_dur.is_(None), None), (_dur < 300, "até 5"), (_dur < 600, "5–10"),
    (_dur < 1200, "10–20"), (_dur < 1800, "20–30"), else_="30+",
)
DIMS_DIA = {"data": Dia.data, "mes": Dia.ano_mes, "dia_semana": Dia.dia_semana, "tipo_dia": Dia.tipo}


@dataclass
class Conjunto:
    rotulo: str
    fato: Any
    dims: dict[str, Any]
    medidas: dict[str, Any]
    filtros: dict[str, Any] = field(default_factory=dict)


CONJUNTOS: dict[str, Conjunto] = {
    "calendario": Conjunto("Calendário", None, dict(DIMS_DIA), {"dias": func.count(Dia.data)}),
    "ouvidoria": Conjunto(
        "Ouvidoria (remoto)", FOuvidoria,
        {**DIMS_DIA, "setor": FOuvidoria.setor, "subsetor": FOuvidoria.subsetor},
        {"mensagens": func.sum(FOuvidoria.qtd), "dias": func.count(distinct(FOuvidoria.data))},
        {"setor": FOuvidoria.setor, "subsetor": FOuvidoria.subsetor},
    ),
    "atendimentos": Conjunto(
        "Atendimentos concluídos", FAtendimento,
        {**DIMS_DIA, "hora": FAtendimento.hora, "servico": FAtendimento.servico,
         "atendente": FAtendimento.atendente, "faixa_duracao": FAIXA_DURACAO},
        {"atendimentos": func.count(FAtendimento.id), "duracao_media": func.avg(FAtendimento.dur),
         "permanencia_media": func.avg(FAtendimento.perm), "dias": func.count(distinct(FAtendimento.data))},
        {"servico": FAtendimento.servico, "atendente": FAtendimento.atendente},
    ),
    "servicos": Conjunto(
        "Serviços executados", FServico,
        {**DIMS_DIA, "servico": FServico.servico},
        {"servicos": func.sum(FServico.qtd), "dias": func.count(distinct(FServico.data))},
        {"servico": FServico.servico},
    ),
    "tempos": Conjunto(
        "Tempos por atendente (TMA)", FTempo,
        {**DIMS_DIA, "atendente": FTempo.atendente},
        {"atendimentos": func.sum(FTempo.n), "tme": _wavg(FTempo.tme, FTempo.n), "tmd": _wavg(FTempo.tmd, FTempo.n),
         "tma": _wavg(FTempo.tma, FTempo.n), "tot": _wavg(FTempo.tot, FTempo.n), "dias": func.count(distinct(FTempo.data))},
        {"atendente": FTempo.atendente},
    ),
}
FILTROS_GLOBAIS = ("setor", "subsetor", "servico", "atendente")


class Filtros(BaseModel):
    de: date | None = None
    ate: date | None = None
    tipo: str | None = None
    setor: str | None = None
    subsetor: str | None = None
    servico: str | None = None
    atendente: str | None = None


class Consulta(BaseModel):
    conjunto: str
    dims: list[str] = []
    medidas: list[str]
    filtros: Filtros = Filtros()
    # nomes de filtros a ignorar nesta consulta ("periodo", "tipo", "setor", ...):
    # permite que o gráfico de setores continue mostrando todos os setores com um setor selecionado
    ignorar: list[str] = []
    ordem: list[str] = []  # "campo" ou "-campo"
    limite: int | None = Field(None, ge=1, le=20000)


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def executa(db: Session, q: Consulta) -> dict:
    cj = CONJUNTOS.get(q.conjunto)
    if not cj:
        raise HTTPException(422, f"Conjunto desconhecido: {q.conjunto}")
    for d in q.dims:
        if d not in cj.dims:
            raise HTTPException(422, f"Dimensão '{d}' não existe em {q.conjunto}")
    for m in q.medidas:
        if m not in cj.medidas:
            raise HTTPException(422, f"Medida '{m}' não existe em {q.conjunto}")
    cols = {d: cj.dims[d].label(d) for d in q.dims} | {m: cj.medidas[m].label(m) for m in q.medidas}
    stmt = select(*cols.values())
    stmt = stmt.select_from(cj.fato).join(Dia, Dia.data == cj.fato.data) if cj.fato else stmt.select_from(Dia)

    f, ign = q.filtros, set(q.ignorar)
    if "periodo" not in ign:
        if f.de:
            stmt = stmt.where(Dia.data >= f.de)
        if f.ate:
            stmt = stmt.where(Dia.data <= f.ate)
    if f.tipo and "tipo" not in ign:
        stmt = stmt.where(Dia.tipo == f.tipo)
    for nome, col in cj.filtros.items():
        v = getattr(f, nome)
        if v and nome not in ign:
            stmt = stmt.where(col == v)

    if q.dims:
        stmt = stmt.group_by(*(cj.dims[d] for d in q.dims))
    ordem = q.ordem or q.dims
    for o in ordem:
        nome = o.lstrip("-")
        if nome not in cols:
            raise HTTPException(422, f"Ordenação por campo ausente: {nome}")
        stmt = stmt.order_by(cols[nome].desc() if o.startswith("-") else cols[nome].asc())
    if q.limite:
        stmt = stmt.limit(q.limite)
    rows = db.execute(stmt).all()
    return {"colunas": list(cols), "linhas": [[_json(v) for v in r] for r in rows]}


def catalogo() -> dict:
    return {k: {"rotulo": c.rotulo, "dims": list(c.dims), "medidas": list(c.medidas), "filtros": list(c.filtros)}
            for k, c in CONJUNTOS.items()}


def meta(db: Session) -> dict:
    """Contexto do painel: recorte disponível, meses, mês parcial, tipos de dia, ranking de setores
    (cores estáveis por entidade) e cobertura de cada fonte."""
    fontes, ini, fim = {}, None, None
    for nome, cj in CONJUNTOS.items():
        if not cj.fato:
            continue
        lo, hi, n = db.execute(select(func.min(cj.fato.data), func.max(cj.fato.data), func.count(cj.fato.id))).one()
        ult = db.execute(select(func.max(ImportBatch.criado_em)).where(
            ImportBatch.conjunto.in_([nome, "legado"]), ImportBatch.status == "ativo")).scalar()
        fontes[nome] = {"rotulo": cj.rotulo, "de": _json(lo), "ate": _json(hi), "linhas": n,
                        "ultima_importacao": ult.isoformat() if ult else None}
        if lo:
            ini, fim = min(ini or lo, lo), max(fim or hi, hi)
    if not ini:
        return {"vazio": True, "fontes": fontes, "catalogo": catalogo()}

    meses = db.scalars(select(Dia.ano_mes).where(Dia.data.between(ini, fim)).distinct().order_by(Dia.ano_mes)).all()
    prox = (fim.replace(day=28) + timedelta(days=4)).replace(day=1)
    parcial = fim.strftime("%Y-%m") if fim < prox - timedelta(days=1) else None
    tipos = db.execute(select(Dia.tipo, func.count()).where(Dia.data.between(ini, fim))
                       .group_by(Dia.tipo).order_by(func.count().desc())).all()
    setores = db.scalars(select(FOuvidoria.setor).group_by(FOuvidoria.setor)
                         .order_by(func.sum(FOuvidoria.qtd).desc())).all()
    servicos = sorted(set(db.scalars(select(FAtendimento.servico).distinct()).all())
                      | set(db.scalars(select(FServico.servico).distinct()).all()))
    atendentes = sorted(set(db.scalars(select(FTempo.atendente).distinct()).all())
                        | set(db.scalars(select(FAtendimento.atendente).distinct()).all()))
    return {
        "vazio": False, "de": ini.isoformat(), "ate": fim.isoformat(), "meses": meses, "parcial": parcial,
        "tipos": [[t, n] for t, n in tipos], "setores": setores, "servicos": servicos, "atendentes": atendentes,
        "fontes": fontes, "catalogo": catalogo(),
    }
