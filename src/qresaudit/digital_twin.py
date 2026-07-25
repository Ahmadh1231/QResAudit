"""Deterministic digital-twin calibration from supplied simulation/measurement data."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationResult:
    parameters: dict[str, float]
    standard_uncertainty: dict[str, float]
    residuals: dict[str, float]
    simulated: dict[str, float]
    measured: dict[str, float]
    assumptions: tuple[str, ...]
    evidence: str


def calibrate_resonator(
    simulated: dict[str, float],
    measured: dict[str, float],
    *,
    measurement_uncertainty: dict[str, float] | None = None,
    parameter_map: dict[str, str] | None = None,
) -> CalibrationResult:
    required = {"frequency_hz", "q"}
    if not required <= simulated.keys() or not required <= measured.keys():
        raise ValueError("frequency_hz and q are required")
    sigma = measurement_uncertainty or {k: 0.0 for k in required}
    if any(
        key not in required or not math.isfinite(float(value)) or float(value) < 0
        for key, value in sigma.items()
    ):
        raise ValueError("measurement uncertainties must be finite and non-negative")
    if any(
        not math.isfinite(float(simulated[k])) or not math.isfinite(float(measured[k]))
        for k in required
    ):
        raise ValueError("calibration inputs must be finite")
    if (
        simulated["frequency_hz"] <= 0
        or simulated["q"] <= 0
        or measured["frequency_hz"] <= 0
        or measured["q"] <= 0
    ):
        raise ValueError("frequency and Q must be positive")
    params = dict(parameter_map or {})
    result = {}
    uncertainty = {}
    residuals = {}
    for key in required:
        delta = float(measured[key] - simulated[key])
        residuals[key] = delta
        result[params.get(key, key + "_correction")] = float(delta)
        uncertainty[params.get(key, key + "_correction")] = float(sigma.get(key, 0.0))
    assumptions = (
        "measurement values are aligned to the simulated mode",
        "corrections are local additive updates",
        "no unprovided material or loss model was inferred",
    )
    return CalibrationResult(
        result,
        uncertainty,
        residuals,
        {key: float(simulated[key]) for key in required},
        {key: float(measured[key]) for key in required},
        assumptions,
        "experimental evidence supplied by caller",
    )


def update_material_loss_model(
    material: dict[str, float],
    calibration: CalibrationResult,
    *,
    dielectric_key: str = "permittivity",
    loss_key: str = "loss_tangent",
) -> dict[str, float]:
    updated = dict(material)
    for key in updated:
        if not math.isfinite(float(updated[key])):
            raise ValueError("material parameters must be finite")
    if loss_key in updated and loss_key + "_correction" in calibration.parameters:
        updated[loss_key] = max(
            0.0, updated[loss_key] + calibration.parameters[loss_key + "_correction"]
        )
    if dielectric_key in updated and "frequency_hz_correction" in calibration.parameters:
        simulated_frequency = calibration.simulated["frequency_hz"]
        measured_frequency = calibration.measured["frequency_hz"]
        updated[dielectric_key] = max(
            1e-12,
            updated[dielectric_key] * (simulated_frequency / measured_frequency) ** 2,
        )
    return updated
