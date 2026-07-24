from pathlib import Path

import pytest

from qresaudit.validation import validate_bundle

ROOT = Path(__file__).resolve().parents[2] / "testdata" / "synthetic"


@pytest.mark.parametrize("name", ["valid_driven_minimal", "valid_eigenmode_minimal"])
def test_valid_bundles(name: str) -> None:
    result = validate_bundle(ROOT / name)
    assert result.valid, result.diagnostics


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("corrupt_checksum", "VALIDATION_CHECKSUM_MISMATCH"),
        ("missing_normalization", "VALIDATION_FIELD_NORMALIZATION_MISSING"),
        ("port_mismatch", "VALIDATION_TOUCHSTONE_PORT_MISMATCH"),
        ("field_shape_mismatch", "VALIDATION_FIELD_SHAPE_MISMATCH"),
        ("unknown_unit", "VALIDATION_UNKNOWN_UNIT"),
        ("partial_bundle", "VALIDATION_BUNDLE_INCOMPLETE"),
    ],
)
def test_invalid_bundles(name: str, code: str) -> None:
    result = validate_bundle(ROOT / name)
    assert not result.valid
    assert code in {item.code for item in result.diagnostics}
