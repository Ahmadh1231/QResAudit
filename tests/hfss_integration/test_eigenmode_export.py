from pathlib import Path

import pytest

from qresaudit.io.bundle import load_manifest
from qresaudit.models.common import FieldRepresentation, SolutionKind


@pytest.mark.hfss
def test_eigenmode_export(eigenmode_bundle: Path) -> None:
    manifest = load_manifest(eigenmode_bundle / "manifest.json")
    assert manifest.solution_kind is SolutionKind.EIGENMODE
    assert manifest.eigenmode is not None
    assert manifest.fields
    assert all(
        field.representation in {FieldRepresentation.REAL_GAUGE, FieldRepresentation.COMPLEX_PHASOR}
        for field in manifest.fields
    )
