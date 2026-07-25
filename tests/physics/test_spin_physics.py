"""Regression tests for spin-resonator equations and explicit contracts."""

import numpy as np

from qresaudit.analysis.spin_resonator import (
    K_B,
    MU_B,
    ensemble_coupling,
    thermal_polarization,
    zero_point_magnetic_field,
)


def test_weighted_zero_point_field_uses_physical_volume() -> None:
    coordinates = np.zeros((2, 3))
    field = np.asarray([[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]])

    rms, peak = zero_point_magnetic_field(field, coordinates, np.asarray([3.0, 1.0]))

    assert np.isclose(rms, np.sqrt(3.0))
    assert np.isclose(peak, 3.0)


def test_spin_half_polarization_matches_two_level_formula() -> None:
    temperature = 0.1
    field = np.asarray([0.0, 0.0, 0.2])
    g_effective = 2.0

    result = thermal_polarization(0.5, temperature, 6e9, field, g_effective)
    expected = np.tanh(g_effective * MU_B * 0.2 / (2.0 * K_B * temperature))

    assert np.isclose(result, expected)


def test_unsupported_spin_model_and_negative_population_are_rejected() -> None:
    with np.testing.assert_raises_regex(ValueError, "spin-1/2"):
        thermal_polarization(1.0, 0.1, 6e9, np.asarray([0.0, 0.0, 0.2]), 2.0)
    with np.testing.assert_raises_regex(ValueError, "spin count"):
        ensemble_coupling(10.0, -1.0)
