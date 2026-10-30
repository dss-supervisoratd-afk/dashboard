from datetime import date, datetime, time, timedelta

import pytest

from app.importers.parse import compativel, data, datahora, duracao, hora, inteiro, norm


def test_norm():
    assert norm("  Serviço  Triado ") == "servico triado"
    assert norm("TMÉ (min)") == "tme min"


@pytest.mark.parametrize("v,esperado", [
    ("05/03/2026", date(2026, 3, 5)), ("2026-03-05", date(2026, 3, 5)), ("5/3/26", date(2026, 3, 5)),
    ("05/03/2026 14:22", date(2026, 3, 5)), (datetime(2026, 3, 5, 9), date(2026, 3, 5)), (46086, date(2026, 3, 5)),
])
def test_data(v, esperado):
    assert data(v) == esperado


def test_datahora_hora():
    assert datahora("05/03/2026 14:22:10") == datetime(2026, 3, 5, 14, 22, 10)
    assert hora("09") == 9 and hora("14h") == 14 and hora("08:45") == 8 and hora(time(17, 5)) == 17
    with pytest.raises(ValueError):
        hora("31")


@pytest.mark.parametrize("v,un,seg", [
    ("00:12:30", "s", 750), ("12:30", "s", 750), (timedelta(minutes=2), "s", 120), (time(0, 1, 5), "s", 65),
    (90, "s", 90), (1.5, "min", 90), ("1h 2min 3s", "s", 3723), ("7,5", "min", 450),
])
def test_duracao(v, un, seg):
    assert duracao(v, un) == seg


def test_inteiro():
    assert inteiro("1.234") == 1234 and inteiro("12,0") == 12 and inteiro(3.0) == 3


def test_compativel():
    assert compativel("data", ["01/01/2026", "02/01/2026", "x"]) == pytest.approx(2 / 3)
    assert compativel("texto", ["Vida", "123"]) == 0.5
