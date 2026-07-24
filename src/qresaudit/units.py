import re

_UNIT_FACTORS = {
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
    "K": 1.0,
    "mK": 1e-3,
}
RECOGNIZED_FIELD_UNITS = {"V/m", "A/m", "T"}
RECOGNIZED_COORDINATE_UNITS = {"m"}


def parse_quantity(value: str) -> tuple[float, str]:
    match = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]+)\s*",
        value,
    )
    if not match:
        raise ValueError(f"invalid dimensional value: {value!r}")
    number, unit = match.groups()
    if unit not in _UNIT_FACTORS:
        raise ValueError(f"unknown unit: {unit}")
    return float(number) * _UNIT_FACTORS[unit], unit


def convert_to_si(value: str) -> float:
    return parse_quantity(value)[0]


def canonical_variation(values: dict[str, str]) -> str:
    return ";".join(f"{name}={values[name]}" for name in sorted(values))
