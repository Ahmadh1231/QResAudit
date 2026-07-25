"""Bundle comparison — compare two validated evidence bundles.

Classifies differences: NUMERICAL_DIFFERENCE, CONFIGURATION_DIFFERENCE,
SOLVER_VERSION_DIFFERENCE, PHYSICAL_MODEL_DIFFERENCE, MISSING_EVIDENCE.

Command:
    qresaudit compare RUN_A RUN_B
"""

from pathlib import Path

import numpy as np

from qresaudit.analysis.mode_tracking import field_overlap
from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.io.touchstone import load_network
from qresaudit.models.v0_2 import ComparisonResult, ModeOverlapResult


def compare_bundles(bundle_a: Path, bundle_b: Path) -> ComparisonResult:
    """Compare two validated bundles across all evidence dimensions."""
    ma = load_manifest(bundle_a / "manifest.json")
    mb = load_manifest(bundle_b / "manifest.json")

    result = ComparisonResult(
        bundle_a=str(bundle_a),
        bundle_b=str(bundle_b),
        schema_versions_match=ma.schema_version == mb.schema_version,
        solution_kinds_match=ma.solution_kind == mb.solution_kind,
    )

    # Provenance differences
    if ma.aedt_version != mb.aedt_version:
        result.provenance_differences.append(f"aedt: {ma.aedt_version} vs {mb.aedt_version}")
    if ma.pyaedt_version != mb.pyaedt_version:
        result.provenance_differences.append(f"pyaedt: {ma.pyaedt_version} vs {mb.pyaedt_version}")
    if ma.python_version != mb.python_version:
        result.provenance_differences.append(f"python: {ma.python_version} vs {mb.python_version}")
    if (
        ma.project_file_sha256 != mb.project_file_sha256
        and ma.project_file_sha256
        and mb.project_file_sha256
    ):
        result.provenance_differences.append("project_file_sha256 differs")

    # Variable differences. Portable bundles may express a solved case through
    # variation, solved_variation, project_variables, or design_variables.
    # Comparing only the latter two silently hid real parameter sweeps.
    variables_a = {
        **ma.project_variables,
        **ma.design_variables,
        **ma.variation,
        **ma.solved_variation,
    }
    variables_b = {
        **mb.project_variables,
        **mb.design_variables,
        **mb.variation,
        **mb.solved_variation,
    }
    all_vars = (
        set(variables_a)
        | set(variables_b)
    )
    for var in sorted(all_vars):
        va = variables_a.get(var)
        vb = variables_b.get(var)
        expression_a = va.expression if va else "<missing>"
        expression_b = vb.expression if vb else "<missing>"
        if expression_a != expression_b:
            result.variable_differences.append(f"{var}: {expression_a} vs {expression_b}")

    # Mesh differences
    mesh_a = next((f for f in ma.files if f.role == "mesh_stats"), None)
    mesh_b = next((f for f in mb.files if f.role == "mesh_stats"), None)
    if mesh_a and mesh_b:
        try:
            import pandas as pd

            da = pd.read_csv(safe_bundle_path(bundle_a, mesh_a.path))
            db = pd.read_csv(safe_bundle_path(bundle_b, mesh_b.path))
            if len(da) > 0 and len(db) > 0:
                ta = da["tetrahedra"].iloc[-1]
                tb = db["tetrahedra"].iloc[-1]
                if abs(ta - tb) / (abs(ta) + 1) > 0.05:
                    result.mesh_differences.append(f"tetrahedra: {ta} vs {tb}")
        except Exception:
            pass

    # Touchstone comparison
    if ma.touchstone and mb.touchstone:
        try:
            na = load_network(safe_bundle_path(bundle_a, ma.touchstone.path))
            nb = load_network(safe_bundle_path(bundle_b, mb.touchstone.path))
            rms_diff = float(np.sqrt(np.mean(np.abs(na.s - nb.s) ** 2)))
            max_diff = float(np.max(np.abs(na.s - nb.s)))
            result.s_parameter_rms_difference = rms_diff
            result.s_parameter_max_difference = max_diff
        except Exception:
            pass

    # Frequency and Q differences for eigenmode bundles
    if ma.eigenmode and mb.eigenmode:
        try:
            import pandas as pd

            ea = pd.read_csv(safe_bundle_path(bundle_a, ma.eigenmode.path))
            eb = pd.read_csv(safe_bundle_path(bundle_b, mb.eigenmode.path))
            if "frequency_real_hz" in ea and "frequency_real_hz" in eb:
                fa = ea["frequency_real_hz"].iloc[0]
                fb = eb["frequency_real_hz"].iloc[0]
                result.resonant_frequency_difference_hz = float(abs(fa - fb))
                result.resonant_frequency_relative = (
                    float(abs(fa - fb) / abs(fa)) if fa != 0 else 0.0
                )
        except Exception:
            pass

    # Field overlap comparison
    if ma.fields and mb.fields:
        overlaps = []
        for fa, fb in zip(ma.fields, mb.fields, strict=False):
            try:
                ca_raw, va_raw, _, _ = read_field_hdf5(safe_bundle_path(bundle_a, fa.path))
                cb_raw, vb_raw, _, _ = read_field_hdf5(safe_bundle_path(bundle_b, fb.path))
                if ca_raw is None or va_raw is None or cb_raw is None or vb_raw is None:
                    continue
                ca_arr: np.ndarray = ca_raw
                va_arr: np.ndarray = va_raw
                cb_arr: np.ndarray = cb_raw
                vb_arr: np.ndarray = vb_raw
                overlap_val = field_overlap(ca_arr, va_arr, cb_arr, vb_arr)
                overlaps.append(
                    ModeOverlapResult(
                        mode_a=fa.mode or 0,
                        mode_b=fb.mode or 0,
                        electric_overlap=overlap_val,
                        frequency_a_hz=fa.frequency_hz or 0.0,
                        frequency_b_hz=fb.frequency_hz or 0.0,
                        frequency_difference_hz=float(
                            abs((fa.frequency_hz or 0) - (fb.frequency_hz or 0))
                        ),
                    )
                )
            except Exception:
                pass
        result.mode_overlap = overlaps

    # Classification
    if result.provenance_differences or result.variable_differences:
        if any("sha256" in d for d in result.provenance_differences):
            result.classification = "PHYSICAL_MODEL_DIFFERENCE"
        elif any("version" in d.lower() for d in result.provenance_differences):
            result.classification = "SOLVER_VERSION_DIFFERENCE"
        else:
            result.classification = "CONFIGURATION_DIFFERENCE"
    elif result.s_parameter_rms_difference is not None:
        if result.s_parameter_rms_difference < 1e-6:
            result.classification = "NUMERICAL_DIFFERENCE"
        else:
            result.classification = "PHYSICAL_MODEL_DIFFERENCE"
    else:
        result.classification = "MISSING_EVIDENCE"

    return result
