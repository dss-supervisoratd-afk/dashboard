from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Auditoria, User
from ..security import Email, audita, exige, hash_senha
from .auth import perfil

router = APIRouter(prefix="/api", tags=["usuários"])
Papel = Literal["admin", "gestor", "leitor"]


def _linha(u: User) -> dict:
    return perfil(u) | {"ativo": u.ativo, "criado_em": u.criado_em.isoformat(),
                        "ultimo_acesso": u.ultimo_acesso.isoformat() if u.ultimo_acesso else None}


class NovoUsuario(BaseModel):
    email: Email
    nome: str = Field(min_length=2, max_length=120)
    papel: Papel = "leitor"
    senha: str | None = Field(None, min_length=10, max_length=128)  # sem senha = só login Google


class AlteraUsuario(BaseModel):
    nome: str | None = Field(None, min_length=2, max_length=120)
    papel: Papel | None = None
    ativo: bool | None = None
    senha: str | None = Field(None, min_length=10, max_length=128)


@router.get("/usuarios")
def lista(db: Session = Depends(get_db), _: User = Depends(exige("usuarios:gerir"))):
    return [_linha(u) for u in db.scalars(select(User).order_by(User.nome))]


@router.post("/usuarios", status_code=201)
def cria(dados: NovoUsuario, db: Session = Depends(get_db), quem: User = Depends(exige("usuarios:gerir"))):
    email = dados.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email já cadastrado")
    u = User(email=email, nome=dados.nome, papel=dados.papel, senha_hash=hash_senha(dados.senha) if dados.senha else None)
    db.add(u)
    db.flush()
    audita(db, quem, "usuario_criado", alvo=u.id, email=email, papel=dados.papel)
    db.commit()
    return _linha(u)


@router.patch("/usuarios/{uid}")
def altera(uid: int, dados: AlteraUsuario, db: Session = Depends(get_db), quem: User = Depends(exige("usuarios:gerir"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    perde_admin = u.papel == "admin" and ((dados.papel and dados.papel != "admin") or dados.ativo is False)
    if perde_admin:
        admins = db.scalar(select(func.count()).select_from(User).where(User.papel == "admin", User.ativo))
        if admins <= 1:
            raise HTTPException(400, "Não é possível remover o último administrador ativo")
    mud = dados.model_dump(exclude_unset=True, exclude={"senha"})
    for k, v in mud.items():
        setattr(u, k, v)
    if dados.senha:
        u.senha_hash = hash_senha(dados.senha)
        mud["senha"] = "redefinida"
    audita(db, quem, "usuario_alterado", alvo=u.id, **mud)
    db.commit()
    return _linha(u)


@router.get("/auditoria")
def auditoria(limite: int = 200, db: Session = Depends(get_db), _: User = Depends(exige("auditoria:ver"))):
    nomes = dict(db.execute(select(User.id, User.email)).all())
    rows = db.scalars(select(Auditoria).order_by(Auditoria.id.desc()).limit(min(limite, 1000)))
    return [{"id": a.id, "quando": a.criado_em.isoformat(), "usuario": nomes.get(a.usuario_id), "acao": a.acao,
             "detalhe": a.detalhe} for a in rows]
