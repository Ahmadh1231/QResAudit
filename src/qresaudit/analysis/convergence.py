"""Convergence auditing — analyze adaptive-pass evidence for quality and reliability.

Command:
    qresaudit convergence BUNDLE
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.hfss_convergence import parse_convergence
from qresaudit.models.v0_2 import AdaptivePassRecord, ConvergenceDiagnostic


def canonical_passes(convergence_df: pd.DataFrame) -> list[AdaptivePassRecord]:
    """Convert a parsed convergence DataFrame into structured records."""
    passes: list[AdaptivePassRecord] = []
    for _, row in convergence_df.iterrows():
        passes.append(
            AdaptivePassRecord(
                pass_number=int(row["pass_number"]),
                tetrahedra=0,  # not available in convergence table alone
                frequency_hz=float(row["frequency_hz"]) if pd.notna(row["frequency_hz"]) else None,
                maximum_delta_s=float(row["max_delta_s_percent"])
                if pd.notna(row["max_delta_s_percent"])
                else None,
                converged=bool(row["converged"]) if pd.notna(row["converged"]) else False,
                raw_evidence_path=str(row.get("raw_evidence_path", "")),
            )
        )
    return passes


def _is_monotonic(values: np.ndarray) -> bool:
    """Check if a sequence is strictly monotonic (increasing or decreasing)."""
    finite = values[np.isfinite(values)]
    if len(finite) < 2:
        return True
    diffs = np.diff(finite)
    return bool(np.all(diffs >= 0) or np.all(diffs <= 0))


def _detect_oscillation(values: np.ndarray, threshold: float = 0.01) -> bool:
    """Detect oscillatory behavior in a convergence sequence."""
    finite = values[np.isfinite(values)]
    if len(finite) < 3:
        return False
    sign_changes = np.sum(np.abs(np.diff(np.sign(np.diff(finite)))) > 0)
    return bool(sign_changes >= len(finite) // 3)


def _detect_stagnation(values: np.ndarray, threshold: float = 1e-4) -> bool:
    """Detect stagnation — the last few values change very little."""
    finite = values[np.isfinite(values)]
    if len(finite) < 3:
        return False
    last_few = finite[-min(3, len(finite)) :]
    return bool(np.std(last_few) < threshold * np.abs(np.mean(last_few) + 1e-30))


def _extrapolate_limit(values: np.ndarray) -> tuple[float, float]:
    """Richardson-like extrapolation of limiting value."""
    finite = values[np.isfinite(values)]
    if len(finite) < 3:
        return (float(finite[-1]), 0.0) if len(finite) > 0 else (0.0, 0.0)
    # Linear fit to last 3 points vs 1/pass
    passes = np.arange(len(finite) - 3, len(finite), dtype=float) + 1
    x = 1.0 / passes
    y = finite[-3:]
    coeffs = np.polyfit(x, y, 1)
    limit = float(coeffs[1])  # intercept at 1/pass → 0
    uncertainty = float(np.abs(coeffs[0]) / (len(finite) ** 2))
    return limit, uncertainty


def audit_convergence(bundle: Path) -> ConvergenceDiagnostic:
    """Analyze convergence evidence from a validated bundle."""
    manifest = load_manifest(bundle / "manifest.json")

    # Find convergence file
    conv_record = next(
        (f for f in manifest.files if f.role == "convergence" and f.path.endswith(".csv")),
        None,
    )
    if conv_record is None:
        return ConvergenceDiagnostic(
            insufficient_passes=True,
            solver_messages=["no convergence evidence file found"],
        )

    conv_path = safe_bundle_path(bundle, conv_record.path)
    df = parse_convergence(conv_path)
    passes = canonical_passes(df)

    if not passes:
        return ConvergenceDiagnostic(insufficient_passes=True)

    frequencies = np.array(
        [p.frequency_hz for p in passes if p.frequency_hz is not None], dtype=float
    )
    delta_s_values = np.array(
        [p.maximum_delta_s for p in passes if p.maximum_delta_s is not None], dtype=float
    )

    final_pass = passes[-1]
    mesh_growth = None
    tet_counts = [p.tetrahedra for p in passes if p.tetrahedra > 0]
    if len(tet_counts) >= 2:
        mesh_growth = float(tet_counts[-1] / tet_counts[-2]) if tet_counts[-2] > 0 else None

    final_freq_change = None
    if len(frequencies) >= 2 and frequencies[-2] != 0:
        final_freq_change = float(abs(frequencies[-1] - frequencies[-2]) / abs(frequencies[-2]))

    limit_val, limit_unc = None, None
    if len(frequencies) >= 3:
        limit_val, limit_unc = _extrapolate_limit(frequencies)

    # False convergence: declared converged but sequence still changing rapidly
    false_convergence_risk = "not_evaluated"
    if final_pass.converged and len(delta_s_values) >= 2:
        recent_change = float(abs(delta_s_values[-1] - delta_s_values[-2]))
        if recent_change > 0.01:
            false_convergence_risk = "high"
        elif recent_change > 0.001:
            false_convergence_risk = "medium"
        else:
            false_convergence_risk = "low"

    return ConvergenceDiagnostic(
        passes=passes,
        total_passes=len(passes),
        final_frequency_hz=final_pass.frequency_hz,
        final_frequency_change_fraction=final_freq_change,
        final_max_delta_s=final_pass.maximum_delta_s,
        is_converged=bool(final_pass.converged),
        mesh_growth_ratio=mesh_growth,
        is_monotonic_frequency=_is_monotonic(frequencies) if len(frequencies) >= 2 else False,
        is_monotonic_delta_s=_is_monotonic(delta_s_values) if len(delta_s_values) >= 2 else False,
        oscillation_detected=_detect_oscillation(delta_s_values)
        if len(delta_s_values) >= 3
        else False,
        stagnation_detected=_detect_stagnation(delta_s_values)
        if len(delta_s_values) >= 3
        else False,
        insufficient_passes=len(passes) < 2,
        achieved_max_delta_s=final_pass.maximum_delta_s,
        false_convergence_risk=false_convergence_risk,
        limiting_value_extrapolation_hz=limit_val,
        limiting_value_uncertainty_hz=limit_unc,
    )


def convergence_to_dataframe(diag: ConvergenceDiagnostic) -> pd.DataFrame:
    """Convert a ConvergenceDiagnostic to a pandas DataFrame for CSV export."""
    rows = []
    for p in diag.passes:
        rows.append(
            {
                "pass_number": p.pass_number,
                "tetrahedra": p.tetrahedra,
                "frequency_hz": p.frequency_hz,
                "frequency_change_fraction": p.frequency_change_fraction,
                "maximum_delta_s": p.maximum_delta_s,
                "converged": p.converged,
                "elapsed_time_s": p.elapsed_time_s,
                "peak_memory_bytes": p.peak_memory_bytes,
            }
        )
    return pd.DataFrame(rows)


def convergence_summary_json(diag: ConvergenceDiagnostic) -> dict[str, Any]:
    """Serializable summary for JSON output."""
    return {
        "total_passes": diag.total_passes,
        "final_frequency_hz": diag.final_frequency_hz,
        "final_frequency_change_fraction": diag.final_frequency_change_fraction,
        "final_max_delta_s": diag.final_max_delta_s,
        "is_converged": diag.is_converged,
        "mesh_growth_ratio": diag.mesh_growth_ratio,
        "is_monotonic_frequency": diag.is_monotonic_frequency,
        "is_monotonic_delta_s": diag.is_monotonic_delta_s,
        "oscillation_detected": diag.oscillation_detected,
        "stagnation_detected": diag.stagnation_detected,
        "insufficient_passes": diag.insufficient_passes,
        "false_convergence_risk": diag.false_convergence_risk,
        "limiting_value_extrapolation_hz": diag.limiting_value_extrapolation_hz,
        "limiting_value_uncertainty_hz": diag.limiting_value_uncertainty_hz,
    }
