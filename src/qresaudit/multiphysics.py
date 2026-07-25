"""Transparent analytic thermal, mechanical, and magnetic perturbation models."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Perturbation:
    value: float
    standard_uncertainty: float
    units: str
    approximation: str


def _valid(*values: float) -> None:
    if not all(math.isfinite(v) for v in values):
        raise ValueError("values must be finite")


def thermal_frequency_shift(
    frequency_hz: float,
    temperature_delta_k: float,
    fractional_tempco_per_k: float,
    uncertainty_hz: float = 0.0,
) -> Perturbation:
    _valid(frequency_hz, temperature_delta_k, fractional_tempco_per_k, uncertainty_hz)
    if frequency_hz <= 0 or uncertainty_hz < 0:
        raise ValueError("frequency must be positive and uncertainty non-negative")
    return Perturbation(
        frequency_hz * fractional_tempco_per_k * temperature_delta_k,
        uncertainty_hz,
        "Hz",
        "first-order fractional temperature coefficient",
    )


def strain_frequency_shift(
    frequency_hz: float, strain: float, gauge_factor: float, uncertainty_hz: float = 0.0
) -> Perturbation:
    _valid(frequency_hz, strain, gauge_factor, uncertainty_hz)
    if frequency_hz <= 0 or uncertainty_hz < 0:
        raise ValueError("frequency must be positive")
    return Perturbation(
        frequency_hz * gauge_factor * strain,
        uncertainty_hz,
        "Hz",
        "first-order linear strain gauge model",
    )


def magnetic_frequency_shift(
    susceptibility: float,
    magnetic_field_t: float,
    filling_factor: float,
    frequency_hz: float,
    uncertainty_hz: float = 0.0,
) -> Perturbation:
    _valid(susceptibility, magnetic_field_t, filling_factor, frequency_hz, uncertainty_hz)
    if frequency_hz <= 0 or filling_factor < 0 or uncertainty_hz < 0:
        raise ValueError("invalid magnetic perturbation domain")
    return Perturbation(
        0.5 * frequency_hz * susceptibility * filling_factor * magnetic_field_t**2,
        uncertainty_hz,
        "Hz",
        "small-susceptibility quadratic magnetic energy approximation",
    )


def combine_perturbations(*terms: Perturbation) -> Perturbation:
    if not terms or len({t.units for t in terms}) != 1:
        raise ValueError("at least one same-unit term is required")
    return Perturbation(
        sum(t.value for t in terms),
        math.sqrt(sum(t.standard_uncertainty**2 for t in terms)),
        terms[0].units,
        "independent uncertainty propagation; correlations not supplied",
    )
