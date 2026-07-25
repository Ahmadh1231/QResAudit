from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from qresaudit.exceptions import HFSSSessionError
from qresaudit.models.config import ProjectConfig


@contextmanager
def open_hfss_session(config: ProjectConfig) -> Iterator[Any]:
    """Open an existing HFSS design with explicit AEDT ownership.

    PyAEDT is imported only inside this licensed boundary.
    """
    if not config.path.is_file() or config.path.suffix.lower() not in {".aedt", ".aedtz"}:
        raise HFSSSessionError(
            "HFSS_PROJECT_OPEN_FAILED: project path must be an existing .aedt/.aedtz file"
        )
    try:
        from ansys.aedt.core import Desktop, Hfss

        # QResAudit owns its CLI output (especially JSON mode). PyAEDT still
        # writes detailed diagnostics to its log files.
        with suppress(ImportError):
            from ansys.aedt.core import settings

            settings.enable_screen_logs = False
    except ImportError as exc:
        raise HFSSSessionError(
            "PyAEDT is unavailable; install qresaudit[hfss] in an AEDT-compatible environment"
        ) from exc
    app: Any = None
    desktop: Any = None
    project_name: str | None = None
    owns_project = False
    owns_desktop = config.attach_process_id is None
    try:
        desktop_options: dict[str, Any] = {
            "version": config.aedt_version,
            "non_graphical": config.non_graphical,
            "new_desktop": owns_desktop,
            "close_on_exit": False,
            "student_version": config.student_version,
        }
        if config.attach_process_id is not None:
            desktop_options["aedt_process_id"] = config.attach_process_id
        desktop = Desktop(
            **desktop_options,
        )
        project = _find_loaded_project(desktop, config.path)
        if project is None:
            project = desktop.odesktop.OpenProject(str(config.path.resolve()))
            owns_project = True
        project_name = str(project.GetName())
        designs = {str(name).split(";")[-1] for name in desktop.design_list(project_name)}
        if config.design not in designs:
            raise HFSSSessionError(
                f"HFSS_DESIGN_NOT_FOUND: design {config.design!r} is not present in "
                f"project {project_name!r}"
            )
        process_id = config.attach_process_id or getattr(
            desktop,
            "aedt_process_id",
            None,
        )
        if process_id is None:
            with suppress(Exception):
                process_id = int(desktop.odesktop.GetProcessID())
        if process_id is None:
            raise HFSSSessionError("HFSS_PROCESS_ID_UNAVAILABLE")
        app_options: dict[str, Any] = {
            "project": project_name,
            "design": config.design,
            "version": config.aedt_version,
            "non_graphical": config.non_graphical,
            "new_desktop": False,
            "close_on_exit": False,
            "student_version": config.student_version,
            "remove_lock": False,
            "aedt_process_id": int(process_id),
        }
        app = Hfss(
            **app_options,
        )
        if str(getattr(app, "project_name", project_name)) != project_name:
            raise HFSSSessionError("HFSS_PROJECT_IDENTITY_MISMATCH")
        if str(getattr(app, "design_name", config.design)) != config.design:
            raise HFSSSessionError("HFSS_DESIGN_IDENTITY_MISMATCH")
        yield app
    except HFSSSessionError:
        raise
    except Exception as exc:
        raise HFSSSessionError(f"HFSS_PROJECT_OPEN_FAILED: {exc}") from exc
    finally:
        # Never close an explicitly attached desktop. A desktop created by this
        # context is closed through the Desktop object itself; releasing the
        # secondary Hfss wrapper can detach without terminating AEDT.
        if desktop is not None:
            if owns_desktop:
                with suppress(Exception):
                    desktop.close_desktop()
            else:
                if owns_project and project_name is not None:
                    with suppress(Exception):
                        desktop.odesktop.CloseProject(project_name)
                with suppress(Exception):
                    desktop.release_desktop(
                        close_projects=False,
                        close_on_exit=False,
                    )


def _find_loaded_project(desktop: Any, project_path: Path) -> Any | None:
    target = project_path.resolve()
    # AEDT reports a saved project's directory and project name separately.
    # An opened .aedtz archive does not retain a trustworthy source-archive
    # identity, so it is never treated as an already-loaded source project.
    if target.suffix.lower() != ".aedt":
        return None
    for name in desktop.project_list:
        try:
            project = desktop.active_project(name)
            reported_directory = desktop.project_path(name)
            if project is None or reported_directory is None:
                continue
            loaded_path = (Path(str(reported_directory)) / f"{project.GetName()}.aedt").resolve()
        except Exception:
            continue
        if loaded_path.is_file() and loaded_path.samefile(target):
            return project
    return None
