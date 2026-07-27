"""End-to-end checks for the public synthetic resonator demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qresaudit.api import analyze_resonator, generate_report, validate_bundle
from qresaudit.io.bundle import load_manifest

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "demo_resonator"
BUNDLE = DEMO / "bundle"


def test_demo_is_explicitly_synthetic_and_strictly_valid() -> None:
    expected = json.loads((DEMO / "expected_output.json").read_text(encoding="utf-8"))
    manifest = load_manifest(BUNDLE / "manifest.json")

    assert "synthetic" in expected["classification"]
    assert "analytic synthetic" in manifest.design_type
    assert manifest.aedt_version == "not used"
    assert validate_bundle(BUNDLE, strict=True).valid


def test_demo_recovers_declared_resonator_parameters() -> None:
    expected = json.loads((DEMO / "expected_output.json").read_text(encoding="utf-8"))["fit"]
    result = analyze_resonator(BUNDLE)

    assert result.optimizer_converged
    assert result.f0_hz == pytest.approx(
        expected["frequency_hz"], rel=expected["frequency_tolerance_fraction"]
    )
    assert result.q_loaded == pytest.approx(
        expected["q_loaded"], rel=expected["q_loaded_tolerance_fraction"]
    )
    assert result.q_coupling_absolute == pytest.approx(
        expected["q_coupling"], rel=expected["q_coupling_tolerance_fraction"]
    )
    assert result.q_internal == pytest.approx(
        expected["q_internal"], rel=expected["q_internal_tolerance_fraction"]
    )


def test_demo_generates_a_complete_local_report(tmp_path: Path) -> None:
    report = generate_report(BUNDLE, tmp_path / "report")

    assert report.is_file()
    assert (report.parent / "audit.json").is_file()
    assert (report.parent / "summary.md").is_file()
    assert "QResAudit Report" in report.read_text(encoding="utf-8")
