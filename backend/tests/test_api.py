import json

import pytest

from app.importers.readers import extrai_raw_legado
from conftest import H, LEGADO, entra


def q(c, conjunto, medidas, dims=(), **kw):
    r = c.post("/api/bi/consulta", json={"conjunto": conjunto, "medidas": list(medidas), "dims": list(dims), **kw}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["linhas"]


def test_totais_batem_com_o_painel_legado(admin, legado):
    raw = extrai_raw_legado(LEGADO.read_bytes())
    dias = raw["dias"]
    ouv = sum(n for d in dias for *_, n in d["ouv"])
    atd = sum(len(d["atd"]) for d in dias)
    svc = sum(n for d in dias if d["svc"] for _, n in d["svc"]["itens"])
    tma = [r for d in dias for r in d["tma"]]
    tme = sum(r[2] * r[1] for r in tma if r[2] is not None) / sum(r[1] for r in tma if r[2] is not None)

    assert q(admin, "ouvidoria", ["mensagens"]) == [[ouv]]
    assert q(admin, "atendimentos", ["atendimentos"]) == [[atd]]
    assert q(admin, "servicos", ["servicos"]) == [[svc]]
    assert q(admin, "tempos", ["tme"])[0][0] == pytest.approx(tme)


def test_meta_e_filtros_cruzados(admin, legado):
    m = admin.get("/api/bi/meta").json()
    assert not m["vazio"] and m["de"] == "2026-01-01" and m["parcial"] == m["meses"][-1]
    assert "Fim de semana" in dict(m["tipos"])
    setor = m["setores"][0]
    so = q(admin, "ouvidoria", ["mensagens"], ["setor"], filtros={"setor": setor})
    assert [r[0] for r in so] == [setor]
    # o filtro de setor não afeta conjuntos sem setor
    assert q(admin, "atendimentos", ["atendimentos"], filtros={"setor": setor}) == q(admin, "atendimentos", ["atendimentos"])
    # ignorar mantém a lista completa de setores com um setor selecionado
    assert len(q(admin, "ouvidoria", ["mensagens"], ["setor"], filtros={"setor": setor}, ignorar=["setor"])) == len(m["setores"])


def test_semantica_rejeita_campos_desconhecidos(admin):
    r = admin.post("/api/bi/consulta", json={"conjunto": "ouvidoria", "medidas": ["mensagens; drop table x"]}, headers=H)
    assert r.status_code == 422


def test_importacao_csv_idempotente_e_reversao(admin, legado):
    csv = "data;setor;subsetor;qtd\n05/01/2026;TESTE SETOR;SUB A;3\n05/01/2026;TESTE SETOR;SUB B;2\n"
    antes = q(admin, "ouvidoria", ["mensagens"], filtros={"de": "2026-01-05", "ate": "2026-01-05"})[0][0]

    def importa():
        r = admin.post("/api/importacoes/analisar", files={"arquivo": ("ouvidoria_teste.csv", csv.encode(), "text/csv")}, headers=H)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["conjunto"] == "ouvidoria" and a["validacao"]["validas"] == 2
        return admin.post(f"/api/importacoes/{a['envio']}/confirmar", json={}, headers=H).json()["lote"], a

    lote, _ = importa()
    dia = lambda: q(admin, "ouvidoria", ["mensagens"], filtros={"de": "2026-01-05", "ate": "2026-01-05"})  # noqa: E731
    assert dia() == [[5]]  # o arquivo substitui o dia inteiro do conjunto
    lote2, a2 = importa()
    assert a2["duplicado"]["lote"] == lote["id"]
    assert dia() == [[5]]  # reimportar não duplica
    assert antes != 5
    r = admin.delete(f"/api/importacoes/{lote2['id']}", headers=H)
    assert r.json()["removidas"] == 2
    assert dia() == [[None]]


def test_modelos(admin):
    r = admin.get("/api/importacoes/modelos/tempos.csv")
    assert r.status_code == 200 and r.text.lstrip("﻿").startswith("data;atendente;n;tme")
    assert admin.get("/api/importacoes/modelos/ouvidoria.xlsx").status_code == 200


def test_rbac_csrf_e_ultimo_admin(client):
    entra(client)
    assert client.post("/api/auth/logout").status_code == 403  # sem cabeçalho anti-CSRF
    r = client.post("/api/usuarios", json={"email": "leitor@teste.local", "nome": "Leitor", "papel": "leitor",
                                           "senha": "senha-leitor-1"}, headers=H)
    assert r.status_code == 201, r.text
    admin_id = client.get("/api/auth/me").json()["id"]
    assert client.patch(f"/api/usuarios/{admin_id}", json={"papel": "gestor"}, headers=H).status_code == 400

    me = entra(client, "leitor@teste.local", "senha-leitor-1")
    assert me["permissoes"] == ["painel:ver"]
    assert client.get("/api/bi/meta").status_code == 200
    assert client.get("/api/usuarios").status_code == 403
    r = client.post("/api/importacoes/analisar", files={"arquivo": ("x.csv", b"a;b\n1;2\n", "text/csv")}, headers=H)
    assert r.status_code == 403

    client.cookies.clear()
    assert client.get("/api/bi/meta").status_code == 401
    assert client.post("/api/auth/login", json={"email": "leitor@teste.local", "senha": "errada-123"}, headers=H).status_code == 401
    entra(client)  # devolve a sessão de admin às demais fixtures


def test_auditoria_registra(admin, legado):
    entra(admin)
    acoes = {a["acao"] for a in admin.get("/api/auditoria").json()}
    assert {"login", "login_falhou", "importacao", "importacao_revertida", "usuario_criado"} <= acoes
    lotes = admin.get("/api/importacoes").json()
    assert json.dumps(lotes) and {b["status"] for b in lotes} == {"ativo", "revertido"}


def _importa(c, nome, conteudo: bytes):
    r = c.post("/api/importacoes/analisar", files={"arquivo": (nome, conteudo, "application/octet-stream")}, headers=H)
    assert r.status_code == 200, r.text
    a = r.json()
    return a, c.post(f"/api/importacoes/{a['envio']}/confirmar", json={}, headers=H)


def test_diarios_de_ouvidoria_dia_pelo_nome_e_dia_vazio(admin, legado):
    entra(admin)
    corpo = "Setor;SubSetor;Mensagens\nTESTE DIARIO;SUB;1\n".encode()
    a1, r1 = _importa(admin, "2026.03.10 - Normal - Ouvidorias.csv", corpo)
    assert a1["autoconfiavel"] and a1["validacao"]["de"] == "2026-03-10" and r1.status_code == 200
    # mesmo conteúdo, outro dia: não é duplicata (a data está no nome)
    a2, r2 = _importa(admin, "2026.03.11 - Normal - Ouvidorias.csv", corpo)
    assert a2["duplicado"] is None and r2.status_code == 200
    assert q(admin, "ouvidoria", ["mensagens"], filtros={"de": "2026-03-10", "ate": "2026-03-11", "setor": "TESTE DIARIO"}) == [[2]]
    # só cabeçalho = dia sem mensagens: zera o dia em vez de manter o dado anterior
    a3, r3 = _importa(admin, "2026.03.11 - Feriado - Ouvidorias.csv", b"Setor;SubSetor;Mensagens\n")
    assert a3["dia_vazio"] and a3["autoconfiavel"] and r3.status_code == 200
    assert q(admin, "ouvidoria", ["mensagens"], filtros={"de": "2026-03-11", "ate": "2026-03-11"}) == [[None]]
    assert q(admin, "calendario", ["dias"], ["tipo_dia"], filtros={"de": "2026-03-11", "ate": "2026-03-11"}) == [["Feriado", 1]]


def test_login_vira_nome_do_tma(admin, legado):
    entra(admin)
    _, r = _importa(admin, "tempos.csv", "data;atendente;n;tme\n12/03/2026;João Teste;2;00:01:00\n".encode())
    assert r.status_code == 200
    _, r = _importa(admin, "atend.csv", "data;hora;servico;atendente\n12/03/2026;9;Assim;joao.teste\n13/03/2026;9;Assim;maria.sem.par\n".encode())
    assert r.status_code == 200
    nomes = {x[0] for x in q(admin, "atendimentos", ["atendimentos"], ["atendente"], filtros={"de": "2026-03-12", "ate": "2026-03-13"})}
    assert nomes == {"João Teste", "Maria Sem Par"}
