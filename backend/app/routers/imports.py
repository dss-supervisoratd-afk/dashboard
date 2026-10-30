"""Importação em duas etapas: (1) envio + reconhecimento + prévia; (2) confirmação do
mapeamento, gravação e criação do lote (que pode ser revertido depois)."""
import csv
import hashlib
import io
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..importers import servico
from ..importers.schemas import ESQUEMAS
from ..models import FATOS, CadGuiche, ImportBatch, User
from ..security import audita, exige

router = APIRouter(prefix="/api/importacoes", tags=["importação"])
_ID = re.compile(r"^[0-9a-f]{32}$")
_UP = Path(settings.upload_dir)


def _caminho(uid: str) -> Path:
    if not _ID.match(uid):
        raise HTTPException(404, "Envio não encontrado")
    return _UP / uid


def _carrega_envio(uid: str) -> tuple[dict, bytes]:
    p = _caminho(uid)
    if not (p / "meta.json").exists():
        raise HTTPException(404, "Envio expirado ou inexistente; envie o arquivo novamente")
    return json.loads((p / "meta.json").read_text("utf-8")), (p / "arquivo").read_bytes()


def _limpa_antigos() -> None:
    if not _UP.exists():
        return
    for d in _UP.iterdir():
        if d.is_dir() and time.time() - d.stat().st_mtime > 86400:
            for f in d.iterdir():
                f.unlink(missing_ok=True)
            d.rmdir()


def _duplicado(db: Session, sha: str, nome: str) -> dict | None:
    # mesmo conteúdo E mesmo nome: diários de dias diferentes podem ter conteúdo idêntico
    # (a data de uma planilha de Ouvidoria está só no nome do arquivo)
    b = db.scalar(select(ImportBatch).where(ImportBatch.sha256 == sha, ImportBatch.arquivo == nome, ImportBatch.status == "ativo"))
    return {"lote": b.id, "em": b.criado_em.isoformat(), "conjunto": b.conjunto} if b else None


def _recusa(e: servico.Recusado):
    return HTTPException(e.status, str(e))


@router.get("/esquemas")
def esquemas(_: User = Depends(exige("painel:ver"))):
    return {k: {"rotulo": e.rotulo, "campos": [{"nome": c.nome, "tipo": c.tipo, "obrigatorio": c.obrigatorio,
                                                "descricao": c.descricao} for c in e.campos]} for k, e in ESQUEMAS.items()}


@router.post("/analisar")
async def analisar(arquivo: UploadFile, db: Session = Depends(get_db), _: User = Depends(exige("dados:importar"))):
    raw = await arquivo.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Arquivo maior que {settings.max_upload_mb} MB")
    nome = Path(arquivo.filename or "arquivo").name
    sha = hashlib.sha256(raw).hexdigest()
    try:
        res = servico.analisa(nome, raw)
    except servico.Recusado as e:
        raise _recusa(e)
    _limpa_antigos()
    uid = uuid.uuid4().hex
    p = _UP / uid
    p.mkdir(parents=True)
    (p / "arquivo").write_bytes(raw)
    (p / "meta.json").write_text(json.dumps({"arquivo": nome, "sha256": sha}), "utf-8")
    return {"envio": uid, "arquivo": nome, "duplicado": _duplicado(db, sha, nome)} | res


@router.post("/{envio}/previa")
def previa(envio: str, op: servico.Opcoes, _: User = Depends(exige("dados:importar"))):
    meta, raw = _carrega_envio(envio)
    try:
        res = servico.analisa(meta["arquivo"], raw, op)
    except servico.Recusado as e:
        raise _recusa(e)
    return {"envio": envio, "arquivo": meta["arquivo"]} | res


@router.post("/{envio}/confirmar")
def confirmar(envio: str, op: servico.Opcoes, db: Session = Depends(get_db), quem: User = Depends(exige("dados:importar"))):
    meta, raw = _carrega_envio(envio)
    try:
        lote, erros = servico.grava(db, meta["arquivo"], raw, meta["sha256"], quem.id, op)
    except servico.Recusado as e:
        raise _recusa(e)
    audita(db, quem, "importacao", lote=lote.id, conjunto=lote.conjunto, arquivo=lote.arquivo,
           linhas=lote.linhas_carregadas, descartadas=len(erros))
    db.commit()
    p = _caminho(envio)
    for f in p.iterdir():
        f.unlink(missing_ok=True)
    p.rmdir()
    return {"lote": _lote(lote, {quem.id: quem.email}), "descartadas": len(erros), "erros": erros[:30]}


def _lote(b: ImportBatch, emails: dict) -> dict:
    return {"id": b.id, "conjunto": b.conjunto, "arquivo": b.arquivo, "status": b.status, "linhas_lidas": b.linhas_lidas,
            "linhas_carregadas": b.linhas_carregadas, "de": b.data_inicio.isoformat() if b.data_inicio else None,
            "ate": b.data_fim.isoformat() if b.data_fim else None, "avisos": b.avisos or [], "mapeamento": b.mapeamento,
            "usuario": emails.get(b.usuario_id), "criado_em": b.criado_em.isoformat()}


@router.get("")
def lista(db: Session = Depends(get_db), _: User = Depends(exige("painel:ver"))):
    emails = dict(db.execute(select(User.id, User.email)).all())
    return [_lote(b, emails) for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(300))]


@router.delete("/{lote_id}")
def reverte(lote_id: int, db: Session = Depends(get_db), quem: User = Depends(exige("dados:excluir"))):
    """Remove as linhas do lote. Não restaura dados que o lote tinha substituído."""
    b = db.get(ImportBatch, lote_id)
    if not b or b.status != "ativo":
        raise HTTPException(404, "Lote ativo não encontrado")
    removidas = 0
    for fato in FATOS.values():
        removidas += db.execute(delete(fato).where(fato.lote_id == b.id)).rowcount or 0
    if b.conjunto == "guiches":  # nomes já resolvidos ficam como estão até o próximo cadastro
        removidas += db.execute(delete(CadGuiche).where(CadGuiche.lote_id == b.id)).rowcount or 0
    b.status = "revertido"
    audita(db, quem, "importacao_revertida", lote=b.id, linhas=removidas)
    db.commit()
    return {"ok": True, "removidas": removidas}


@router.get("/modelos/{conjunto}.{ext}")
def modelo(conjunto: str, ext: str, _: User = Depends(exige("painel:ver"))):
    """Planilha padronizada de cada conjunto: cabeçalhos canônicos + uma linha de exemplo."""
    esq = ESQUEMAS.get(conjunto)
    if not esq or ext not in ("csv", "xlsx"):
        raise HTTPException(404, "Modelo inexistente")
    exemplo = {"data": date.today().strftime("%d/%m/%Y"), "data_hora": date.today().strftime("%d/%m/%Y") + " 09:15",
               "hora": "9", "setor": "PLANOS DE SAÚDE E ODONTOLÓGICOS", "subsetor": "UNIMED-FERJ", "qtd": "1",
               "servico": "Seguro Auto(Novo/Renovação)", "atendente": "Nome do atendente", "dur": "00:12:30",
               "perm": "00:25:10", "n": "12", "tme": "00:06:40", "tmd": "00:00:35", "tma": "00:11:05",
               "tot": "00:18:20", "tipo": "Feriado"}
    cab = [c.nome for c in esq.campos]
    lin = [exemplo.get(c, "") for c in cab]
    if ext == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerows([cab, lin])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="modelo_{conjunto}.csv"'})
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = esq.rotulo[:31]
    ws.append(cab)
    ws.append(lin)
    ws2 = wb.create_sheet("Instruções")
    ws2.append(["campo", "obrigatório", "tipo", "descrição"])
    for c in esq.campos:
        ws2.append([c.nome, "sim" if c.obrigatorio else "não", c.tipo, c.descricao])
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="modelo_{conjunto}.xlsx"'})
