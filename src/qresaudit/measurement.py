"""Uncertainty-aware, offline digital-twin comparison."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from qresaudit.v2 import Status


@dataclass(frozen=True)
class Sweep:
    axis: str
    values: NDArray[np.float64]
    response: NDArray[np.complex128] | NDArray[np.float64]
    uncertainty: NDArray[np.float64] | None = None
    axis_unit: str = ""
    response_unit: str = ""


@dataclass(frozen=True)
class Discrepancy:
    status: Status
    rms: float
    max_abs: float
    normalized_rms: float | None
    message: str


def _aligned(simulation: Sweep, experiment: Sweep) -> bool:
    return (
        simulation.axis == experiment.axis
        and simulation.axis_unit == experiment.axis_unit
        and simulation.response_unit == experiment.response_unit
        and simulation.values.shape == experiment.values.shape
        and np.allclose(simulation.values, experiment.values, rtol=1e-12, atol=0)
        and simulation.response.shape == experiment.response.shape
    )


def compare_sweeps(simulation: Sweep, experiment: Sweep, sigma_floor: float = 1e-12) -> Discrepancy:
    if sigma_floor <= 0 or not np.isfinite(sigma_floor):
        raise ValueError("sigma_floor must be finite and positive")
    if not _aligned(simulation, experiment):
        return Discrepancy(
            Status.FAIL, float("nan"), float("nan"), None, "Sweep axes or shapes do not align"
        )
    if not (
        np.all(np.isfinite(simulation.values))
        and np.all(np.isfinite(experiment.values))
        and np.all(np.isfinite(simulation.response))
        and np.all(np.isfinite(experiment.response))
    ):
        return Discrepancy(
            Status.FAIL, float("nan"), float("nan"), None, "Sweep contains nonfinite values"
        )
    residual = np.asarray(simulation.response) - np.asarray(experiment.response)
    rms = float(np.sqrt(np.mean(np.abs(residual) ** 2)))
    maximum = float(np.max(np.abs(residual)))
    if experiment.uncertainty is None:
        return Discrepancy(
            Status.NOT_EVALUATED,
            rms,
            maximum,
            None,
            "Residual computed; no measurement uncertainty was supplied",
        )
    sigma = np.asarray(experiment.uncertainty, dtype=float)
    if sigma.shape != residual.shape or np.any(sigma < 0) or not np.all(np.isfinite(sigma)):
        return Discrepancy(Status.FAIL, rms, maximum, None, "Invalid uncertainty array")
    normalized_rms = float(
        np.sqrt(np.mean((np.abs(residual) / np.maximum(sigma, sigma_floor)) ** 2))
    )
    status = (
        Status.PASS
        if normalized_rms <= 2
        else Status.WARNING
        if normalized_rms <= 3
        else Status.FAIL
    )
    return Discrepancy(
        status,
        rms,
        maximum,
        normalized_rms,
        f"{status}: uncertainty-normalized residual",
    )


def calibrate_offset(simulation: Sweep, experiment: Sweep) -> complex:
    if not _aligned(simulation, experiment):
        raise ValueError("sweeps are not aligned")
    return complex(np.mean(experiment.response - simulation.response))


def resonance_frequency_shift(simulated_hz: float, measured_hz: float) -> dict[str, float | str]:
    if simulated_hz <= 0 or measured_hz <= 0:
        raise ValueError("resonance frequencies must be positive")
    shift = measured_hz - simulated_hz
    return {
        "shift_hz": shift,
        "relative_shift": shift / simulated_hz,
        "likely_cause": (
            "effective permittivity or geometry mismatch"
            if abs(shift / simulated_hz) > 1e-4
            else "within the configured small-discrepancy regime"
        ),
    }
