from __future__ import annotations

import shutil
from pathlib import Path

from qresaudit.analysis.audit import audit_bundle
from qresaudit.analysis.convergence import audit_convergence

ROOT = Path(__file__).resolve().parents[2]


def _bundle_with_convergence(tmp_path: Path, fixture: str) -> Path:
    source = ROOT / "testdata" / "synthetic" / fixture
    bundle = tmp_path / fixture
    shutil.copytree(source, bundle)
    (bundle / "convergence" / "adaptive_passes.csv").write_text(
        "pass_number,frequency_hz,max_delta_s_percent,converged,raw_evidence_path\n"
        "1,,4.0,False,raw.prof\n"
        "2,,0.08,False,raw.prof\n"
        "3,,0.04,True,raw.prof\n",
        encoding="utf-8",
    )
    return bundle


def test_eigenmode_does_not_apply_driven_delta_s_false_convergence(
    tmp_path: Path,
) -> None:
    bundle = _bundle_with_convergence(tmp_path, "valid_eigenmode_minimal")
    result = audit_convergence(bundle)
    assert result.is_converged
    assert result.false_convergence_risk == "not_evaluated"

    report = audit_bundle(bundle)
    verdict = next(item for item in report.verdicts if item.check == "is_converged")
    assert "delta-frequency %=0.04" in verdict.detail
    assert not any(item.check == "false_convergence" for item in report.verdicts)


def test_driven_modal_keeps_delta_s_false_convergence_check(tmp_path: Path) -> None:
    bundle = _bundle_with_convergence(tmp_path, "valid_driven_minimal")
    result = audit_convergence(bundle)
    assert result.is_converged
    assert result.false_convergence_risk == "high"
