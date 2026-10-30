import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="amn-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["ADMIN_EMAIL"] = "admin@teste.local"
os.environ["ADMIN_PASSWORD"] = "senha-admin-123"
os.environ["SECRET_KEY"] = "chave-de-teste-com-mais-de-32-bytes-ok"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

LEGADO = Path(__file__).resolve().parents[2] / ".resources" / "Painel de Atendimento.html"
H = {"X-Requested-With": "amn"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def entra(c: TestClient, email="admin@teste.local", senha="senha-admin-123"):
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"email": email, "senha": senha}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def admin(client):
    entra(client)
    return client


@pytest.fixture(scope="session")
def legado(admin):
    if not LEGADO.exists():
        pytest.skip("painel legado ausente em .resources/")
    with LEGADO.open("rb") as f:
        r = admin.post("/api/importacoes/analisar", files={"arquivo": (LEGADO.name, f, "text/html")}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["tipo_arquivo"] == "legado"
    r = admin.post(f"/api/importacoes/{r.json()['envio']}/confirmar", json={}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["lote"]
