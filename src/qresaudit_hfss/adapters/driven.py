import json
import math
from pathlib import Path
from typing import Any

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5
from qresaudit.io.touchstone import load_network, network_metadata, write_s_parameter_csv
from qresaudit.models.common import Diagnostic, FieldRepresentation, NormalizationKind, error
from qresaudit.models.manifest import EigenmodeRecord, FieldRecord, FileRecord, TouchstoneRecord
from qresaudit_hfss.adapters.common import evidence_records, file_record
from qresaudit_hfss.exports.fields import export_field
from qresaudit_hfss.exports.touchstone import export_touchstone
from qresaudit_hfss.inspect import (
    field_grid_axes,
    field_grid_shape,
    field_source_coordinate_units,
)


class DrivenAdapter:
    def __init__(self, app: Any, config: Any, capabilities: Any) -> None:
        self.app, self.config, self.capabilities = app, config, capabilities
        self.solution_reference = f"{config.solution.setup} : {config.solution.sweep}"

    def preflight(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if not self.config.touchstone.enabled:
            diagnostics.append(
                error(
                    "DRIVEN_TOUCHSTONE_REQUIRED",
                    "Driven evidence bundles require Touchstone export",
                )
            )
        elif not self.capabilities.has_export_touchstone:
            diagnostics.append(error("HFSS_CAPABILITY_TOUCHSTONE_MISSING", "export_touchstone"))
        if self.config.fields and not self.capabilities.has_fields_calculator_export:
            diagnostics.append(error("HFSS_CAPABILITY_FIELD_EXPORT_MISSING", "fields_calculator"))
        diagnostics.extend(_evidence_capability_diagnostics(self.config, self.capabilities))
        return diagnostics

    def export_primary_results(
        self, staging: Path
    ) -> tuple[list[FileRecord], TouchstoneRecord | None, EigenmodeRecord | None]:
        source_network = None
        source_exported = None
        if self.config.touchstone.renormalize:
            source_temporary = (
                staging
                / "network"
                / f"source_normalization_export.s{len(self.app.excitation_names)}p"
            )
            source_exported = export_touchstone(
                self.app,
                self.config,
                source_temporary,
                renormalization=False,
                impedance_ohm=None,
            )
            source_network = load_network(source_exported)
            source_target = staging / "network" / f"source_normalization.s{source_network.nports}p"
            if source_exported != source_target:
                source_exported.replace(source_target)
                source_exported = source_target
        temporary = staging / "network" / f"network_export.s{len(self.app.excitation_names)}p"
        exported = export_touchstone(self.app, self.config, temporary)
        network = load_network(exported)
        target = staging / "network" / f"network.s{network.nports}p"
        if exported != target:
            exported.replace(target)
            exported = target
        ports = [str(value) for value in self.app.excitation_names]
        metadata = network_metadata(network, target.relative_to(staging).as_posix(), ports)
        metadata["renormalized"] = self.config.touchstone.renormalize
        metadata["renormalization_impedance_ohm"] = (
            self.config.touchstone.impedance_ohm if self.config.touchstone.renormalize else None
        )
        metadata["source_impedance_preserved"] = not self.config.touchstone.renormalize
        if source_network is not None and source_exported is not None:
            source_z0 = source_network.z0
            metadata["source_impedance_preserved"] = True
            metadata["source_impedance_path"] = source_exported.relative_to(staging).as_posix()
            metadata["source_reference_impedance_real_ohm"] = source_z0.real.tolist()
            metadata["source_reference_impedance_imag_ohm"] = source_z0.imag.tolist()
        metadata_path = staging / "network" / "network_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        csv_path = write_s_parameter_csv(network, staging / "reports" / "s_parameters.csv")
        records = [
            file_record(exported, staging, "touchstone", True),
            file_record(metadata_path, staging, "network_metadata", True),
            file_record(
                csv_path,
                staging,
                "s_parameters",
                True,
                source_path=target.relative_to(staging).as_posix(),
            ),
        ]
        if source_exported is not None:
            records.append(
                file_record(
                    source_exported,
                    staging,
                    "touchstone_source_normalization",
                    True,
                )
            )
        return records, TouchstoneRecord.model_validate(metadata), None

    def export_evidence(self, staging: Path) -> list[FileRecord]:
        return evidence_records(self.app, self.config, staging)

    def export_fields(self, staging: Path) -> tuple[list[FileRecord], list[FieldRecord]]:
        files: list[FileRecord] = []
        fields: list[FieldRecord] = []
        for field in self.config.fields:
            if field.frequency_hz is None or not field.excitation:
                raise ValueError("EXPORT_DRIVEN_FIELD_CONTEXT_REQUIRED")
            excitation_names = {str(name) for name in self.app.excitation_names}
            if field.excitation not in excitation_names:
                raise ValueError(
                    f"EXPORT_FIELD_EXCITATION_NOT_FOUND: {field.excitation!r} is not one of "
                    f"{sorted(excitation_names)!r}"
                )
            phase_deg = (
                math.degrees(field.phase_deg)
                if field.phase_unit.value == "rad" and field.phase_deg is not None
                else field.phase_deg
            )
            raw = staging / "fields" / "raw" / f"{field.name}_{field.quantity}.fld"
            exported = export_field(
                self.app,
                field,
                self.solution_reference,
                self.config.solution.variation,
                raw,
                {
                    "Phase": f"{field.phase_deg or 0}{field.phase_unit.value}",
                    "Freq": f"{field.frequency_hz}Hz",
                    "Excitation": field.excitation,
                },
            )
            parsed = parse_field_tab(
                exported,
                quantity=field.quantity,
                value_units=field.value_units,
                coordinate_units=field_source_coordinate_units(
                    field,
                    str(self.app.modeler.model_units),
                ),
            )
            h5 = staging / "fields" / "hdf5" / f"{field.name}_{field.quantity}.h5"
            normalization = NormalizationKind.DRIVEN_EXCITATION_DEPENDENT
            metadata = {
                "grid_type": field.grid.type.value,
                "topology": "unstructured"
                if field.grid.sample_points_file is not None
                else "structured",
                "shape": field_grid_shape(field) or [len(parsed.coordinates_m)],
                "axes": field_grid_axes(field),
                "axis_order": ["x", "y", "z"],
                "flattening_order": "C",
                "coordinate_system": field.reference_coordinate_system,
                "solution_reference": self.solution_reference,
                "setup_name": self.config.solution.setup,
                "sweep_name": self.config.solution.sweep,
                "phase_deg": phase_deg,
                "frequency_hz": field.frequency_hz,
                "excitation": field.excitation,
                "excitation_context": {
                    "name": field.excitation,
                    "frequency_hz": field.frequency_hz,
                    "phase_deg": phase_deg,
                    "variation": self.config.solution.variation,
                },
                "representation": (
                    field.representation.value
                    if field.representation is not None
                    else ("complex_phasor" if parsed.is_complex else "phase_evaluated_real")
                ),
                "phasor_convention": field.phasor_convention.value,
                "normalization": normalization.value,
                "region_name": field.name,
                "assignments_json": field.assignment,
                **source_metadata(exported),
            }
            write_field_hdf5(h5, parsed, metadata)
            files.extend(
                [
                    file_record(exported, staging, "field_raw", True),
                    file_record(
                        h5,
                        staging,
                        "field_hdf5",
                        True,
                        source_path=exported.relative_to(staging).as_posix(),
                    ),
                ]
            )
            fields.append(
                FieldRecord(
                    path=h5.relative_to(staging).as_posix(),
                    raw_path=exported.relative_to(staging).as_posix(),
                    quantity=field.quantity,
                    complex_data=parsed.is_complex,
                    vector=parsed.is_vector,
                    units=parsed.value_units,
                    coordinate_units="m",
                    coordinate_system=field.reference_coordinate_system,
                    grid_type=field.grid.type.value,
                    region_name=field.name,
                    assignment=field.assignment,
                    object_type=field.object_type.value,
                    solution=self.solution_reference,
                    excitation=field.excitation,
                    phase_deg=phase_deg,
                    frequency_hz=field.frequency_hz,
                    normalization=normalization,
                    shape=[
                        *(metadata["shape"]),
                        *([3] if parsed.is_vector else []),
                    ],
                    point_count=len(parsed.coordinates_m),
                    representation=(
                        field.representation
                        if field.representation is not None
                        else (
                            FieldRepresentation.COMPLEX_PHASOR
                            if parsed.is_complex
                            else FieldRepresentation.PHASE_EVALUATED_REAL
                        )
                    ),
                    phasor_convention=field.phasor_convention,
                    component_labels=["x", "y", "z"] if parsed.is_vector else ["scalar"],
                    topology=metadata["topology"],
                    variation=self.config.solution.variation,
                )
            )
        return files, fields


def _evidence_capability_diagnostics(config: Any, capabilities: Any) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    checks = [
        (config.export_convergence, capabilities.has_export_convergence, "convergence"),
        (config.export_mesh_stats, capabilities.has_export_mesh_stats, "mesh_stats"),
        (config.export_profile, capabilities.has_export_profile, "profile"),
        (
            config.export_mesh_visualization,
            capabilities.has_export_mesh_obj,
            "mesh_visualization",
        ),
    ]
    for enabled, available, name in checks:
        if enabled and not available:
            diagnostics.append(
                error(
                    "HFSS_CAPABILITY_EVIDENCE_EXPORT_MISSING",
                    f"Required PyAEDT capability is unavailable: {name}",
                )
            )
    return diagnostics
