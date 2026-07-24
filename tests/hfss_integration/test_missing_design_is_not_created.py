from pathlib import Path

import pytest

from qresaudit.exceptions import HFSSSessionError
from qresaudit_hfss.exporter import load_config
from qresaudit_hfss.session import open_hfss_session


@pytest.mark.hfss
def test_missing_design_is_not_created(driven_config_path: Path) -> None:
    config = load_config(driven_config_path)
    config.project.design = "__QRESAUDIT_MISSING_DESIGN__"
    with (
        pytest.raises(HFSSSessionError, match="HFSS_DESIGN_NOT_FOUND"),
        open_hfss_session(config.project),
    ):
        pass
