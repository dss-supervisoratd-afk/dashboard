import io

from openpyxl import Workbook

from app.importers.readers import le
from app.importers.recognize import analisa, converte, separa


def _xlsx(linhas):
    wb = Workbook()
    for r in linhas:
        wb.active.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_csv_ouvidoria_com_titulo_e_ponto_e_virgula():
    csv = ("Relatório de Ouvidorias - Janeiro\n\n"
           "Data de abertura;Área;Convênio;Protocolo\n"
           "02/01/2026;PLANOS DE SAÚDE E ODONTOLÓGICOS;UNIMED NACIONAL;123\n"
           "02/01/2026;AMN;CONVÊNIOS;124\n"
           "03/01/2026;AMN;DESCONTOS;125\n").encode("cp1252")
    abas = le("relatorio.csv", csv)
    r = analisa("relatorio.csv", abas)
    assert r["conjunto"] == "ouvidoria"
    assert r["linha_cabecalho"] == 3  # título, linha em branco, cabeçalho
    cols = r["colunas"]
    assert cols[r["mapeamento"]["data"]] == "Data de abertura"
    assert cols[r["mapeamento"]["setor"]] == "Área"
    assert cols[r["mapeamento"]["subsetor"]] == "Convênio"
    assert "qtd" not in r["mapeamento"]  # protocolo não é quantidade


def test_xlsx_tempos_por_atendente():
    raw = _xlsx([["Atendente", "Data", "Atendimentos", "TME", "TMD", "TMA"],
                 ["Danielle Martins", "02/01/2026", 1, "00:00:23", "00:00:06", "00:00:07"],
                 ["Marta (MAPMA) — guiche 11", "02/01/2026", 2, "00:06:02", "00:06:05", "00:31:10"]])
    r = analisa("TMA_jan.xlsx", le("TMA_jan.xlsx", raw))
    assert r["conjunto"] == "tempos"
    _, dados, nums, _ = separa(le("TMA_jan.xlsx", raw)[0]["linhas"])
    regs, erros = converte("tempos", dados, r["mapeamento"], r["unidades"], nums)
    assert not erros
    assert regs[1]["tma"] == 1870 and regs[1]["n"] == 2


def test_atendimentos_deriva_data_e_hora_de_data_hora():
    raw = _xlsx([["Senha", "Início da chamada", "Serviço triado", "Atendente", "Duração"],
                 ["A001", "02/01/2026 09:12:00", "Sulamérica", "Danielle Martins", "00:00:07"],
                 ["A002", "02/01/2026 10:40:00", "Seguro Auto(Novo/Renovação)", "Marta", "00:30:20"],
                 ["Total", "", "", "", ""]])
    abas = le("Atendimentos Concluidos.xlsx", raw)
    r = analisa("Atendimentos Concluidos.xlsx", abas)
    assert r["conjunto"] == "atendimentos"
    _, dados, nums, _ = separa(abas[0]["linhas"])
    regs, erros = converte("atendimentos", dados, r["mapeamento"], r["unidades"], nums)
    assert [x["hora"] for x in regs] == [9, 10]
    assert regs[0]["data"].isoformat() == "2026-01-02"
    assert len(erros) == 1 and erros[0]["linha"] == 4  # linha de total descartada e relatada


def test_duracao_numerica_em_minutos_gera_aviso():
    raw = _xlsx([["Data", "Atendente", "Qtd", "TME"], ["02/01/2026", "Ana", 3, 6.5], ["02/01/2026", "Bia", 2, 4.25]])
    r = analisa("tempos.xlsx", le("tempos.xlsx", raw))
    assert r["conjunto"] == "tempos" and r["unidades"]["tme"] == "min"
    assert any("tme" in a for a in r["avisos"])


def test_abreviacao_e_numero_de_linha_real():
    raw = _xlsx([["SGA — Relatório de Tempo Médio por Atendente"], [None],
                 ["Usuário", "Dia", "Qtde", "T.M. Espera", "T.M. Atendimento"],
                 ["Ana", "26/10/2026", 12, "00:06:30", "00:11:12"],
                 [None], ["Bia", "26/10/2026", 9, "00:04:15", "00:09:48"],
                 ["Total geral", None, 21, None, None]])
    abas = le("relatorio.xlsx", raw)
    r = analisa("relatorio.xlsx", abas)
    assert r["conjunto"] == "tempos" and r["linha_cabecalho"] == 3
    assert r["colunas"][r["mapeamento"]["tme"]] == "T.M. Espera"
    assert r["colunas"][r["mapeamento"]["tma"]] == "T.M. Atendimento"
    _, dados, nums, _ = separa(abas[0]["linhas"])
    regs, erros = converte("tempos", dados, r["mapeamento"], r["unidades"], nums)
    assert len(regs) == 2 and [e["linha"] for e in erros] == [7]
