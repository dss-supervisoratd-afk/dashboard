"""Conversão tolerante de valores vindos de CSV/XLSX/PDF (formatos pt-BR e ISO)."""
import re
import unicodedata
from datetime import date, datetime, time, timedelta

_EXCEL_EPOCH = datetime(1899, 12, 30)


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def texto(v) -> str:
    if vazio(v):
        raise ValueError("vazio")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


_DT = re.compile(r"^(\d{1,4})[/.-](\d{1,2})[/.-](\d{1,4})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?")


def datahora(v) -> datetime:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # número de série do Excel
        return _EXCEL_EPOCH + timedelta(days=float(v))
    m = _DT.match(str(v).strip()) if not vazio(v) else None
    if not m:
        raise ValueError("data não reconhecida")
    a, b, c, hh, mi, ss = m.groups()
    if len(a) == 4:
        y, mo, d = int(a), int(b), int(c)
    else:  # dd/mm/aaaa (pt-BR)
        d, mo, y = int(a), int(b), int(c)
        if y < 100:
            y += 2000
    return datetime(y, mo, d, int(hh or 0), int(mi or 0), int(ss or 0))


def data(v) -> date:
    return datahora(v).date()


def hora(v) -> int:
    if isinstance(v, (datetime, time)):
        return v.hour
    if isinstance(v, float) and 0 <= v < 1:  # fração de dia do Excel
        return int(v * 24)
    s = str(v).strip().lower()
    m = re.match(r"^(\d{1,2})\s*(?:h|:|$)", s)
    if not m or not 0 <= int(m.group(1)) <= 23:
        raise ValueError("hora inválida")
    return int(m.group(1))


def inteiro(v) -> int:
    if isinstance(v, bool):
        raise ValueError("booleano")
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # milhar pt-BR
        s = s.replace(".", "")
    return int(round(float(s.replace(",", "."))))


def duracao(v, unidade: str = "s") -> float:
    """Segundos. Aceita hh:mm:ss, mm:ss, timedelta/time, '5min', '1h 2min 3s' e números
    (interpretados na unidade informada: s ou min)."""
    if isinstance(v, timedelta):
        return v.total_seconds()
    if isinstance(v, time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, datetime):  # Excel às vezes entrega 1899-12-30 hh:mm:ss
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, (int, float)):
        return float(v) * (60 if unidade == "min" else 1)
    s = str(v).strip().lower()
    if re.fullmatch(r"-?\d+:\d{1,2}(:\d{1,2})?", s):
        p = [int(x) for x in s.split(":")]
        return float(p[0] * 3600 + p[1] * 60 + p[2]) if len(p) == 3 else float(p[0] * 60 + p[1])
    partes = re.findall(r"(\d+(?:[.,]\d+)?)\s*(h|min|m|s)", s)
    if partes:
        mult = {"h": 3600, "min": 60, "m": 60, "s": 1}
        return sum(float(n.replace(",", ".")) * mult[u] for n, u in partes)
    return float(s.replace(",", ".")) * (60 if unidade == "min" else 1)


CONVERSORES = {"data": data, "datahora": datahora, "hora": hora, "inteiro": inteiro, "texto": texto, "duracao": duracao}


def compativel(tipo: str, valores: list) -> float:
    """Fração dos valores não vazios que convertem no tipo (0–1)."""
    vs = [v for v in valores if not vazio(v)]
    if not vs:
        return 0.0
    conv, ok = CONVERSORES[tipo], 0
    for v in vs:
        try:
            r = conv(v)
            if tipo == "texto" and re.fullmatch(r"[\d.,:/ -]+", str(r)):
                continue  # número/data puro não é rótulo de texto
            ok += 1
        except (ValueError, TypeError, OverflowError):
            pass
    return ok / len(vs)
