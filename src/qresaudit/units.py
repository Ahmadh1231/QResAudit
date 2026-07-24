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
RECOGNIZED_COORDINATE_UNITS = {"m", "cm", "mm", "um", "nm"}

FIELD_QUANTITY_REGISTRY: dict[str, tuple[bool, str]] = {
    "E": (True, "V/m"),
    "H": (True, "A/m"),
    "B": (True, "T"),
    "J": (True, "A/m^2"),
    "SURFACE_CURRENT": (True, "A/m"),
    "POYNTING": (True, "W/m^2"),
    "ENERGY_DENSITY": (False, "J/m^3"),
}
RECOGNIZED_FIELD_UNITS.update(value[1] for value in FIELD_QUANTITY_REGISTRY.values())


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


def canonical_si_unit(unit: str) -> str:
    if unit in {"m", "cm", "mm", "um", "nm"}:
        return "m"
    if unit in {"Hz", "kHz", "MHz", "GHz"}:
        return "Hz"
    if unit in {"K", "mK"}:
        return "K"
    raise ValueError(f"unknown unit: {unit}")


def unit_factor(unit: str) -> float:
    try:
        return _UNIT_FACTORS[unit]
    except KeyError as exc:
        raise ValueError(f"unknown unit: {unit}") from exc


def field_quantity_contract(
    quantity: str,
    *,
    vector: bool,
    explicit_units: str | None,
) -> tuple[str, bool, str]:
    canonical = quantity.strip().upper().replace(" ", "_")
    registered = FIELD_QUANTITY_REGISTRY.get(canonical)
    if registered is None:
        if not explicit_units:
            raise ValueError(f"custom field quantity {quantity!r} requires explicit value_units")
        return quantity, vector, explicit_units
    expected_vector, units = registered
    if vector != expected_vector:
        raise ValueError(
            f"field quantity {quantity!r} requires vector={expected_vector}, got {vector}"
        )
    if explicit_units is not None and explicit_units != units:
        raise ValueError(
            f"field quantity {quantity!r} requires units {units!r}, got {explicit_units!r}"
        )
    return canonical, expected_vector, units


def canonical_variation(values: dict[str, str]) -> str:
    return ";".join(f"{name}={values[name]}" for name in sorted(values))
