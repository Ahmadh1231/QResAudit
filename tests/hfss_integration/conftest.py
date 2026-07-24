import os
from pathlib import Path

import pytest

from qresaudit_hfss.exporter import export_bundle, load_config


def configured_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"{variable} is required on the licensed HFSS runner")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{variable} does not name an existing file: {path}")
    return path


@pytest.fixture(scope="session")
def driven_config_path() -> Path:
    return configured_path("QRESAUDIT_HFSS_DRIVEN_CONFIG")


@pytest.fixture(scope="session")
def eigenmode_config_path() -> Path:
    return configured_path("QRESAUDIT_HFSS_EIGENMODE_CONFIG")


@pytest.fixture(scope="session")
def driven_bundle(
    driven_config_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    config = load_config(driven_config_path)
    return export_bundle(config, tmp_path_factory.mktemp("hfss") / "driven")


@pytest.fixture(scope="session")
def eigenmode_bundle(
    eigenmode_config_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    config = load_config(eigenmode_config_path)
    return export_bundle(config, tmp_path_factory.mktemp("hfss") / "eigenmode")
