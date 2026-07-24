from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qresaudit.hashing import sha256_file, write_checksums  # noqa: E402
from qresaudit.io.field_tab import ParsedField  # noqa: E402
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5  # noqa: E402
from qresaudit.models.common import ExportStatus, NormalizationKind, SolutionKind  # noqa: E402
from qresaudit.models.manifest import (  # noqa: E402
    EigenmodeRecord,
    FieldRecord,
    FileRecord,
    HFSSRunManifest,
    TouchstoneRecord,
)


def file_record(root: Path, relative: str, role: str, required: bool = True) -> FileRecord:
    path = root / relative
    return FileRecord(
        path=relative,
        role=role,
        media_type="application/octet-stream",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        required=required,
        generated_by="qresaudit-testdata 0.1.0",
    )


def write_field(
    root: Path,
    name: str,
    quantity: str,
    normalization: NormalizationKind,
    mode: int | None,
) -> tuple[FieldRecord, list[FileRecord]]:
    raw_relative = f"fields/raw/{name}.fld"
    h5_relative = f"fields/hdf5/{name}.h5"
    raw = root / raw_relative
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        f"# quantity: {quantity}\n# units: {'A/m' if quantity == 'H' else 'V/m'}\n"
        "0 0 0 1 0 0 1 0 0\n"
        "0.001 0 0 0.5 0.1 0.2 0.0 0.1 -0.1\n",
        encoding="utf-8",
    )
    coordinates = np.array([[0, 0, 0], [0.001, 0, 0]], dtype=np.float64)
    values = np.array([[1 + 0j, 0 + 1j, 0], [0.5 + 0.1j, 0.2 + 0j, 0.1 - 0.1j]])
    parsed = ParsedField(
        coordinates_m=coordinates,
        values=values,
        is_complex=True,
        is_vector=True,
        quantity=quantity,
        value_units="A/m" if quantity == "H" else "V/m",
        coordinate_units="m",
        source_header=(),
    )
    metadata = {
        "grid_type": "Cartesian",
        "grid_shape": [2],
        "coordinate_system": "Global",
        "solution_reference": "Setup1 : LastAdaptive" if mode else "Setup1 : Sweep1",
        "setup_name": "Setup1",
        "sweep_name": "" if mode else "Sweep1",
        "mode": mode,
        "frequency_hz": 6e9,
        "phase_deg": 0.0,
        "normalization": normalization.value,
        "region_name": name,
        "assignments_json": ["AllObjects"],
        **source_metadata(raw),
    }
    write_field_hdf5(root / h5_relative, parsed, metadata)
    field = FieldRecord(
        path=h5_relative,
        raw_path=raw_relative,
        quantity=quantity,
        complex_data=True,
        vector=True,
        units=parsed.value_units,
        coordinate_units="m",
        coordinate_system="Global",
        grid_type="Cartesian",
        region_name=name,
        assignment=["AllObjects"],
        object_type="Vol",
        solution=str(metadata["solution_reference"]),
        mode=mode,
        frequency_hz=6e9,
        phase_deg=0,
        normalization=normalization,
        shape=[2, 3],
        point_count=2,
    )
    return field, [
        file_record(root, raw_relative, "field_raw"),
        file_record(root, h5_relative, "field_hdf5"),
    ]


def common_files(root: Path) -> list[FileRecord]:
    (root / "convergence").mkdir(parents=True, exist_ok=True)
    (root / "convergence/convergence_raw.prof").write_text("Pass 1 Converged\n", encoding="utf-8")
    (root / "convergence/mesh_stats_raw.txt").write_text("Tetrahedra: 1000\n", encoding="utf-8")
    (root / "convergence/adaptive_passes.csv").write_text(
        "pass_index,frequency_hz,delta_frequency_percent,maximum_delta_s,tetrahedra,converged,elapsed_time_s,peak_memory_bytes\n"
        "1,6000000000,0.1,,1000,True,1.0,1024\n",
        encoding="utf-8",
    )
    (root / "export_config.resolved.yaml").write_text(
        yaml.safe_dump({"schema_version": "0.1.0", "strict": True}),
        encoding="utf-8",
    )
    (root / "design_variables.json").write_text("{}\n", encoding="utf-8")
    (root / "project_variables.json").write_text("{}\n", encoding="utf-8")
    return [
        file_record(root, "convergence/convergence_raw.prof", "convergence"),
        file_record(root, "convergence/mesh_stats_raw.txt", "mesh_stats"),
        file_record(root, "convergence/adaptive_passes.csv", "convergence"),
        file_record(root, "export_config.resolved.yaml", "configuration"),
        file_record(root, "design_variables.json", "design_variables"),
        file_record(root, "project_variables.json", "project_variables"),
    ]


def base_manifest(
    kind: SolutionKind, fields: list[FieldRecord], files: list[FileRecord]
) -> dict[str, object]:
    return {
        "exporter_version": "0.1.0",
        "bundle_status": ExportStatus.COMPLETE,
        "run_id": "1234abcd",
        "export_timestamp_utc": datetime(2026, 7, 23, tzinfo=UTC),
        "project_name": "synthetic",
        "project_file_name": "synthetic.aedt",
        "project_file_sha256": None,
        "design_name": "Synthetic",
        "design_type": "HFSS",
        "solution_kind": kind,
        "setup_name": "Setup1",
        "sweep_name": None if kind is SolutionKind.EIGENMODE else "Sweep1",
        "solution_reference": "Setup1 : LastAdaptive"
        if kind is SolutionKind.EIGENMODE
        else "Setup1 : Sweep1",
        "variation_id": "nominal",
        "variation": {},
        "aedt_version": "synthetic",
        "pyaedt_version": "synthetic",
        "python_version": "3.11",
        "operating_system": "synthetic",
        "model_units": "mm",
        "reference_coordinate_system": "Global",
        "fields": fields,
        "files": files,
        "diagnostics": [],
    }


def driven(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "network").mkdir()
    (root / "reports").mkdir()
    touchstone = root / "network/network.s2p"
    touchstone.write_text(
        "! synthetic reciprocal passive two-port\n"
        "# GHZ S RI R 50\n"
        "5.0 0.1 0 0.9 0 0.9 0 0.1 0\n"
        "6.0 0.2 0 0.7 -0.1 0.7 -0.1 0.2 0\n"
        "7.0 0.1 0 0.9 0 0.9 0 0.1 0\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "frequency_hz": [5e9, 6e9, 7e9],
            "re_S1_1": [0.1, 0.2, 0.1],
            "im_S1_1": [0, 0, 0],
            "re_S1_2": [0.9, 0.7, 0.9],
            "im_S1_2": [0, -0.1, 0],
            "re_S2_1": [0.9, 0.7, 0.9],
            "im_S2_1": [0, -0.1, 0],
            "re_S2_2": [0.1, 0.2, 0.1],
            "im_S2_2": [0, 0, 0],
        }
    ).to_csv(root / "reports/s_parameters.csv", index=False)
    field, field_files = write_field(
        root, "device_H", "H", NormalizationKind.DRIVEN_EXCITATION_DEPENDENT, None
    )
    files = (
        common_files(root)
        + field_files
        + [
            file_record(root, "network/network.s2p", "touchstone"),
            file_record(root, "reports/s_parameters.csv", "s_parameters"),
        ]
    )
    values = base_manifest(SolutionKind.DRIVEN_MODAL, [field], files)
    values.update(
        {
            "ports": ["1", "2"],
            "touchstone": TouchstoneRecord(
                path="network/network.s2p",
                number_of_ports=2,
                frequency_unit="Hz",
                data_format="RI",
                renormalized=False,
                reference_impedance_ohm=50,
                port_names=["1", "2"],
                frequency_min_hz=5e9,
                frequency_max_hz=7e9,
                point_count=3,
            ),
            "eigenmode": None,
        }
    )
    manifest = HFSSRunManifest.model_validate(values)
    (root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    write_checksums(root)


def eigenmode(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "modes").mkdir()
    pd.DataFrame(
        {
            "mode": [1, 2],
            "frequency_real_hz": [6e9, 8e9],
            "frequency_imag_hz": [0, 0],
            "q_hfss_unloaded": [0, 0],
            "source_solution": ["Setup1 : LastAdaptive"] * 2,
            "variation_id": ["nominal"] * 2,
        }
    ).to_csv(root / "modes/eigenmodes.csv", index=False)
    fields: list[FieldRecord] = []
    files = common_files(root)
    for quantity in ("E", "H"):
        field, field_files = write_field(
            root,
            f"mode_01_{quantity}",
            quantity,
            NormalizationKind.HFSS_EIGENMODE_PEAK_1,
            1,
        )
        fields.append(field)
        files.extend(field_files)
    files.append(file_record(root, "modes/eigenmodes.csv", "eigenmodes"))
    values = base_manifest(SolutionKind.EIGENMODE, fields, files)
    values.update(
        {
            "ports": [],
            "touchstone": None,
            "eigenmode": EigenmodeRecord(path="modes/eigenmodes.csv", mode_count=2),
        }
    )
    manifest = HFSSRunManifest.model_validate(values)
    (root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    write_checksums(root)


def generate() -> None:
    target = ROOT / "testdata" / "synthetic"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    driven(target / "valid_driven_minimal")
    eigenmode(target / "valid_eigenmode_minimal")
    for name in (
        "corrupt_checksum",
        "missing_normalization",
        "port_mismatch",
        "field_shape_mismatch",
        "unknown_unit",
        "partial_bundle",
    ):
        source = target / (
            "valid_driven_minimal"
            if name in {"corrupt_checksum", "port_mismatch"}
            else "valid_eigenmode_minimal"
        )
        shutil.copytree(source, target / name)
    with (target / "corrupt_checksum" / "design_variables.json").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write("X")
    manifest_path = target / "port_mismatch" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["ports"] = ["1"]
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_checksums(target / "port_mismatch")
    manifest_path = target / "missing_normalization" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["fields"][0]["normalization"] = "unknown"
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_checksums(target / "missing_normalization")
    manifest_path = target / "unknown_unit" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["fields"][0]["units"] = "Am"
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_checksums(target / "unknown_unit")
    manifest_path = target / "field_shape_mismatch" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["fields"][0]["point_count"] = 99
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_checksums(target / "field_shape_mismatch")
    manifest_path = target / "partial_bundle" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["bundle_status"] = "building"
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_checksums(target / "partial_bundle")


if __name__ == "__main__":
    generate()
