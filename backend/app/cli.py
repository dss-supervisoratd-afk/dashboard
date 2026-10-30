"""Comandos de manutenção:

    python -m app.cli criar-admin email@dominio "Nome"        (pede a senha)
    python -m app.cli importar CAMINHO... [--autor email] [--reimportar]

`importar` aceita arquivos e pastas (percorridas recursivamente): painel HTML legado,
PDFs do Novo SGA, cadastro de guichês e planilhas diárias "AAAA.MM.DD …". O cadastro
de guichês é gravado antes dos demais, para os nomes já entrarem resolvidos. Arquivos
que exigem conferência de colunas são listados e ficam para a tela de importação.
Arquivos com mesmo nome e conteúdo de um lote ativo são pulados, salvo com --reimportar.
"""
import getpass
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .importers import servico
from .main import inicializa
from .models import ImportBatch, User
from .security import audita, hash_senha

EXTENSOES = {".pdf", ".xls", ".xlsx", ".xlsm", ".csv", ".html", ".htm"}


def criar_admin(email: str, nome: str) -> None:
    senha = getpass.getpass("Senha (mín. 10 caracteres): ")
    if len(senha) < 10:
        sys.exit("Senha curta demais")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email.lower()))
        if u:
            u.papel, u.ativo, u.senha_hash = "admin", True, hash_senha(senha)
        else:
            u = User(email=email.lower(), nome=nome, papel="admin", senha_hash=hash_senha(senha))
            db.add(u)
        db.flush()
        audita(db, u, "admin_via_cli")
        db.commit()
    print(f"Administrador {email} pronto.")


def _arquivos(caminhos: list[str]) -> list[Path]:
    fs = []
    for c in map(Path, caminhos):
        fs += [f for f in c.rglob("*") if f.is_file()] if c.is_dir() else [c]
    fs = [f for f in fs if f.suffix.lower() in EXTENSOES and not f.name.startswith("~$")]
    # cadastro primeiro; depois em ordem de nome (= ordem cronológica dos diários)
    return sorted(fs, key=lambda f: (not servico.e_cadastro_nome(f.name), f.name))


def importar(caminhos: list[str], autor: str | None, reimportar: bool) -> None:
    cont = {"gravados": 0, "pulados": 0, "conferir": [], "recusados": []}
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == autor.lower())) if autor else None
        ativos = set(db.execute(select(ImportBatch.sha256, ImportBatch.arquivo).where(ImportBatch.status == "ativo")).all())
        for f in _arquivos(caminhos):
            raw = f.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if (sha, f.name) in ativos and not reimportar:
                cont["pulados"] += 1
                continue
            try:
                res = servico.analisa(f.name, raw)
                if not res.get("autoconfiavel"):
                    cont["conferir"].append(f"{f.name} ({res.get('conjunto')}, confiança {res.get('confianca', 0):.0%})")
                    continue
                lote, erros = servico.grava(db, f.name, raw, sha, u.id if u else None)
                audita(db, u, "importacao", lote=lote.id, conjunto=lote.conjunto, arquivo=lote.arquivo,
                       linhas=lote.linhas_carregadas, descartadas=len(erros), via="cli")
                db.commit()
                ativos.add((sha, f.name))
                cont["gravados"] += 1
                print(f"  ok  {f.name}: {lote.conjunto}, {lote.linhas_carregadas} linhas"
                      + (f", {len(erros)} descartadas" if erros else "") + "".join(f" · {a}" for a in lote.avisos[:2]))
            except servico.Recusado as e:
                db.rollback()
                cont["recusados"].append(f"{f.name}: {e}")
    print(f"\n{cont['gravados']} gravado(s), {cont['pulados']} já importado(s).")
    for k, titulo in (("conferir", "Precisam de conferência na tela de importação"), ("recusados", "Recusados")):
        if cont[k]:
            print(f"\n{titulo} ({len(cont[k])}):")
            for x in cont[k]:
                print("  -", x)


if __name__ == "__main__":
    inicializa()
    cmd, *args = sys.argv[1:] or ["ajuda"]
    if cmd == "criar-admin" and len(args) >= 1:
        criar_admin(args[0], args[1] if len(args) > 1 else "Administrador")
    elif cmd == "importar" and args:
        autor = args[args.index("--autor") + 1] if "--autor" in args else None
        caminhos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--autor")]
        importar(caminhos, autor, "--reimportar" in args)
    else:
        print(__doc__)
