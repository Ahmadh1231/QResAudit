import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "check_release_version.py"
SPEC = importlib.util.spec_from_file_location("check_release_version", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

check_release_version = MODULE.check_release_version
normalize_release_tag = MODULE.normalize_release_tag
package_version = MODULE.package_version


def write_pyproject(path: Path, version: str) -> Path:
    pyproject = path / "pyproject.toml"
    pyproject.write_text(
        f'[project]\nname = "qresaudit"\nversion = "{version}"\n', encoding="utf-8"
    )
    return pyproject


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v2.0.0", "2.0.0"),
        ("2.0.0", "2.0.0"),
        ("refs/tags/v2.0.0", "2.0.0"),
    ],
)
def test_normalize_release_tag(tag: str, expected: str) -> None:
    assert normalize_release_tag(tag) == expected


def test_release_tag_must_match_package_version(tmp_path: Path) -> None:
    pyproject = write_pyproject(tmp_path, "2.0.0")
    assert check_release_version("v2.0.0", pyproject) == "2.0.0"
    with pytest.raises(ValueError, match="does not match"):
        check_release_version("v2.0.1", pyproject)


def test_missing_project_version_is_rejected(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "qresaudit"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"project\.version"):
        package_version(pyproject)


def test_empty_release_tag_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_release_tag("v")


def test_publish_workflow_uses_release_only_trusted_publishing() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish-pypi.yml"
    ).read_text(encoding="utf-8")
    assert "types: [published]" in workflow
    assert "workflow_dispatch" not in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "secrets." not in workflow
    assert "password:" not in workflow
