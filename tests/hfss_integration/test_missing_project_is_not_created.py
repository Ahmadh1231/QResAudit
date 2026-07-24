from pathlib import Path

import pytest

from qresaudit.exceptions import HFSSSessionError
from qresaudit.models.config import ProjectConfig
from qresaudit_hfss.session import open_hfss_session


@pytest.mark.hfss
def test_missing_project_is_not_created(tmp_path: Path) -> None:
    project = tmp_path / "must_not_be_created.aedt"
    config = ProjectConfig(path=project, design="Missing")
    with (
        pytest.raises(HFSSSessionError, match="HFSS_PROJECT_OPEN_FAILED"),
        open_hfss_session(config),
    ):
        pass
    assert not project.exists()
