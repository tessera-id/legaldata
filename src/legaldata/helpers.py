def format_cnj(digits: str) -> str:
    n = digits[0:7]
    d = digits[7:9]
    a = digits[9:13]
    j = digits[13]
    tt = digits[14:16]   # mantém 2 dígitos: "04", "16", "24"
    o = digits[16:20]
    return f"{n}-{d}.{a}.{j}.{tt}.{o}"


def safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_date(val: str | None) -> str | None:
    """Aceita ISO (YYYY-MM-DD...) ou compacto (YYYYMMDD...)."""
    if not val:
        return None
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-":        # ISO: 2021-12-22T10:...
        return s[:10]
    if len(s) >= 8 and s[:8].isdigit():     # compacto: 20211222...
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def parse_datetime(val: str | None) -> str | None:
    """Aceita ISO (YYYY-MM-DDTHH:MM:SS) ou compacto (YYYYMMDDHHMMSS)."""
    if not val:
        return None
    s = str(val).strip()
    if len(s) >= 19 and s[4] == "-":        # ISO
        return s[:19]
    if len(s) >= 14 and s[:14].isdigit():   # compacto: 20211222103045
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}"
    return None
