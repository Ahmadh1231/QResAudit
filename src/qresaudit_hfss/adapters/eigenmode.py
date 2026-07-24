from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5
from qresaudit.models.common import Diagnostic, NormalizationKind
from qresaudit.models.manifest import EigenmodeRecord, FieldRecord, FileRecord, TouchstoneRecord
from qresaudit_hfss.adapters.common import evidence_records, file_record
from qresaudit_hfss.exports.fields import export_field


class EigenmodeAdapter:
    def __init__(self, app: Any, config: Any, capabilities: Any) -> None:
        self.app, self.config, self.capabilities = app, config, capabilities
        self.solution_reference = f"{config.solution.setup} : LastAdaptive"
        self.mode_frequencies: dict[int, float] = {}

    def preflight(self) -> list[Diagnostic]:
        return []

    def _mode_data(self) -> pd.DataFrame:
        expressions = ["Eigenmode(Real)", "Eigenmode(Imag)", "Q"]
        data = self.app.post.get_solution_data(
            expressions=expressions,
            setup_sweep_name=self.solution_reference,
            domain="Sweep",
            variations=self.config.solution.variation,
        )
        if not data:
            raise ValueError("EXPORT_EIGENMODE_DATA_FAILED")
        modes = np.asarray(data.primary_sweep_values, dtype=int)
        real = np.asarray(data.data_real(expressions[0]), dtype=float) * 1e9
        try:
            imag = np.asarray(data.data_real(expressions[1]), dtype=float) * 1e9
        except Exception:
            imag = np.zeros_like(real)
        try:
            q_values = np.asarray(data.data_real(expressions[2]), dtype=float)
        except Exception:
            q_values = np.zeros_like(real)
        self.mode_frequencies = {
            int(mode): float(frequency) for mode, frequency in zip(modes, real, strict=True)
        }
        return pd.DataFrame(
            {
                "mode": modes,
                "frequency_real_hz": real,
                "frequency_imag_hz": imag,
                "q_hfss_unloaded": q_values,
                "source_solution": self.solution_reference,
                "variation_id": "nominal",
            }
        )

    def export_primary_results(
        self, staging: Path
    ) -> tuple[list[FileRecord], TouchstoneRecord | None, EigenmodeRecord | None]:
        modes = self._mode_data()
        target = staging / "modes" / "eigenmodes.csv"
        modes.to_csv(target, index=False)
        return (
            [file_record(target, staging, "eigenmodes", True)],
            None,
            EigenmodeRecord(path="modes/eigenmodes.csv", mode_count=len(modes)),
        )

    def export_evidence(self, staging: Path) -> list[FileRecord]:
        return evidence_records(self.app, self.config, staging)

    def export_fields(self, staging: Path) -> tuple[list[FileRecord], list[FieldRecord]]:
        files: list[FileRecord] = []
        fields: list[FieldRecord] = []
        for mode in self.config.solution.modes:
            frequency = self.mode_frequencies[mode]
            for field in self.config.fields:
                raw = (
                    staging
                    / "fields"
                    / "raw"
                    / f"mode_{mode:02d}_{field.quantity}_{field.name}.fld"
                )
                exported = export_field(
                    self.app,
                    field,
                    self.solution_reference,
                    self.config.solution.variation,
                    raw,
                    {"Mode": str(mode), "Phase": f"{field.phase_deg or 0}deg"},
                )
                unit = "A/m" if field.quantity == "H" else "V/m"
                parsed = parse_field_tab(exported, quantity=field.quantity, value_units=unit)
                if not parsed.is_complex:
                    raise ValueError("EXPORT_COMPLEX_FIELD_UNAVAILABLE")
                h5 = (
                    staging
                    / "fields"
                    / "hdf5"
                    / f"mode_{mode:02d}_{field.quantity}_{field.name}.h5"
                )
                normalization = NormalizationKind.HFSS_EIGENMODE_PEAK_1
                metadata = {
                    "grid_type": field.grid.type,
                    "grid_shape": [len(parsed.coordinates_m)],
                    "coordinate_system": field.reference_coordinate_system,
                    "solution_reference": self.solution_reference,
                    "setup_name": self.config.solution.setup,
                    "mode": mode,
                    "frequency_hz": frequency,
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
                        mode=mode,
                        frequency_hz=frequency,
                        phase_deg=field.phase_deg,
                        normalization=normalization,
                        shape=list(parsed.values.shape),
                        point_count=len(parsed.coordinates_m),
                    )
                )
        return files, fields
