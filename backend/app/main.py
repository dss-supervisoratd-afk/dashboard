from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, settings
from .db import Base, SessionLocal, engine
from .models import User
from .routers import analytics, auth, imports, users
from .security import audita, hash_senha


def inicializa() -> None:
    if not settings.database_url.startswith("sqlite") and settings.secret_key == Settings.model_fields["secret_key"].default:
        raise RuntimeError("Defina SECRET_KEY (ex.: python -c \"import secrets;print(secrets.token_urlsafe(48))\")")
    # Fase 1: esquema criado direto dos modelos; migrações (Alembic) entram na Fase 2
    Base.metadata.create_all(engine)
    if settings.admin_email and settings.admin_password:
        with SessionLocal() as db:
            if not db.scalar(select(func.count()).select_from(User)):
                u = User(email=settings.admin_email.lower(), nome="Administrador", papel="admin",
                         senha_hash=hash_senha(settings.admin_password))
                db.add(u)
                db.flush()
                audita(db, u, "admin_inicial_criado")
                db.commit()


@asynccontextmanager
async def ciclo(_: FastAPI):
    inicializa()
    yield


app = FastAPI(title="AMN · Gestão Estratégica do Atendimento", lifespan=ciclo,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
# sessão usada apenas pelo fluxo OAuth (state/nonce); a sessão do usuário é o cookie JWT
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="amn_oauth",
                   same_site="lax", https_only=settings.cookie_secure)


@app.middleware("http")
async def csrf(request: Request, call_next):
    """Cookie SameSite=Lax + cabeçalho customizado obrigatório em métodos de escrita:
    formulários de outros sites não conseguem enviá-lo."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and request.headers.get("x-requested-with") != "amn":
        return JSONResponse({"detail": "Cabeçalho X-Requested-With ausente"}, status_code=403)
    return await call_next(request)


for r in (auth.router, users.router, analytics.router, imports.router):
    app.include_router(r)


@app.get("/api/saude")
def saude():
    return {"ok": True}
