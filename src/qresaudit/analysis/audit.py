"""Automated audit report generation.

Produces HTML, JSON, and Markdown audit reports from a validated bundle.
Every result is PASS / WARNING / FAIL / NOT_EVALUATED.
Missing evidence is never treated as a pass.

Command:
    qresaudit audit BUNDLE --output audit/
"""

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from qresaudit.analysis.convergence import audit_convergence, convergence_summary_json
from qresaudit.analysis.field_integration import integrate_bundle_fields
from qresaudit.analysis.participation import compute_participation_bundle
from qresaudit.io.bundle import load_manifest
from qresaudit.models.common import Severity
from qresaudit.models.v0_2 import (
    AuditReport,
    AuditVerdict,
    DiagnosticRecord,
)
from qresaudit.validation.engine import validate_bundle


def _verdict(
    verdicts: list[AuditVerdict],
    section: str,
    check: str,
    result: str,
    detail: str = "",
    diagnostics: list[str] | None = None,
) -> None:
    verdicts.append(
        AuditVerdict(
            section=section,
            check=check,
            result=result,
            detail=detail,
            diagnostics=diagnostics or [],
        )
    )


def audit_bundle(
    bundle: Path,
    regions_path: Path | None = None,
    fit_response: str = "S21",
    fit_model: str = "notch",
) -> AuditReport:
    """Generate a complete audit report for a validated bundle."""
    validation = validate_bundle(bundle)
    manifest = load_manifest(bundle / "manifest.json")
    verdicts: list[AuditVerdict] = []
    _verdict(
        verdicts,
        "validation",
        "bundle_validation",
        "PASS" if validation.valid else "FAIL",
        (
            "Bundle passed semantic and checksum validation"
            if validation.valid
            else "; ".join(
                f"{diagnostic.code}: {diagnostic.message}"
                for diagnostic in validation.diagnostics
                if diagnostic.severity == Severity.ERROR
            )
        ),
    )

    # ── Provenance checks ──────────────────────────────────────────────
    _verdict(
        verdicts,
        "provenance",
        "manifest_loaded",
        "PASS",
        f"Schema {manifest.schema_version}, exporter {manifest.exporter_version}",
    )

    if manifest.project_file_sha256:
        _verdict(
            verdicts,
            "provenance",
            "project_hash",
            "PASS",
            f"SHA-256: {manifest.project_file_sha256[:16]}...",
        )
    else:
        _verdict(verdicts, "provenance", "project_hash", "FAIL", "Source project hash is missing")

    _verdict(
        verdicts,
        "provenance",
        "aedt_version",
        "PASS" if manifest.aedt_version else "WARNING",
        f"AEDT {manifest.aedt_version} / PyAEDT {manifest.pyaedt_version}",
    )

    _verdict(
        verdicts,
        "provenance",
        "solution_kind",
        "PASS",
        f"{manifest.solution_kind.value} — {manifest.setup_name}",
    )

    # ── Evidence completeness ──────────────────────────────────────────
    _verdict(
        verdicts,
        "evidence",
        "touchstone_present",
        "PASS" if manifest.touchstone else "NOT_EVALUATED",
        f"{manifest.touchstone.number_of_ports} ports" if manifest.touchstone else "",
    )

    _verdict(
        verdicts,
        "evidence",
        "eigenmodes_present",
        "PASS" if manifest.eigenmode else "NOT_EVALUATED",
        f"{manifest.eigenmode.mode_count} modes" if manifest.eigenmode else "",
    )

    _verdict(
        verdicts,
        "evidence",
        "fields_present",
        "PASS"
        if manifest.fields
        else ("FAIL" if manifest.evidence_profile == "strict" else "NOT_EVALUATED"),
        f"{len(manifest.fields)} field records",
    )

    conv_present = any(f.role == "convergence" for f in manifest.files)
    _verdict(
        verdicts,
        "evidence",
        "convergence_present",
        "PASS" if conv_present else "WARNING",
        "Convergence data found" if conv_present else "No convergence data",
    )

    mesh_present = any(f.role == "mesh_stats" for f in manifest.files)
    _verdict(
        verdicts,
        "evidence",
        "mesh_stats_present",
        "PASS" if mesh_present else "WARNING",
        "Mesh statistics found" if mesh_present else "No mesh statistics",
    )

    # ── Validation status ──────────────────────────────────────────────
    diag_errors = [d for d in manifest.diagnostics if d.severity == Severity.ERROR]
    diag_warnings = [d for d in manifest.diagnostics if d.severity == Severity.WARNING]
    _verdict(
        verdicts,
        "validation",
        "export_status",
        "PASS"
        if manifest.bundle_status.value in ("complete", "complete_with_warnings")
        else "FAIL",
        f"Bundle status: {manifest.bundle_status.value}",
    )
    _verdict(
        verdicts,
        "validation",
        "export_errors",
        "FAIL" if diag_errors else "PASS",
        f"{len(diag_errors)} errors" if diag_errors else "No errors",
    )
    _verdict(
        verdicts,
        "validation",
        "export_warnings",
        "WARNING" if diag_warnings else "PASS",
        f"{len(diag_warnings)} warnings" if diag_warnings else "No warnings",
    )

    # ── Convergence audit ──────────────────────────────────────────────
    convergence = None
    if conv_present:
        try:
            convergence = audit_convergence(bundle)
            convergence_metric = (
                "delta-frequency %" if manifest.solution_kind.value == "eigenmode" else "delta-S %"
            )
            _verdict(
                verdicts,
                "convergence",
                "is_converged",
                "PASS" if convergence.is_converged else "FAIL",
                f"{convergence.total_passes} passes, "
                f"{convergence_metric}={convergence.final_max_delta_s}",
            )
            if convergence.false_convergence_risk not in ("low", "not_evaluated"):
                _verdict(
                    verdicts,
                    "convergence",
                    "false_convergence",
                    "WARNING" if convergence.false_convergence_risk == "medium" else "FAIL",
                    f"False convergence risk: {convergence.false_convergence_risk}",
                )
            if convergence.oscillation_detected:
                _verdict(
                    verdicts,
                    "convergence",
                    "oscillation",
                    "WARNING",
                    "Oscillation detected in convergence sequence",
                )
            if convergence.insufficient_passes:
                _verdict(
                    verdicts,
                    "convergence",
                    "insufficient_passes",
                    "FAIL",
                    "Insufficient adaptive passes for convergence assessment",
                )
        except Exception as exc:
            _verdict(verdicts, "convergence", "audit_failed", "FAIL", str(exc))

    # ── Resonator fitting ──────────────────────────────────────────────
    fit_results: dict[str, Any] = {}
    if manifest.touchstone:
        for response in ["S21"]:
            try:
                from qresaudit.analysis.fitting import fit_bundle_resonator

                fit_result = fit_bundle_resonator(bundle, response=response, model=fit_model)
                # Ensure real-valued output
                fit_result.f0_hz = float(abs(fit_result.f0_hz))
                fit_result.q_loaded = float(abs(fit_result.q_loaded))
                fit_result.q_coupling_absolute = (
                    float(abs(fit_result.q_coupling_absolute))
                    if fit_result.q_coupling_absolute
                    else None
                )
                fit_results[response] = fit_result
                _verdict(
                    verdicts,
                    "fitting",
                    f"{response}_{fit_model}",
                    "PASS" if fit_result.optimizer_converged else "WARNING",
                    f"f0={fit_result.f0_hz / 1e9:.3f} GHz, Ql={fit_result.q_loaded:.0f}, "
                    f"Qi={fit_result.q_internal or float('nan'):.0f}",
                )
            except Exception as exc:
                _verdict(verdicts, "fitting", f"{response}_{fit_model}", "FAIL", str(exc))

    # ── Field integration ──────────────────────────────────────────────
    field_integration = []
    if manifest.fields:
        try:
            field_integration = integrate_bundle_fields(bundle)
            for fi in field_integration:
                _verdict(
                    verdicts,
                    "fields",
                    f"energy_{fi.region}",
                    "PASS",
                    f"U={fi.total_energy_j:.3e} J, V_eff={fi.effective_mode_volume_m3 or 0:.3e} m³",
                )
        except Exception as exc:
            _verdict(verdicts, "fields", "integration_failed", "FAIL", str(exc))

    # ── Participation ──────────────────────────────────────────────────
    loss_estimate = None
    if manifest.fields and regions_path is not None:
        try:
            _, loss_estimate = compute_participation_bundle(bundle, regions_path)
            if loss_estimate.total_q_loss is not None:
                _verdict(
                    verdicts,
                    "participation",
                    "total_q_loss",
                    "PASS",
                    f"Q_loss={loss_estimate.total_q_loss:.0f}, "
                    f"sum_check={loss_estimate.sum_check:.3f}",
                )
            else:
                _verdict(
                    verdicts,
                    "participation",
                    "total_q_loss",
                    "WARNING",
                    "Could not compute total Q_loss",
                )
        except Exception as exc:
            _verdict(verdicts, "participation", "analysis_failed", "FAIL", str(exc))

    # ── Build report ───────────────────────────────────────────────────
    return AuditReport(
        bundle_path=str(bundle),
        audit_timestamp_utc=datetime.now(UTC),
        verdicts=verdicts,
        convergence=convergence,
        fit_results={k: v for k, v in fit_results.items() if hasattr(v, "f0_hz")},
        field_integration=field_integration,
        participation=loss_estimate,
        diagnostics_raw=[
            DiagnosticRecord(
                code=d.code,
                severity=d.severity,
                message=d.message,
                path=d.path,
                context=d.context,
            )
            for d in manifest.diagnostics
        ],
    )


def render_audit_html(report: AuditReport) -> str:
    """Render an audit report as a self-contained HTML page."""

    def _badge(result: str) -> str:
        colors = {
            "PASS": "#28a745",
            "WARNING": "#ffc107",
            "FAIL": "#dc3545",
            "NOT_EVALUATED": "#6c757d",
        }
        color = colors.get(result, "#6c757d")
        return (
            f'<span style="background:{color};color:white;'
            f'padding:2px 8px;border-radius:4px;font-weight:bold">{result}</span>'
        )

    rows = "\n".join(
        f"<tr><td>{escape(v.section)}</td><td>{escape(v.check)}</td>"
        f"<td>{_badge(v.result)}</td><td>{escape(v.detail)}</td></tr>"
        for v in report.verdicts
    )

    n_pass = sum(1 for v in report.verdicts if v.result == "PASS")
    n_warn = sum(1 for v in report.verdicts if v.result == "WARNING")
    n_fail = sum(1 for v in report.verdicts if v.result == "FAIL")
    n_na = sum(1 for v in report.verdicts if v.result == "NOT_EVALUATED")
    evaluated = n_pass + n_warn + n_fail
    evidence_score = 100.0 * n_pass / evaluated if evaluated else 0.0
    overall = "FAIL" if n_fail else ("WARNING" if n_warn else "PASS")
    fit_json = escape(
        json.dumps(
            {
                key: {
                    field: value
                    for field, value in result.model_dump().items()
                    if field not in ("bootstrap_confidence_95", "parameter_correlation")
                }
                for key, result in report.fit_results.items()
            },
            indent=2,
            default=str,
        )
    )
    convergence_json = escape(
        json.dumps(
            convergence_summary_json(report.convergence) if report.convergence else {},
            indent=2,
            default=str,
        )
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QResAudit Report — {escape(Path(report.bundle_path).name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 12px; border-bottom: 1px solid #ddd; }}
  th {{ background: #f5f5f5; }}
  .summary {{ display: flex; gap: 2rem; margin: 1rem 0; }}
  .stat {{ text-align: center; }}
  .stat .value {{ font-size: 2rem; font-weight: bold; }}
  .pass {{ color: #28a745; }} .warn {{ color: #ffc107; }} .fail {{ color: #dc3545; }}
</style>
</head>
<body>
<h1>QResAudit Report</h1>
<p>Bundle: <code>{escape(report.bundle_path)}</code><br>
Audit: {report.audit_timestamp_utc.isoformat()}<br>
Schema: {escape(report.schema_version)}<br>
Overall: {_badge(overall)}<br>
Evidence score: {evidence_score:.1f}% of evaluated checks passed</p>

<div class="summary">
  <div class="stat"><div class="value pass">{n_pass}</div><div>PASS</div></div>
  <div class="stat"><div class="value warn">{n_warn}</div><div>WARNING</div></div>
  <div class="stat"><div class="value fail">{n_fail}</div><div>FAIL</div></div>
  <div class="stat"><div class="value">{n_na}</div><div>NOT EVALUATED</div></div>
</div>

<h2>Verdicts</h2>
<table>
<thead><tr><th>Section</th><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>Fit Results</h2>
<pre>{fit_json}</pre>

<h2>Convergence</h2>
<pre>{convergence_json}</pre>

<p><em>Generated by QResAudit v{report.auditor_version}</em></p>
</body>
</html>"""


def render_audit_markdown(report: AuditReport) -> str:
    """Render a Markdown summary of the audit report."""
    lines = [
        f"# QResAudit Report — `{Path(report.bundle_path).name}`",
        "",
        f"- **Audit time**: {report.audit_timestamp_utc.isoformat()}",
        f"- **Schema**: {report.schema_version}",
        "",
        "## Verdicts",
        "",
        "| Section | Check | Result | Detail |",
        "|---------|-------|--------|--------|",
    ]
    for v in report.verdicts:
        values = [v.section, v.check, v.result, v.detail]
        escaped_values = [
            value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ") for value in values
        ]
        lines.append(f"| {' | '.join(escaped_values)} |")
    return "\n".join(lines) + "\n"


def write_audit_output(report: AuditReport, output_dir: Path) -> None:
    """Write audit report files to an output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    (output_dir / "audit.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    # HTML
    (output_dir / "report.html").write_text(
        render_audit_html(report),
        encoding="utf-8",
    )

    # Markdown
    (output_dir / "summary.md").write_text(
        render_audit_markdown(report),
        encoding="utf-8",
    )

    # Diagnostics CSV
    if report.diagnostics_raw:
        import pandas as pd

        diag_df = pd.DataFrame([d.model_dump() for d in report.diagnostics_raw])
        diag_df.to_csv(output_dir / "diagnostics.csv", index=False)

    (output_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (output_dir / "plots").mkdir(parents=True, exist_ok=True)

    # Convergence CSV
    if report.convergence and report.convergence.passes:
        from qresaudit.analysis.convergence import convergence_to_dataframe

        conv_df = convergence_to_dataframe(report.convergence)
        conv_df.to_csv(output_dir / "analysis" / "convergence.csv", index=False)
        (output_dir / "analysis" / "convergence.json").write_text(
            json.dumps(convergence_summary_json(report.convergence), indent=2) + "\n",
            encoding="utf-8",
        )
