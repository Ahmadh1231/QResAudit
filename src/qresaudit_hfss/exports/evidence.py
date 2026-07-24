from pathlib import Path
from typing import Any

from qresaudit.exceptions import ExportError
from qresaudit.models.config import ExportConfig


def export_evidence(app: Any, config: ExportConfig, staging: Path) -> list[tuple[Path, str, bool]]:
    variation = config.solution.variation or None
    outputs: list[tuple[Path, str, bool]] = []
    operations = [
        (
            config.export_convergence,
            "convergence_raw.prof",
            "convergence_raw",
            app.export_convergence,
        ),
        (
            config.export_mesh_stats,
            "mesh_stats_raw.txt",
            "mesh_stats_raw",
            app.export_mesh_stats,
        ),
        (config.export_profile, "solver_profile.prof", "profile", app.export_profile),
    ]
    for enabled, name, role, method in operations:
        if not enabled:
            continue
        target = staging / "convergence" / name
        try:
            result = method(config.solution.setup, variation, str(target))
        except TypeError:
            result = method(
                setup=config.solution.setup, variations=variation, output_file=str(target)
            )
        if not result:
            raise ExportError(f"EXPORT_{role.upper()}_FAILED")
        outputs.append((target, role, role in {"convergence_raw", "mesh_stats_raw"}))
    if config.export_mesh_visualization:
        target = staging / "mesh" / "mesh.aedtplt"
        result = app.post.export_mesh_obj(
            setup=config.solution.setup,
            intrinsics="",
            export_air_objects=False,
            on_surfaces=True,
            file_name=str(target),
        )
        if result:
            outputs.append((target, "mesh_visualization", False))
    return outputs
