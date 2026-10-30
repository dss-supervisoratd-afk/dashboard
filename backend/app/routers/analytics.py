from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import exige
from ..semantic import Consulta, executa, meta

router = APIRouter(prefix="/api/bi", tags=["BI"])


class Lote(BaseModel):
    consultas: dict[str, Consulta] = Field(max_length=40)


@router.get("/meta")
def get_meta(db: Session = Depends(get_db), _: User = Depends(exige("painel:ver"))):
    return meta(db)


@router.post("/consulta")
def consulta(q: Consulta, db: Session = Depends(get_db), _: User = Depends(exige("painel:ver"))):
    return executa(db, q)


@router.post("/lote")
def lote(q: Lote, db: Session = Depends(get_db), _: User = Depends(exige("painel:ver"))):
    """Várias consultas numa ida ao servidor (uma tela do painel = um lote)."""
    if not q.consultas:
        raise HTTPException(422, "Lote vazio")
    return {k: executa(db, c) for k, c in q.consultas.items()}
