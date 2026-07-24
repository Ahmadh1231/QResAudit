import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from qresaudit.models.config import (
    AngularUnit,
    FieldExportConfig,
    FieldGridConfig,
)
from qresaudit_hfss.adapters import driven as driven_module
from qresaudit_hfss.adapters.driven import DrivenAdapter


def _field(tmp_path: Path, *, excitation: str, phase: float = 0.0) -> FieldExportConfig:
    return FieldExportConfig(
        name="device",
        quantity="E",
        excitation=excitation,
        frequency_hz=6.0e9,
        phase_deg=phase,
        phase_unit=AngularUnit.RADIANS,
        grid=FieldGridConfig(
            start=["0m", "0m", "0m"],
            stop=["1m", "0m", "0m"],
            step=["1m", "1m", "1m"],
        ),
    )


def test_driven_field_rejects_unknown_excitation(tmp_path: Path) -> None:
    config = SimpleNamespace(
        fields=[_field(tmp_path, excitation="Missing")],
        solution=SimpleNamespace(setup="Setup1", sweep="Sweep1", variation={}),
    )
    app = SimpleNamespace(
        excitation_names=["Port1"],
        modeler=SimpleNamespace(model_units="m"),
    )
    adapter = DrivenAdapter(app, config, SimpleNamespace())

    with pytest.raises(ValueError, match="EXCITATION_NOT_FOUND"):
        adapter.export_fields(tmp_path)


def test_driven_preflight_rejects_disabled_touchstone() -> None:
    config = SimpleNamespace(
        touchstone=SimpleNamespace(enabled=False),
        fields=[],
        export_convergence=False,
        export_mesh_stats=False,
        export_profile=False,
        export_mesh_visualization=False,
        solution=SimpleNamespace(setup="Setup1", sweep="Sweep1"),
    )
    capabilities = SimpleNamespace(
        has_export_touchstone=True,
        has_fields_calculator_export=True,
        has_export_convergence=True,
        has_export_mesh_stats=True,
        has_export_profile=True,
        has_export_mesh_obj=True,
    )
    adapter = DrivenAdapter(SimpleNamespace(), config, capabilities)

    assert {item.code for item in adapter.preflight()} == {"DRIVEN_TOUCHSTONE_REQUIRED"}


def test_radian_phase_is_recorded_in_degrees(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, str] = {}

    def fake_export(
        app: object,
        field: object,
        solution: str,
        variation: object,
        path: Path,
        intrinsics: dict[str, str],
    ) -> Path:
        captured.update(intrinsics)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("0 0 0 1 0 0\n1 0 0 2 0 0\n", encoding="utf-8")
        return path

    monkeypatch.setattr(driven_module, "export_field", fake_export)
    config = SimpleNamespace(
        fields=[_field(tmp_path, excitation="Port1", phase=math.pi / 2)],
        solution=SimpleNamespace(setup="Setup1", sweep="Sweep1", variation={}),
    )
    app = SimpleNamespace(
        excitation_names=["Port1"],
        modeler=SimpleNamespace(model_units="m"),
    )
    adapter = DrivenAdapter(app, config, SimpleNamespace())

    _, fields = adapter.export_fields(tmp_path)

    assert captured["Phase"].endswith("rad")
    assert fields[0].phase_deg == pytest.approx(90.0)
