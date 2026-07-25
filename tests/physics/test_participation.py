"""Participation and TLS-loss invariants."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from qresaudit.analysis.participation import normalized_participation, tls_quality_factor


@given(st.floats(min_value=1e-12, max_value=1e12, allow_nan=False, allow_infinity=False))
def test_field_amplitude_scaling_does_not_change_participation(scale: float) -> None:
    base = {"substrate": 90.0, "oxide": 7.0, "metal": 3.0}
    scaled = {region: energy * scale * scale for region, energy in base.items()}

    assert normalized_participation(scaled) == pytest.approx(normalized_participation(base))


def test_tls_quality_factor_matches_loss_budget_equation() -> None:
    participation = {"sapphire": 0.9, "oxide": 0.07, "metal": 0.03}
    loss_tangent = {"sapphire": 1e-7, "oxide": 2e-3, "metal": 5e-4}

    result = tls_quality_factor(participation, loss_tangent)
    expected = 1.0 / sum(participation[key] * loss_tangent[key] for key in participation)

    assert math.isclose(result, expected, rel_tol=1e-15)
