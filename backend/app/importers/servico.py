"""Reconhecer e gravar um arquivo — usado pela API (envio a envio) e pela CLI (pasta inteira).

Tipos de arquivo, na ordem em que são tentados:
  legado    painel HTML antigo (const RAW)
  sga       PDF do Novo SGA (atendimentos, serviços, tempos) — leitor dedicado
  cadastro  "Guichês - Tabela Consolidada" — substitui o cadastro e renomeia o histórico
  planilha  CSV/XLSX/XLS/PDF genérico — reconhecimento de colunas + conferência
"""
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import FATOS, ImportBatch
from . import readers
from .load import aplica_tipo_dia, carrega, garante_dias, carrega_cadastro, carrega_legado, registros_legado
from .recognize import _str, analisa as analisa_abas, converte, detalha, separa
from .schemas import ESQUEMAS
from .sga import SgaInvalido, e_consolidado_protocolos, le_cadastro_guiches, le_pdf_sga, meta_nome

CONFIANCA_AUTOMATICA = 0.75


class Recusado(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


class Opcoes(BaseModel):
    aba: int | None = None
    conjunto: str | None = None
    mapeamento: dict[str, int | None] | None = None
    unidades: dict[str, str] | None = None


def _amostra(regs: list[dict], n: int = 8) -> dict:
    cols = list(regs[0]) if regs else []
    return {"colunas": cols, "amostra": [[_str(r.get(c)) for c in cols] for r in regs[:n]]}


def _planilha(nome: str, raw: bytes, op: Opcoes) -> tuple[dict, list[dict], list[dict]]:
    try:
        abas = readers.le(nome, raw)
    except readers.FormatoNaoSuportado as e:
        raise Recusado(415, str(e))
    for a in abas:
        if any(e_consolidado_protocolos(r) for r in a["linhas"][:5]):
            raise Recusado(422, "Este é o consolidado de protocolos (“Ouvidorias por Situação”): tem nomes de associados "
                                "e não é fonte do painel. Importe os relatórios diários de Ouvidorias.")
    data_arquivo, _ = meta_nome(nome)
    if op.conjunto is None and op.aba is None:
        res = analisa_abas(nome, abas, data_arquivo)
    else:
        aba, conj = op.aba or 0, op.conjunto or "ouvidoria"
        if conj not in ESQUEMAS or not 0 <= aba < len(abas):
            raise Recusado(422, "Aba ou conjunto inválido")
        res = detalha(nome, abas, aba, conj, None, data_arquivo)
    if op.mapeamento is not None and op.conjunto in (None, res["conjunto"]):
        res["mapeamento"] = {k: v for k, v in op.mapeamento.items() if v is not None and 0 <= v < len(res["colunas"])}
    if op.unidades:
        res["unidades"] |= {k: v for k, v in op.unidades.items() if v in ("s", "min")}
    _, dados, nums, _ = separa(abas[res["aba"]]["linhas"])
    regs, erros = converte(res["conjunto"], dados, res["mapeamento"], res["unidades"], nums, data_arquivo)
    ds = [r["data"] for r in regs if r.get("data")]
    res["validacao"] = {"validas": len(regs), "com_erro": len(erros), "erros": erros[:30],
                        "de": min(ds).isoformat() if ds else None, "ate": max(ds).isoformat() if ds else None,
                        "dias": len(set(ds))}
    # gravação sem conferência (importação em massa) só para relatório diário reconhecido com folga:
    # PDF genérico e planilha sem data no nome sempre passam pela tela de conferência
    # arquivo diário só com cabeçalho = dia sem registros (ex.: domingo sem mensagens): zera o dia
    res["dia_vazio"] = data_arquivo is not None and not dados and not res["faltando"]
    res["autoconfiavel"] = ((bool(regs) or res["dia_vazio"]) and res["confianca"] >= CONFIANCA_AUTOMATICA
                            and not res["faltando"] and data_arquivo is not None and not nome.lower().endswith(".pdf"))
    return res, regs, erros


def _confere_data_do_nome(lido, nome: str) -> None:
    """O período impresso no PDF prevalece sobre o nome do arquivo; divergência vira aviso no lote
    (ex.: '2026.02.08 Serviços executados.pdf' que contém o relatório de 06/02)."""
    dn, _ = meta_nome(nome)
    if dn and not (lido.de == lido.ate == dn):
        periodo = f"{lido.de:%d/%m/%Y}" if lido.de == lido.ate else f"{lido.de:%d/%m/%Y} a {lido.ate:%d/%m/%Y}"
        lido.avisos.insert(0, f"O nome do arquivo indica {dn:%d/%m/%Y}, mas o relatório é de {periodo}: "
                              "gravado pelo período do relatório. Confira se o arquivo do dia certo existe.")


def e_cadastro_nome(nome: str) -> bool:
    return nome.lower().endswith((".xlsx", ".xlsm")) and "guich" in nome.lower() and "consolid" in nome.lower()


def analisa(nome: str, raw: bytes, op: Opcoes | None = None) -> dict:
    op = op or Opcoes()
    ext = Path(nome).suffix.lower()
    _, tipo_dia = meta_nome(nome)
    base = {"tipo_dia": tipo_dia}
    if ext in (".html", ".htm"):
        legado = readers.extrai_raw_legado(raw)
        if not legado:
            raise Recusado(415, "HTML sem o bloco de dados do painel antigo (const RAW)")
        return base | {"automatico": True, "tipo_arquivo": "legado", "conjunto": "legado", "autoconfiavel": True,
                       "resumo": {k: len(v) for k, v in registros_legado(legado).items()},
                       "de": legado["dias"][0]["d"], "ate": legado["dias"][-1]["d"], "avisos": []}
    if ext == ".pdf" and op.conjunto is None:
        try:
            lido = le_pdf_sga(raw)
        except SgaInvalido as e:
            raise Recusado(422, str(e))
        if lido:
            _confere_data_do_nome(lido, nome)
            return base | {"automatico": True, "tipo_arquivo": "sga", "conjunto": lido.conjunto, "autoconfiavel": True,
                           "de": lido.de.isoformat(), "ate": lido.ate.isoformat(), "linhas": len(lido.registros),
                           "avisos": lido.avisos} | _amostra(lido.registros)
    if ext in (".xlsx", ".xlsm") and op.conjunto is None:
        cad = le_cadastro_guiches(raw)
        if cad is not None:
            regs = [{"tipo": o.tipo, "numero": o.numero, "atendente": o.atendente, "grupo": o.grupo,
                     "vigencia_inicio": o.vig_inicio, "vigencia_fim": o.vig_fim} for o in cad]
            return base | {"automatico": True, "tipo_arquivo": "cadastro", "conjunto": "guiches", "autoconfiavel": True,
                           "linhas": len(cad), "avisos": ["Substitui o cadastro atual e renomeia atendimentos e tempos já carregados."]} \
                | _amostra(regs, 40)
    res, _, _ = _planilha(nome, raw, op)
    return base | res | {"automatico": False, "tipo_arquivo": "planilha"}


def grava(db: Session, nome: str, raw: bytes, sha: str, usuario_id: int | None, op: Opcoes | None = None
          ) -> tuple[ImportBatch, list[dict]]:
    """Grava o arquivo (mesmo reconhecimento de analisa) e devolve o lote e as linhas descartadas."""
    op = op or Opcoes()
    ext = Path(nome).suffix.lower()
    data_nome, tipo_dia = meta_nome(nome)
    if ext in (".html", ".htm"):
        return carrega_legado(db, readers.extrai_raw_legado(raw), nome, sha, usuario_id), []

    lido = cad = None
    if ext == ".pdf" and op.conjunto is None:
        try:
            lido = le_pdf_sga(raw)
        except SgaInvalido as e:
            raise Recusado(422, str(e))
    if ext in (".xlsx", ".xlsm") and op.conjunto is None:
        cad = le_cadastro_guiches(raw)

    if cad is not None:
        lote = ImportBatch(conjunto="guiches", arquivo=nome, sha256=sha, usuario_id=usuario_id, linhas_lidas=len(cad),
                           mapeamento={"origem": "cadastro de guichês"}, avisos=[])
        db.add(lote)
        db.flush()
        lote.linhas_carregadas, renomeadas = carrega_cadastro(db, cad, lote)
        lote.avisos = [f"{renomeadas} linha(s) de atendimentos/tempos renomeada(s)"]
        return lote, []

    if lido:
        _confere_data_do_nome(lido, nome)
        conj, regs, erros, avisos = lido.conjunto, lido.registros, [], list(lido.avisos)
        mapa = {"origem": "PDF Novo SGA"}
        de, ate = lido.de, lido.ate
    else:
        res, regs, erros = _planilha(nome, raw, op)
        if not regs and not res["dia_vazio"]:
            raise Recusado(422, "Nenhuma linha válida com o mapeamento informado")
        conj, avisos = res["conjunto"], res["avisos"] + [f"{len(erros)} linha(s) descartada(s) por erro"] * bool(erros)
        mapa = {"aba": res["aba"], "colunas": {k: res["colunas"][v] for k, v in res["mapeamento"].items()},
                "unidades": res["unidades"]}
        ds = [r["data"] for r in regs] or [data_nome]
        de, ate = min(ds), max(ds)

    lote = ImportBatch(conjunto=conj, arquivo=nome, sha256=sha, usuario_id=usuario_id, linhas_lidas=len(regs) + len(erros),
                       mapeamento=mapa, avisos=avisos, data_inicio=de, data_fim=ate)
    db.add(lote)
    db.flush()
    lote.linhas_carregadas = carrega(db, conj, regs, lote) if regs else 0
    if not regs and de == ate and conj in FATOS:
        # dia sem movimento (feriado, domingo sem mensagens): zera o dia no conjunto em vez de manter dado antigo
        garante_dias(db, {de})
        db.execute(delete(FATOS[conj]).where(FATOS[conj].data == de))
    # tipo de dia vai para o dia do conteúdo quando o relatório é de um dia só (vale mesmo com nome trocado)
    dia_tipo = de if lido and de == ate else data_nome
    if dia_tipo and tipo_dia:
        aplica_tipo_dia(db, dia_tipo, tipo_dia)
    return lote, erros
