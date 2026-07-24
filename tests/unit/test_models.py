from pathlib import Path

import pytest
from pydantic import ValidationError

from qresaudit.models.config import ExportConfig, FieldGridConfig, ProjectConfig, SolutionConfig


def test_external_models_forbid_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        ExportConfig.model_validate(
            {
                "project": {"path": "x.aedt", "design": "D"},
                "solution": {"setup": "S"},
                "misspelled": True,
            }
        )


def test_modes_are_positive_and_unique() -> None:
    with pytest.raises(ValidationError):
        SolutionConfig(setup="S", modes=[1, 1])
    with pytest.raises(ValidationError):
        SolutionConfig(setup="S", modes=[0])


def test_student_requires_graphical_mode() -> None:
    with pytest.raises(ValidationError):
        ProjectConfig(path=Path("x.aedt"), design="D", student_version=True, non_graphical=True)


def test_missing_sample_point_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="existing file"):
        FieldGridConfig(sample_points_file=tmp_path / "missing.pts")
