from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qresaudit.units import (
    RECOGNIZED_COORDINATE_UNITS,
    RECOGNIZED_FIELD_UNITS,
    unit_factor,
)

PARSER_VERSION = "0.1.1"


@dataclass(frozen=True)
class ParsedField:
    coordinates_m: NDArray[np.float64]
    values: NDArray[np.complex128]
    is_complex: bool
    is_vector: bool
    quantity: str
    value_units: str
    coordinate_units: str
    source_header: tuple[str, ...]


def _header_metadata(headers: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in headers:
        stripped = line.lstrip("#!% \t")
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            metadata[key.strip().lower()] = value.strip()
    return metadata


def parse_field_tab(
    path: Path,
    *,
    quantity: str | None = None,
    value_units: str | None = None,
    coordinate_units: str | None = None,
    coordinate_scale: float | None = None,
) -> ParsedField:
    """Parse whitespace/comma-delimited AEDT-like field data.

    Accepted numeric layouts are x y z value, x y z re im,
    x y z vx vy vz, and x y z re_vx im_vx re_vy im_vy re_vz im_vz.
    Comment headers may define ``quantity`` and ``units``.
    """
    headers: list[str] = []
    rows: list[list[complex]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in "#!%":
            headers.append(stripped)
            continue
        normalized = stripped.replace(",", " ").replace("(", " ").replace(")", " ")
        try:
            rows.append([complex(token.lower().replace("i", "j")) for token in normalized.split()])
        except ValueError:
            if not rows:
                headers.append(stripped)
                continue
            raise ValueError(f"non-numeric field row at line {line_number}") from None
    if not rows:
        raise ValueError("field export contains no numeric rows")
    widths = {len(row) for row in rows}
    if len(widths) != 1:
        raise ValueError("field rows have inconsistent column counts")
    width = widths.pop()
    if width not in {4, 5, 6, 9}:
        raise ValueError(f"unsupported field column count: {width}")
    array = np.asarray(rows, dtype=np.complex128)
    if np.any(np.imag(array[:, :3]) != 0):
        raise ValueError("field coordinates must be real")
    metadata = _header_metadata(headers)
    source_coordinate_units = (
        metadata.get("coordinate_units")
        or metadata.get("coordinate units")
        or metadata.get("length_units")
        or coordinate_units
    )
    if coordinate_scale is None:
        if source_coordinate_units not in RECOGNIZED_COORDINATE_UNITS:
            raise ValueError("field coordinate units are absent or unsupported")
        coordinate_scale = unit_factor(source_coordinate_units)
    coordinates = np.asarray(np.real(array[:, :3]) * coordinate_scale, dtype=np.float64)
    if len({tuple(point) for point in coordinates}) != len(coordinates):
        raise ValueError("field export contains duplicate coordinates")
    if width == 4:
        values = array[:, 3]
        is_vector, is_complex = False, bool(np.any(np.imag(values) != 0))
    elif width == 5:
        values = np.real(array[:, 3]) + 1j * np.real(array[:, 4])
        is_vector, is_complex = False, True
    elif width == 6:
        values = array[:, 3:6]
        is_vector, is_complex = True, bool(np.any(np.imag(values) != 0))
    else:
        values = np.real(array[:, 3::2]) + 1j * np.real(array[:, 4::2])
        is_vector, is_complex = True, True
    if not np.all(np.isfinite(coordinates)) or not np.all(np.isfinite(values)):
        raise ValueError("field export contains nonfinite values")
    parsed_quantity = quantity or metadata.get("quantity", "")
    parsed_units = value_units or metadata.get("units", "")
    if parsed_units and parsed_units not in RECOGNIZED_FIELD_UNITS:
        raise ValueError(f"unknown field unit: {parsed_units}")
    return ParsedField(
        coordinates_m=coordinates,
        values=np.asarray(values, dtype=np.complex128),
        is_complex=is_complex,
        is_vector=is_vector,
        quantity=parsed_quantity,
        value_units=parsed_units,
        coordinate_units="m",
        source_header=tuple(headers),
    )
