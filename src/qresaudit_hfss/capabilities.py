from importlib import metadata
from typing import Any

from pydantic import BaseModel, ConfigDict


class PyAEDTCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    has_fields_calculator_export: bool
    has_export_touchstone: bool
    has_export_convergence: bool
    has_export_mesh_stats: bool
    has_export_profile: bool
    has_export_mesh_obj: bool


def detect_capabilities(app: Any) -> PyAEDTCapabilities:
    try:
        version = metadata.version("pyaedt")
    except metadata.PackageNotFoundError:
        version = metadata.version("ansys-aedt-core")
    post = app.post
    fields_calculator = getattr(post, "fields_calculator", None)
    return PyAEDTCapabilities(
        version=version,
        has_fields_calculator_export=hasattr(fields_calculator, "export"),
        has_export_touchstone=hasattr(app, "export_touchstone"),
        has_export_convergence=hasattr(app, "export_convergence"),
        has_export_mesh_stats=hasattr(app, "export_mesh_stats"),
        has_export_profile=hasattr(app, "export_profile"),
        has_export_mesh_obj=hasattr(post, "export_mesh_obj"),
    )
