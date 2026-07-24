from pathlib import Path

import numpy as np

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import read_field_hdf5, source_metadata, write_field_hdf5


def test_complex_vector_field_round_trip(tmp_path: Path) -> None:
    raw = tmp_path / "field.fld"
    raw.write_text(
        "# quantity: H\n# units: A/m\n0 0 0 1 2 3 4 5 6\n1 0 0 2 3 4 5 6 7\n",
        encoding="utf-8",
    )
    parsed = parse_field_tab(raw)
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
