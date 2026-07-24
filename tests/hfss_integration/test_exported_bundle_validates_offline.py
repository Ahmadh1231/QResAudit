from pathlib import Path

import pytest

from qresaudit.validation import validate_bundle


@pytest.mark.hfss
@pytest.mark.parametrize("fixture_name", ["driven_bundle", "eigenmode_bundle"])
def test_exported_bundle_validates_offline(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    bundle = request.getfixturevalue(fixture_name)
    assert isinstance(bundle, Path)
    result = validate_bundle(bundle)
    assert result.valid, result.diagnostics
