"""Analytical field-energy tests."""

import numpy as np

from qresaudit.analysis.field_integration import (
    EPSILON_0,
    MU_0,
    compute_energy,
    normalize_field,
    structured_volume_weights,
)


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
    volume = np.ones(2)
    peak = compute_energy(coordinates, electric, magnetic, volume, phasor_convention="peak")
    rms = compute_energy(coordinates, electric, magnetic, volume, phasor_convention="rms")

    assert np.isclose(rms["electric_energy_j"], 2.0 * peak["electric_energy_j"])
    assert np.isclose(rms["magnetic_energy_j"], 2.0 * peak["magnetic_energy_j"])


def test_nonuniform_structured_weights_integrate_bounding_volume() -> None:
    axes = ([0.0, 1.0, 3.0], [0.0, 2.0], [-1.0, 0.0, 4.0])
    mesh = np.meshgrid(*axes, indexing="ij")
    coordinates = np.column_stack([component.ravel(order="C") for component in mesh])

    weights = structured_volume_weights(
        coordinates,
        {
            "topology": "structured",
            "shape": [3, 2, 3],
            "axis_order": ["x", "y", "z"],
            "flattening_order": "C",
        },
    )

    assert np.isclose(np.sum(weights), 3.0 * 2.0 * 5.0)


def test_volume_weight_length_mismatch_is_rejected() -> None:
    coordinates = np.zeros((2, 3))
    with np.testing.assert_raises_regex(ValueError, "one value per coordinate"):
        compute_energy(
            coordinates,
            np.ones((2, 3)),
            np.ones((2, 3)),
            np.ones(1),
        )


def test_zero_energy_field_cannot_claim_normalization() -> None:
    coordinates = np.zeros((2, 3))
    with np.testing.assert_raises_regex(ValueError, "zero-energy"):
        normalize_field(
            np.zeros((2, 3)),
            np.zeros((2, 3)),
            coordinates,
            1.0,
            np.ones(2),
        )
