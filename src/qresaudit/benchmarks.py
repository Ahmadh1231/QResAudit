"""Deterministic analytical benchmarks for the local physics engine."""

from typing import Any

import numpy as np

from qresaudit.analysis.field_integration import EPSILON_0, MU_0, compute_energy
from qresaudit.analysis.fitting import fit_resonator, notch_model
from qresaudit.analysis.mode_tracking import assign_modes, field_overlap
from qresaudit.analysis.participation import normalized_participation, tls_quality_factor


def run_benchmarks() -> dict[str, Any]:
    """Run fast, solver-free physics checks and return machine-readable evidence."""
    checks: list[dict[str, Any]] = []

    f0 = 6.513e9
    q_loaded = 8_500.0
    q_coupling = 12_000.0
    frequency = np.linspace(f0 - 8e6, f0 + 8e6, 2_001)
    trace = notch_model(frequency, f0, q_loaded, q_coupling)
    fit = fit_resonator(
        frequency,
        trace,
        ql_guess=7_000.0,
        qc_guess=15_000.0,
        use_bootstrap=False,
    )
    if fit.f0_hz is None or fit.q_coupling_absolute is None:
        raise RuntimeError("resonator benchmark did not return required fit parameters")
    fit_errors = {
        "f0": abs(fit.f0_hz / f0 - 1.0),
        "q_loaded": abs(fit.q_loaded / q_loaded - 1.0),
        "q_coupling": abs(fit.q_coupling_absolute / q_coupling - 1.0),
    }
    checks.append(
        {
            "name": "synthetic_notch_fit",
            "passed": max(fit_errors.values()) < 0.05,
            "acceptance": "all relative errors < 5%",
            "relative_errors": fit_errors,
        }
    )

    coords = np.zeros((4, 3))
    e_field = np.tile([2.0, 0.0, 0.0], (4, 1))
    h_field = np.tile([0.0, 3.0, 0.0], (4, 1))
    d_v = np.full(4, 0.25)
    energy = compute_energy(coords, e_field, h_field, d_v)
    expected_e = 0.25 * EPSILON_0 * 4.0
    expected_h = 0.25 * MU_0 * 9.0
    energy_error = max(
        abs(energy["electric_energy_j"] / expected_e - 1.0),
        abs(energy["magnetic_energy_j"] / expected_h - 1.0),
    )
    checks.append(
        {
            "name": "uniform_field_energy",
            "passed": energy_error < 1e-12,
            "acceptance": "relative error < 1e-12",
            "relative_error": energy_error,
        }
    )

    participation = normalized_participation({"substrate": 90.0, "oxide": 7.0, "metal": 3.0})
    quality_factor = tls_quality_factor(
        participation,
        {"substrate": 1e-7, "oxide": 2e-3, "metal": 5e-4},
    )
    expected_q = 1.0 / (0.9e-7 + 0.07 * 2e-3 + 0.03 * 5e-4)
    checks.append(
        {
            "name": "participation_tls_loss",
            "passed": abs(quality_factor / expected_q - 1.0) < 1e-12,
            "acceptance": "relative error < 1e-12",
            "quality_factor": quality_factor,
        }
    )

    mode_coords = np.column_stack((np.arange(4), np.zeros(4), np.zeros(4)))
    first_mode = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]] * 2, dtype=complex)
    phase_overlap = field_overlap(
        mode_coords,
        first_mode,
        mode_coords,
        first_mode * np.exp(1j * 0.73),
    )
    assignment, confidence = assign_modes(np.asarray([[0.02, 0.99], [0.98, 0.01]]))
    mode_passed = abs(phase_overlap - 1.0) < 1e-12 and assignment == [1, 0]
    checks.append(
        {
            "name": "phase_invariant_mode_assignment",
            "passed": mode_passed,
            "acceptance": "overlap = 1 and swapped modes correctly assigned",
            "overlap": phase_overlap,
            "assignment": assignment,
            "confidence": confidence,
        }
    )

    return {
        "passed": all(bool(check["passed"]) for check in checks),
        "scope": "deterministic analytical and synthetic checks; no solver validation",
        "checks": checks,
    }
