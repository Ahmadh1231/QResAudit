from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qresaudit.units import RECOGNIZED_FIELD_UNITS

PARSER_VERSION = "0.1.0"


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
    coordinate_scale: float = 1.0,
) -> ParsedField:
    """Parse whitespace/comma-delimited AEDT-like field data.

    Accepted numeric layouts are x y z value, x y z re im,
    x y z vx vy vz, and x y z re_vx im_vx re_vy im_vy re_vz im_vz.
    Comment headers may define ``quantity`` and ``units``.
    """
    headers: list[str] = []
    rows: list[list[float]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in "#!%":
            headers.append(stripped)
            continue
        normalized = stripped.replace(",", " ").replace("(", " ").replace(")", " ")
        try:
            rows.append([float(token) for token in normalized.split()])
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
    array = np.asarray(rows, dtype=np.float64)
    coordinates = np.asarray(array[:, :3] * coordinate_scale, dtype=np.float64)
    if width == 4:
        values = array[:, 3].astype(np.complex128)
        is_vector, is_complex = False, False
    elif width == 5:
        values = array[:, 3] + 1j * array[:, 4]
        is_vector, is_complex = False, True
    elif width == 6:
        values = array[:, 3:6].astype(np.complex128)
        is_vector, is_complex = True, False
    else:
        values = array[:, 3::2] + 1j * array[:, 4::2]
        is_vector, is_complex = True, True
    metadata = _header_metadata(headers)
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
