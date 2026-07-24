from pathlib import Path

import numpy as np
import pytest

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import read_field_hdf5, source_metadata, write_field_hdf5


def test_complex_vector_field_round_trip(tmp_path: Path) -> None:
    raw = tmp_path / "field.fld"
    raw.write_text(
        "# quantity: H\n# units: A/m\n0 0 0 1 2 3 4 5 6\n1 0 0 2 3 4 5 6 7\n",
        encoding="utf-8",
    )
    parsed = parse_field_tab(raw, coordinate_units="m")
    assert parsed.is_vector and parsed.is_complex
    target = write_field_hdf5(
        tmp_path / "field.h5",
        parsed,
        {"normalization": "driven_excitation_dependent", **source_metadata(raw)},
    )
    coordinates, values, magnitude, metadata = read_field_hdf5(target)
    np.testing.assert_array_equal(coordinates, parsed.coordinates_m)
    np.testing.assert_array_equal(values, parsed.values)
    np.testing.assert_allclose(magnitude, np.linalg.norm(values, axis=-1), rtol=1e-12)
    assert metadata["source_raw_file"] == "field.fld"
    assert metadata["schema_version"] == "0.1.1"
    assert metadata["topology"] == "unstructured"


def test_real_gauge_scalar_field_is_valid(tmp_path: Path) -> None:
    raw = tmp_path / "real.fld"
    raw.write_text("0 0 0 1\n1 0 0 2\n", encoding="utf-8")
    parsed = parse_field_tab(
        raw,
        quantity="E",
        value_units="V/m",
        coordinate_units="m",
    )
    assert not parsed.is_complex
    write_field_hdf5(tmp_path / "real.h5", parsed, {"normalization": "hfss_eigenmode_peak_1"})


def test_duplicate_sample_points_are_rejected(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from qresaudit.models.config import FieldGridConfig

    points = tmp_path / "points.txt"
    points.write_text("0m 0m 0m\n0m 0m 0m\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate"):
        FieldGridConfig(sample_points_file=points)


def test_complex_i_notation_and_coordinate_header(tmp_path: Path) -> None:
    raw = tmp_path / "complex.fld"
    raw.write_text(
        "# coordinate_units: mm\n# quantity: E\n# units: V/m\n"
        "0 0 0 1+2i 3+4i 5+6i\n"
        "1 0 0 2+3i 4+5i 6+7i\n",
        encoding="utf-8",
    )
    parsed = parse_field_tab(raw)
    assert parsed.is_complex and parsed.is_vector
    assert parsed.coordinates_m[1, 0] == pytest.approx(1e-3)
    assert parsed.values[0, 0] == 1 + 2j


def test_structured_grid_round_trip_preserves_shape(tmp_path: Path) -> None:
    coordinates = np.asarray(
        [[x, y, 0.0] for x in (0.0, 1.0) for y in (0.0, 1.0)],
        dtype=float,
    )
    values = np.arange(12, dtype=float).reshape(4, 3).astype(complex)
    parsed = parse_field_tab(
        _write_vector_field(tmp_path / "structured.fld", coordinates, values),
        quantity="E",
        value_units="V/m",
        coordinate_units="m",
    )
    target = write_field_hdf5(
        tmp_path / "structured.h5",
        parsed,
        {
            "topology": "structured",
            "shape": [2, 2, 1],
            "axes": {"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0]},
            "axis_order": ["x", "y", "z"],
            "flattening_order": "C",
            "normalization": "driven_excitation_dependent",
        },
    )
    restored_coordinates, restored_values, _, metadata = read_field_hdf5(target)
    np.testing.assert_array_equal(restored_coordinates, coordinates)
    np.testing.assert_array_equal(restored_values, values)
    assert metadata["shape"] == [2, 2, 1]
    assert metadata["axis_order"] == ["x", "y", "z"]


def _write_vector_field(path: Path, coordinates: np.ndarray, values: np.ndarray) -> Path:
    lines = [
        " ".join(str(value) for value in [*point, *vector.real])
        for point, vector in zip(coordinates, values, strict=True)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
