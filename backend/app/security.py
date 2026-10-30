"""Senhas (argon2), sessão em JWT num cookie httpOnly, RBAC e trilha de auditoria."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from pydantic import StringConstraints
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Auditoria, User

COOKIE = "amn_sessao"
# validação propositalmente simples: domínios internos (.local, .intra) são válidos aqui
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
_ph = PasswordHasher()

PAPEIS = {
    "admin": {"painel:ver", "dados:importar", "dados:excluir", "usuarios:gerir", "auditoria:ver"},
    "gestor": {"painel:ver", "dados:importar", "dados:excluir", "auditoria:ver"},
    "leitor": {"painel:ver"},
}


def hash_senha(senha: str) -> str:
    return _ph.hash(senha)


def confere_senha(hash_: str | None, senha: str) -> bool:
    if not hash_:
        return False
    try:
        return _ph.verify(hash_, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def abre_sessao(resp: Response, user: User) -> None:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    token = jwt.encode({"sub": str(user.id), "exp": exp}, settings.secret_key, algorithm="HS256")
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                    max_age=settings.session_hours * 3600, path="/")


def fecha_sessao(resp: Response) -> None:
    resp.delete_cookie(COOKIE, path="/")


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sessão ausente")
    try:
        uid = int(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Sessão inválida ou expirada")
    user = db.get(User, uid)
    if not user or not user.ativo:
        raise HTTPException(401, "Usuário inativo")
    return user


def permissoes(user: User) -> set[str]:
    return PAPEIS.get(user.papel, set())


def exige(perm: str):
    def dep(user: User = Depends(usuario_atual)) -> User:
        if perm not in permissoes(user):
            raise HTTPException(403, f"Permissão necessária: {perm}")
        return user
    return dep


def audita(db: Session, user: User | None, acao: str, **detalhe) -> None:
    db.add(Auditoria(usuario_id=user.id if user else None, acao=acao, detalhe=detalhe or None))
