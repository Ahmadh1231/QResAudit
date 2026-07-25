"""Compatibility tests for the frozen local-only API and CLI."""

from pathlib import Path

from typer.testing import CliRunner

import qresaudit
from qresaudit.api import load_bundle, validate_bundle
from qresaudit.cli import app

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "testdata" / "synthetic" / "valid_driven_minimal"


def test_package_root_exposes_only_stable_names() -> None:
    assert qresaudit.__all__ == [
        "__version__",
        "analyze_resonator",
        "generate_report",
        "load_bundle",
        "validate_bundle",
    ]


def test_stable_validation_and_loading_are_local() -> None:
    result = validate_bundle(BUNDLE)
    manifest = load_bundle(BUNDLE)

    assert result.valid
    assert manifest.design_name == "Synthetic"


def test_benchmark_cli_returns_machine_readable_success() -> None:
    result = CliRunner().invoke(app, ["benchmark"])

    assert result.exit_code == 0
    assert '"passed": true' in result.stdout
    assert "no solver validation" in result.stdout


def test_analyze_cli_reports_insufficient_trace_without_traceback() -> None:
    result = CliRunner().invoke(app, ["analyze", str(BUNDLE)])

    assert result.exit_code != 0
    assert "at least 16 finite frequency samples" in result.output
    assert "Traceback" not in result.output
