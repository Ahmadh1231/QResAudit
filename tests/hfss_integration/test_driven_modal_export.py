from pathlib import Path

import pytest

from qresaudit.io.bundle import load_manifest
from qresaudit.models.common import SolutionKind


@pytest.mark.hfss
def test_driven_modal_export(driven_bundle: Path) -> None:
    manifest = load_manifest(driven_bundle / "manifest.json")
    assert manifest.solution_kind is SolutionKind.DRIVEN_MODAL
    assert manifest.touchstone is not None
    assert manifest.touchstone.number_of_ports >= 1
    assert all(field.frequency_hz is not None for field in manifest.fields)
    assert all(field.excitation for field in manifest.fields)
