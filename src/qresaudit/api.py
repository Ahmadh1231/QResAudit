"""Stable, local-only public API for QResAudit 2.x."""

from pathlib import Path

from qresaudit.analysis.audit import AuditReport, audit_bundle, write_audit_output
from qresaudit.analysis.fitting import ResonatorFitResult, fit_bundle_resonator
from qresaudit.io.bundle import load_manifest
from qresaudit.models.manifest import HFSSRunManifest
from qresaudit.validation.engine import ValidationResult
from qresaudit.validation.engine import validate_bundle as _validate_bundle

__all__ = ["analyze_resonator", "generate_report", "load_bundle", "validate_bundle"]


def validate_bundle(bundle: str | Path) -> ValidationResult:
    """Validate an evidence bundle without contacting any external service."""
    return _validate_bundle(Path(bundle))


def load_bundle(bundle: str | Path, *, require_valid: bool = True) -> HFSSRunManifest:
    """Load a manifest and optionally require full evidence validation first."""
    root = Path(bundle)
    if require_valid:
        result = _validate_bundle(root)
        if not result.valid:
            codes = ", ".join(sorted({item.code for item in result.diagnostics}))
            raise ValueError(f"bundle validation failed: {codes}")
    return load_manifest(root / "manifest.json")


def analyze_resonator(
    bundle: str | Path,
    *,
    response: str = "S21",
    model: str = "notch",
    require_valid: bool = True,
    use_bootstrap: bool = False,
) -> ResonatorFitResult:
    """Fit a resonator trace from a local bundle after optional validation."""
    root = Path(bundle)
    if require_valid:
        load_bundle(root, require_valid=True)
    return fit_bundle_resonator(
        root,
        response=response,
        model=model,
        use_bootstrap=use_bootstrap,
    )


def generate_report(
    bundle: str | Path,
    output: str | Path,
    *,
    regions: str | Path | None = None,
    fit_model: str = "notch",
    require_valid: bool = True,
) -> Path:
    """Generate local HTML, JSON, Markdown, and CSV audit artifacts."""
    root = Path(bundle)
    if require_valid:
        load_bundle(root, require_valid=True)
    report: AuditReport = audit_bundle(
        root,
        regions_path=Path(regions) if regions is not None else None,
        fit_model=fit_model,
    )
    destination = Path(output)
    write_audit_output(report, destination)
    return destination / "report.html"
