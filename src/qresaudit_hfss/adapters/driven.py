import json
from pathlib import Path
from typing import Any

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5
from qresaudit.io.touchstone import load_network, network_metadata, write_s_parameter_csv
from qresaudit.models.common import Diagnostic, NormalizationKind
from qresaudit.models.manifest import EigenmodeRecord, FieldRecord, FileRecord, TouchstoneRecord
from qresaudit_hfss.adapters.common import evidence_records, file_record
from qresaudit_hfss.exports.fields import export_field
from qresaudit_hfss.exports.touchstone import export_touchstone


class DrivenAdapter:
    def __init__(self, app: Any, config: Any, capabilities: Any) -> None:
        self.app, self.config, self.capabilities = app, config, capabilities
        self.solution_reference = f"{config.solution.setup} : {config.solution.sweep}"

    def preflight(self) -> list[Diagnostic]:
        return []

    def export_primary_results(
        self, staging: Path
    ) -> tuple[list[FileRecord], TouchstoneRecord | None, EigenmodeRecord | None]:
        target = staging / "network" / f"network.s{len(self.app.excitation_names)}p"
        exported = export_touchstone(self.app, self.config, target)
        network = load_network(exported)
        ports = [str(value) for value in self.app.excitation_names]
        metadata = network_metadata(network, target.relative_to(staging).as_posix(), ports)
        metadata["renormalized"] = self.config.touchstone.renormalize
        metadata["reference_impedance_ohm"] = (
            self.config.touchstone.impedance_ohm or metadata["reference_impedance_ohm"]
        )
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
        return records, TouchstoneRecord.model_validate(metadata), None

    def export_evidence(self, staging: Path) -> list[FileRecord]:
        return evidence_records(self.app, self.config, staging)

    def export_fields(self, staging: Path) -> tuple[list[FileRecord], list[FieldRecord]]:
        files: list[FileRecord] = []
        fields: list[FieldRecord] = []
        for field in self.config.fields:
            raw = staging / "fields" / "raw" / f"{field.name}_{field.quantity}.fld"
            exported = export_field(
                self.app,
                field,
                self.solution_reference,
                self.config.solution.variation,
                raw,
                {"Phase": f"{field.phase_deg or 0}deg"},
            )
            parsed = parse_field_tab(
                exported,
                quantity=field.quantity,
                value_units="A/m" if field.quantity == "H" else "V/m",
            )
            if not parsed.is_complex:
                raise ValueError("EXPORT_COMPLEX_FIELD_UNAVAILABLE")
            h5 = staging / "fields" / "hdf5" / f"{field.name}_{field.quantity}.h5"
            normalization = NormalizationKind.DRIVEN_EXCITATION_DEPENDENT
            metadata = {
                "grid_type": field.grid.type,
                "grid_shape": [len(parsed.coordinates_m)],
                "coordinate_system": field.reference_coordinate_system,
                "solution_reference": self.solution_reference,
                "setup_name": self.config.solution.setup,
                "sweep_name": self.config.solution.sweep,
                "phase_deg": field.phase_deg,
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
                    complex_data=True,
                    vector=parsed.is_vector,
                    units=parsed.value_units,
                    coordinate_units="m",
                    coordinate_system=field.reference_coordinate_system,
                    grid_type=field.grid.type,
                    region_name=field.name,
                    assignment=field.assignment,
                    object_type=field.object_type,
                    solution=self.solution_reference,
                    phase_deg=field.phase_deg,
                    normalization=normalization,
                    shape=list(parsed.values.shape),
                    point_count=len(parsed.coordinates_m),
                )
            )
        return files, fields
