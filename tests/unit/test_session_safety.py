import sys
import types
from pathlib import Path

import pytest

from qresaudit.exceptions import HFSSSessionError
from qresaudit.models.config import ProjectConfig
from qresaudit_hfss.session import open_hfss_session


def test_missing_project_fails_before_hfss_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed = False

    class FakeHfss:
        def __init__(self, **kwargs: object) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setitem(sys.modules, "ansys", types.ModuleType("ansys"))
    aedt = types.ModuleType("ansys.aedt")
    core = types.ModuleType("ansys.aedt.core")
    core.Hfss = FakeHfss  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys.aedt", aedt)
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", core)
    config = ProjectConfig(path=Path("missing.aedt"), design="D")
    with (
        pytest.raises(HFSSSessionError, match="HFSS_PROJECT_OPEN_FAILED"),
        open_hfss_session(config),
    ):
        pass
    assert not constructed


def test_missing_design_fails_before_hfss_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    constructed = False
    closed: list[str] = []
    desktop_closed = False

    class FakeProject:
        def GetName(self) -> str:
            return "project"

    class FakeODesktop:
        def OpenProject(self, path: str) -> FakeProject:
            assert Path(path).is_file()
            return FakeProject()

        def CloseProject(self, name: str) -> None:
            closed.append(name)

    class FakeDesktop:
        aedt_process_id = 456

        def __init__(self, **kwargs: object) -> None:
            self.odesktop = FakeODesktop()
            self.project_list: list[str] = []

        def design_list(self, project: str) -> list[str]:
            assert project == "project"
            return ["HFSS;ExistingDesign"]

        def release_desktop(self, *, close_projects: bool, close_on_exit: bool) -> None:
            assert not close_projects
            assert not close_on_exit

        def close_desktop(self) -> None:
            nonlocal desktop_closed
            desktop_closed = True

    class FakeHfss:
        def __init__(self, **kwargs: object) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setitem(sys.modules, "ansys", types.ModuleType("ansys"))
    aedt = types.ModuleType("ansys.aedt")
    core = types.ModuleType("ansys.aedt.core")
    core.Desktop = FakeDesktop  # type: ignore[attr-defined]
    core.Hfss = FakeHfss  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys.aedt", aedt)
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", core)
    project = tmp_path / "project.aedt"
    project.write_bytes(b"existing project")
    config = ProjectConfig(path=project, design="MissingDesign")

    with pytest.raises(HFSSSessionError, match="HFSS_DESIGN_NOT_FOUND"), open_hfss_session(config):
        pass

    assert not constructed
    assert closed == []
    assert desktop_closed


def test_existing_desktop_and_project_remain_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, object]] = []
    project_path = tmp_path / "project.aedt"
    project_path.write_bytes(b"existing project")

    class FakeProject:
        def GetName(self) -> str:
            return "project"

    class FakeODesktop:
        def OpenProject(self, path: str) -> FakeProject:
            raise AssertionError("already-loaded project must not be reopened")

        def CloseProject(self, name: str) -> None:
            calls.append(("close_project", name))

    class FakeDesktop:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("desktop", kwargs))
            self.odesktop = FakeODesktop()
            self.project_list = ["project"]

        def project_path(self, name: str) -> str:
            return str(tmp_path)

        def active_project(self, name: str) -> FakeProject:
            return FakeProject()

        def design_list(self, project: str) -> list[str]:
            return ["HFSS;Design"]

        def release_desktop(self, *, close_projects: bool, close_on_exit: bool) -> None:
            calls.append(("release", (close_projects, close_on_exit)))

        def close_desktop(self) -> None:
            calls.append(("close_desktop", None))

    class FakeHfss:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("hfss", kwargs))

    monkeypatch.setitem(sys.modules, "ansys", types.ModuleType("ansys"))
    monkeypatch.setitem(sys.modules, "ansys.aedt", types.ModuleType("ansys.aedt"))
    core = types.ModuleType("ansys.aedt.core")
    core.Desktop = FakeDesktop  # type: ignore[attr-defined]
    core.Hfss = FakeHfss  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", core)
    config = ProjectConfig(path=project_path, design="Design", attach_process_id=123)

    with open_hfss_session(config):
        pass

    assert not any(name == "close_project" for name, _ in calls)
    assert ("release", (False, False)) in calls
    desktop_options = next(value for name, value in calls if name == "desktop")
    assert isinstance(desktop_options, dict)
    assert desktop_options["new_desktop"] is False
    assert desktop_options["aedt_process_id"] == 123


def test_project_opened_in_attached_desktop_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, object]] = []
    project_path = tmp_path / "project.aedtz"
    project_path.write_bytes(b"existing archive")

    class FakeProject:
        def GetName(self) -> str:
            return "loaded_project"

    class FakeODesktop:
        def OpenProject(self, path: str) -> FakeProject:
            calls.append(("open_project", path))
            return FakeProject()

        def CloseProject(self, name: str) -> None:
            calls.append(("close_project", name))

    class FakeDesktop:
        def __init__(self, **kwargs: object) -> None:
            self.odesktop = FakeODesktop()
            self.project_list = ["loaded_project"]

        def project_path(self, name: str) -> str:
            return str(tmp_path)

        def active_project(self, name: str) -> FakeProject:
            raise AssertionError("an .aedtz source must not reuse an in-memory project")

        def design_list(self, project: str) -> list[str]:
            return ["HFSS;Design"]

        def release_desktop(self, *, close_projects: bool, close_on_exit: bool) -> None:
            calls.append(("release", (close_projects, close_on_exit)))

    class FakeHfss:
        project_name = "loaded_project"
        design_name = "Design"

        def __init__(self, **kwargs: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "ansys", types.ModuleType("ansys"))
    monkeypatch.setitem(sys.modules, "ansys.aedt", types.ModuleType("ansys.aedt"))
    core = types.ModuleType("ansys.aedt.core")
    core.Desktop = FakeDesktop  # type: ignore[attr-defined]
    core.Hfss = FakeHfss  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", core)

    with open_hfss_session(
        ProjectConfig(path=project_path, design="Design", attach_process_id=123)
    ):
        pass

    assert ("close_project", "loaded_project") in calls
    assert ("release", (False, False)) in calls


def test_default_session_owns_and_closes_new_desktop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, object]] = []
    project_path = tmp_path / "project.aedt"
    project_path.write_bytes(b"existing project")

    class FakeProject:
        def GetName(self) -> str:
            return "project"

    class FakeODesktop:
        def OpenProject(self, path: str) -> FakeProject:
            return FakeProject()

        def CloseProject(self, name: str) -> None:
            calls.append(("close_project", name))

    class FakeDesktop:
        aedt_process_id = 789

        def __init__(self, **kwargs: object) -> None:
            calls.append(("desktop", kwargs))
            self.odesktop = FakeODesktop()
            self.project_list: list[str] = []

        def design_list(self, project: str) -> list[str]:
            return ["HFSS;Design"]

        def release_desktop(self, *, close_projects: bool, close_on_exit: bool) -> None:
            calls.append(("release", (close_projects, close_on_exit)))

        def close_desktop(self) -> None:
            calls.append(("close_desktop", None))

    class FakeHfss:
        project_name = "project"
        design_name = "Design"

        def __init__(self, **kwargs: object) -> None:
            calls.append(("hfss", kwargs))

    monkeypatch.setitem(sys.modules, "ansys", types.ModuleType("ansys"))
    monkeypatch.setitem(sys.modules, "ansys.aedt", types.ModuleType("ansys.aedt"))
    core = types.ModuleType("ansys.aedt.core")
    core.Desktop = FakeDesktop  # type: ignore[attr-defined]
    core.Hfss = FakeHfss  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", core)

    with open_hfss_session(ProjectConfig(path=project_path, design="Design")):
        pass

    desktop_options = next(value for name, value in calls if name == "desktop")
    assert isinstance(desktop_options, dict)
    assert desktop_options["new_desktop"] is True
    assert not any(name == "close_project" for name, _ in calls)
    assert ("close_desktop", None) in calls


def test_remove_lock_is_rejected_for_read_only_sessions() -> None:
    with pytest.raises(ValueError, match="remove_lock"):
        ProjectConfig(path=Path("project.aedt"), design="D", remove_lock=True)
