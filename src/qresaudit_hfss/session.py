from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from qresaudit.exceptions import HFSSSessionError
from qresaudit.models.config import ProjectConfig


@contextmanager
def open_hfss_session(config: ProjectConfig) -> Iterator[Any]:
    """Open an existing HFSS design and guarantee desktop cleanup.

    PyAEDT is imported only inside this licensed boundary.
    """
    try:
        from ansys.aedt.core import Hfss
    except ImportError as exc:
        raise HFSSSessionError(
            "PyAEDT is unavailable; install qresaudit[hfss] in an AEDT-compatible environment"
        ) from exc
    app: Any = None
    try:
        app = Hfss(
            project=str(config.path),
            design=config.design,
            version=config.aedt_version,
            non_graphical=config.non_graphical,
            new_desktop=False,
            close_on_exit=True,
            student_version=config.student_version,
            remove_lock=config.remove_lock,
        )
        yield app
    except HFSSSessionError:
        raise
    except Exception as exc:
        raise HFSSSessionError(f"HFSS_PROJECT_OPEN_FAILED: {exc}") from exc
    finally:
        if app is not None:
            with suppress(Exception):
                app.release_desktop(close_projects=False, close_desktop=True)
