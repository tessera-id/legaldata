import re
import tomllib
from pathlib import Path

_TOML = tomllib.loads((Path(__file__).parent / "tribunais.toml").read_text(encoding="utf-8"))

_ESTADUAL    = _TOML["estadual"]
_TRABALHISTA = _TOML["trabalhista"]
_FEDERAL_TRF = _TOML["federal"]["trf"]


def parse_cnj(numero: str) -> tuple[str, str]:
    clean = re.split(r"[\s(]", numero.strip())[0]
    digits = re.sub(r"\D", "", clean)

    if len(digits) != 20:
        raise ValueError(
            f"Número CNJ deve ter 20 dígitos, encontrado {len(digits)}: '{numero}'"
        )

    j    = digits[13]
    tt   = digits[14:16]
    oooo = digits[16:20]
    key  = f"{j}.{tt}"

    if j == "8":
        if key not in _ESTADUAL:
            raise ValueError(f"Tribunal estadual não suportado: {key} em '{numero}'")
        return digits, _ESTADUAL[key]

    if j == "5":
        if key not in _TRABALHISTA:
            raise ValueError(f"Tribunal trabalhista não suportado: {key} em '{numero}'")
        return digits, _TRABALHISTA[key]

    if j == "4":
        if key not in _FEDERAL_TRF:
            raise ValueError(f"Região federal não suportada: {key} em '{numero}'")
        return digits, _FEDERAL_TRF[key]

    raise ValueError(f"Segmento J={j} não suportado em '{numero}'")
