"""Analytical field-energy tests."""

import numpy as np

from qresaudit.analysis.field_integration import EPSILON_0, MU_0, compute_energy


def test_uniform_peak_phasor_energy_uses_one_quarter_factor() -> None:
    coordinates = np.zeros((4, 3))
    electric = np.tile([2.0, 0.0, 0.0], (4, 1))
    magnetic = np.tile([0.0, 3.0, 0.0], (4, 1))
    volume = np.full(4, 0.25)

    result = compute_energy(coordinates, electric, magnetic, volume)

    assert np.isclose(result["electric_energy_j"], 0.25 * EPSILON_0 * 4.0)
    assert np.isclose(result["magnetic_energy_j"], 0.25 * MU_0 * 9.0)


def test_rms_phasor_energy_is_twice_peak_phasor_result() -> None:
    coordinates = np.zeros((2, 3))
    electric = np.ones((2, 3))
    magnetic = np.ones((2, 3))
    peak = compute_energy(coordinates, electric, magnetic, phasor_convention="peak")
    rms = compute_energy(coordinates, electric, magnetic, phasor_convention="rms")

    assert np.isclose(rms["electric_energy_j"], 2.0 * peak["electric_energy_j"])
    assert np.isclose(rms["magnetic_energy_j"], 2.0 * peak["magnetic_energy_j"])
