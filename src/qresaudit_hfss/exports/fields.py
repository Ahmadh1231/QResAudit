from pathlib import Path
from typing import Any

from qresaudit.exceptions import ExportError
from qresaudit.models.config import FieldExportConfig


def export_field(
    app: Any,
    field: FieldExportConfig,
    solution_reference: str,
    variation: dict[str, str],
    output_file: Path,
    intrinsics: dict[str, str],
) -> Path:
    result = app.post.fields_calculator.export(
        quantity=field.quantity,
        solution=solution_reference,
        variations=variation,
        output_file=str(output_file),
        intrinsics=intrinsics,
        sample_points=str(field.grid.sample_points_file) if field.grid.sample_points_file else None,
        export_with_sample_points=True,
        reference_coordinate_system=field.reference_coordinate_system,
        export_in_si_system=field.export_in_si_system,
        export_field_in_reference=field.export_field_in_reference,
        grid_type=None if field.grid.sample_points_file else field.grid.type.value,
        grid_center=field.grid.center,
        grid_start=field.grid.start,
        grid_stop=field.grid.stop,
        grid_step=field.grid.step,
        is_vector=field.vector,
        assignment=field.assignment,
        objects_type=field.object_type.value,
    )
    if not result:
        raise ExportError("EXPORT_FIELD_FAILED")
    return Path(result)
