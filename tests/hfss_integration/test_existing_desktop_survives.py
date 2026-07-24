import os
from pathlib import Path

import pytest

from qresaudit_hfss.exporter import load_config
from qresaudit_hfss.session import open_hfss_session


def process_exists(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except OSError:
        return False
    return True


@pytest.mark.hfss
def test_existing_desktop_survives(driven_config_path: Path) -> None:
    raw_process_id = os.environ.get("QRESAUDIT_HFSS_EXISTING_PROCESS_ID")
    if not raw_process_id:
        pytest.skip("QRESAUDIT_HFSS_EXISTING_PROCESS_ID is required")
    process_id = int(raw_process_id)
    config = load_config(driven_config_path)
    config.project.attach_process_id = process_id
    with open_hfss_session(config.project):
        assert process_exists(process_id)
    assert process_exists(process_id)
