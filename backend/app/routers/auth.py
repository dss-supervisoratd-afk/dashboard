import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User
from ..security import Email, abre_sessao, audita, confere_senha, fecha_sessao, hash_senha, permissoes, usuario_atual

router = APIRouter(prefix="/api/auth", tags=["autenticação"])

oauth = OAuth()
if settings.google_enabled:
    oauth.register(
        "google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# limite simples de tentativas: 8 falhas por email+IP em 15 min
_falhas: dict[str, deque] = defaultdict(deque)
_JANELA, _MAX = 900, 8


def _bloqueado(chave: str) -> bool:
    q = _falhas[chave]
    while q and q[0] < time.time() - _JANELA:
        q.popleft()
    return len(q) >= _MAX


def perfil(u: User) -> dict:
    return {"id": u.id, "email": u.email, "nome": u.nome, "papel": u.papel, "permissoes": sorted(permissoes(u)),
            "tem_senha": bool(u.senha_hash), "google": bool(u.google_sub)}


class Login(BaseModel):
    email: Email
    senha: str


@router.get("/provedores")
def provedores():
    return {"google": settings.google_enabled, "senha": True}


@router.post("/login")
def login(dados: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    email = dados.email.lower()
    chave = f"{email}|{request.client.host if request.client else ''}"
    if _bloqueado(chave):
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    u = db.scalar(select(User).where(User.email == email))
    if not u or not u.ativo or not confere_senha(u.senha_hash, dados.senha):
        _falhas[chave].append(time.time())
        audita(db, u, "login_falhou", email=email)
        db.commit()
        raise HTTPException(401, "Email ou senha inválidos")
    _falhas.pop(chave, None)
    u.ultimo_acesso = datetime.now(timezone.utc)
    audita(db, u, "login", metodo="senha")
    db.commit()
    abre_sessao(response, u)
    return perfil(u)


@router.post("/logout")
def logout(response: Response):
    fecha_sessao(response)
    return {"ok": True}


@router.get("/me")
def me(u: User = Depends(usuario_atual)):
    return perfil(u)


class TrocaSenha(BaseModel):
    atual: str | None = None
    nova: str = Field(min_length=10, max_length=128)


@router.post("/senha")
def troca_senha(dados: TrocaSenha, u: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    if u.senha_hash and not confere_senha(u.senha_hash, dados.atual or ""):
        raise HTTPException(400, "Senha atual incorreta")
    u.senha_hash = hash_senha(dados.nova)
    audita(db, u, "senha_alterada")
    db.commit()
    return {"ok": True}


@router.get("/google/login")
async def google_login(request: Request):
    if not settings.google_enabled:
        raise HTTPException(404, "Login Google não configurado")
    return await oauth.google.authorize_redirect(request, str(request.url_for("google_callback")))


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    destino = settings.frontend_url.rstrip("/")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{destino}/login?erro=oauth")
    info = token.get("userinfo") or {}
    email, sub = (info.get("email") or "").lower(), info.get("sub")
    if not email or not sub or not info.get("email_verified"):
        return RedirectResponse(f"{destino}/login?erro=email_nao_verificado")
    u = db.scalar(select(User).where(User.google_sub == sub)) or db.scalar(select(User).where(User.email == email))
    if not u:
        if email.split("@")[-1] not in settings.allowed_domains:
            audita(db, None, "login_google_negado", email=email)
            db.commit()
            return RedirectResponse(f"{destino}/login?erro=nao_autorizado")
        u = User(email=email, nome=info.get("name") or email, papel=settings.google_default_role)
        db.add(u)
        db.flush()
        audita(db, u, "usuario_criado_google", email=email)
    if not u.ativo:
        return RedirectResponse(f"{destino}/login?erro=inativo")
    u.google_sub = u.google_sub or sub
    u.ultimo_acesso = datetime.now(timezone.utc)
    audita(db, u, "login", metodo="google")
    db.commit()
    resp = RedirectResponse(destino + "/")
    abre_sessao(resp, u)
    return resp
