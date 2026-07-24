from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from qresaudit.io.field_tab import ParsedField
from qresaudit.io.fields_hdf5 import read_field_hdf5, write_field_hdf5
from qresaudit_hfss.inspect import axis_count


@given(
    intervals=st.integers(min_value=1, max_value=1000),
    step=st.floats(
        min_value=1e-9,
        max_value=1e3,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_grid_count_property(intervals: int, step: float) -> None:
    assert axis_count(0.0, intervals * step, step) == intervals + 1


@given(
    real=st.lists(
        st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=3,
        max_size=30,
    ),
)
def test_field_hdf5_property(real: list[float]) -> None:
    point_count = len(real) // 3
    values = np.asarray(real[: point_count * 3], dtype=np.float64).reshape(point_count, 3)
    complex_values = values + 1j * values[::-1]
    parsed = ParsedField(
        coordinates_m=np.column_stack(
            (np.arange(point_count), np.zeros(point_count), np.zeros(point_count))
        ),
        values=complex_values,
        is_complex=True,
        is_vector=True,
        quantity="H",
        value_units="A/m",
        coordinate_units="m",
        source_header=(),
    )
    with TemporaryDirectory() as directory:
        target = write_field_hdf5(
            Path(directory) / "field.h5",
            parsed,
            {"normalization": "driven_excitation_dependent"},
        )
        _, restored, magnitude, _ = read_field_hdf5(target)
    np.testing.assert_array_equal(restored, complex_values)
    np.testing.assert_allclose(
        magnitude,
        np.linalg.norm(complex_values, axis=-1),
        rtol=1e-12,
        atol=1e-15,
    )
