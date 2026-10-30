"""Leitores das fontes reais (formato do Novo SGA v2.1.9), com conteúdo sintético."""
import io
from datetime import date

from openpyxl import Workbook

from app.importers.sga import (Ocupacao, atendimentos_das_tabelas, e_consolidado_protocolos, identifica,
                               le_cadastro_guiches, meta_nome, origem_de, resolvedor, rotulo, servicos_do_texto,
                               tempos_do_texto)

TMA = """Imprimir
Tempos médios por Atendente
Abrigo do Marinheiro
Período de 02/09/2026 a 02/09/2026
Usuário Atendimentos TME TMD TMA Tempo total
Fulano de Tal 6 00:02:47 00:12:41 00:08:51 00:24:20
guiche 18 9 00:16:46 00:10:36 00:00:04 00:27:28
sala 01 3 00:05:20 02:08:51 00:00:04 02:14:15
sala 7 2 00:00:10 00:00:10 00:00:10 00:00:30
18 00:57:13 08:12:17 04:04:30 09:07:53
Legenda
TME: Tempo médio de espera
Tempos médios por Atendente - Novo SGA v2.1.9"""

SVC = """Imprimir
Serviços executados
Abrigo do Marinheiro
Período de 02/09/2026 a 02/09/2026
Serviço Total
Seguro Auto(Novo/Renovação) 4
Unimed Ferj 13
Total: 17
Serviços executados - Novo SGA v2.1.9"""


def test_nome_do_arquivo():
    assert meta_nome("2026.10.01 - Normal - Ouvidorias.xls") == (date(2026, 10, 1), "Normal")
    assert meta_nome("2026.09.07 - Feriado - Serviços executados.pdf") == (date(2026, 9, 7), "Feriado")
    assert meta_nome("2026.06.04 - Fechou 15h- Atendimentos concluídos.pdf") == (date(2026, 6, 4), "Fechou 15h")
    assert meta_nome("2026.09.02 Ouvidorias.xls") == (date(2026, 9, 2), None)
    assert meta_nome("Relatório Executivo 2026.09.pdf") == (None, None)


def test_identifica_e_tempos():
    assert identifica(TMA) == ("tempos", date(2026, 9, 2), date(2026, 9, 2))
    regs, _ = tempos_do_texto(TMA, date(2026, 9, 2))
    assert [r["atendente_origem"] for r in regs] == ["Fulano de Tal", "guiche 18", "sala 1"]  # sala 7 (CPD) e total fora
    assert regs[1]["n"] == 9 and regs[1]["tme"] == 1006 and regs[1]["tot"] == 1648


def test_servicos_confere_total():
    regs, avisos = servicos_do_texto(SVC, date(2026, 9, 2))
    assert [(r["servico"], r["qtd"]) for r in regs] == [("Seguro Auto(Novo/Renovação)", 4), ("Unimed Ferj", 13)]
    assert not avisos
    _, avisos = servicos_do_texto(SVC.replace("Total: 17", "Total: 20"), date(2026, 9, 2))
    assert avisos


def test_atendimentos_em_blocos():
    cab = ["Senha", "Data", "Chamada", "Início", "Fim", "Duração", "Permanência", "Serviço Triado", "Atendente"]
    vazio = [None] * 9
    t = [cab,
         ["UNC1", "02/09/2026", "08:23:36", "08:23:45", "10:16:30", "01:52:45", "01:56:10", "Unimed Nacional", "guiche23"],
         [None, "Observação:"] + [None] * 7, [None, "Serviços realizados"] + [None] * 7, [None, "Unimed Ferj"] + [None] * 7, vazio,
         ["SEG2", "02/09/2026", "13:05:00", "13:06:00", "13:20:00", "00:14:00", "00:15:00", "Seguro Auto(Novo/\nRenovação)", "sala01"]]
    regs, avisos = atendimentos_das_tabelas([t])
    assert len(regs) == 2 and not avisos
    assert regs[0] == {"data": date(2026, 9, 2), "hora": 8, "servico": "Unimed Nacional", "atendente_origem": "guiche 23",
                       "atendente": "guiche 23", "dur": 6765, "perm": 6970}
    assert regs[1]["servico"] == "Seguro Auto(Novo/Renovação)" and regs[1]["atendente_origem"] == "sala 1"


def test_rotulos_e_resolucao_por_vigencia():
    assert rotulo("guiche023") == "guiche 23" and rotulo(" Fulano  de Tal ") == "Fulano de Tal"
    assert origem_de("Marta (MAPMA) — guiche 11") == "guiche 11" and origem_de("Davi Pontes") is None
    cad = [Ocupacao("guiche", 18, "Aline", "MAPMA", date(2026, 6, 1), None),
           Ocupacao("guiche", 16, "Ana", "QV", None, date(2026, 5, 31)), Ocupacao("guiche", 16, "Bia", "MAG", date(2026, 6, 1), None),
           Ocupacao("sala", 1, "AMN", "AMN", None, None)]
    r = resolvedor(cad)
    assert r("guiche 18", date(2026, 1, 5)) == "Aline (MAPMA) — guiche 18"  # mesma pessoa: vale para todo o histórico
    assert r("guiche 16", date(2026, 5, 2)) == "Ana (QV) — guiche 16"
    assert r("guiche 16", date(2026, 7, 2)) == "Bia (MAG) — guiche 16"
    assert r("sala 1", date(2026, 7, 2)) == "AMN (AMN) — sala 1"
    assert r("guiche 99", date(2026, 7, 2)) == "guiche 99"


def test_cadastro_de_guiches_e_consolidado():
    wb = Workbook()
    g = wb.active
    g.title = "Guichês"
    g.append(["Guichê", "Grupo/Empresa", "Atendente", "Convênios/Serviços atendidos", "Vigência início", "Vigência fim", "Observações"])
    g.append([1, "MAPMA", "Fulana", "Vida", "01/06/2026", None, None])
    s = wb.create_sheet("Salas (supervisores)")
    s.append(["Sala", "Supervisor(a)", "Empresa", "Serviços", "Observação"])
    s.append(["sala1 / sala01", "AMN", "AMN", "Gerência", None])
    b = io.BytesIO()
    wb.save(b)
    cad = le_cadastro_guiches(b.getvalue())
    assert cad == [Ocupacao("guiche", 1, "Fulana", "MAPMA", date(2026, 6, 1), None), Ocupacao("sala", 1, "AMN", "AMN", None, None)]
    assert le_cadastro_guiches(b"nao e xlsx") is None
    assert e_consolidado_protocolos(["Protocolo", "Assunto", "Nome", "Setor", "Subsetor", "DataCadastro", "Situacao"])
    assert not e_consolidado_protocolos(["Setor", "SubSetor", "Mensagens"])
