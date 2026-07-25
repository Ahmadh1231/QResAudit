"""Palace adapter — converts Palace simulation outputs into QResAudit bundles.

Palace output files:
  - postpro/    : Paraview-compatible field exports (.vtu, .pvtu)
  - eigenmode.csv : Eigenmode frequencies and Q factors
  - ports.csv   : S-parameter touchstone data
  - mesh/       : Mesh statistics
  - config.json : Simulation configuration

This adapter reads these outputs and produces a canonical QResAudit bundle.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from qresaudit.hashing import run_id_for, sha256_file, write_checksums
from qresaudit.io.bundle import prepare_bundle_directories, write_manifest
from qresaudit.models.common import (
    EvidenceProfile,
    ExportStatus,
    FieldRepresentation,
    NormalizationKind,
    PhasorConvention,
    SolutionKind,
)
from qresaudit.models.manifest import (
    EigenmodeRecord,
    FieldRecord,
    FileRecord,
    HFSSRunManifest,
    TouchstoneRecord,
    VariationValue,
)


def _guess_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".csv": "text/csv",
        ".json": "application/json",
        ".h5": "application/x-hdf5",
        ".hdf5": "application/x-hdf5",
        ".vtu": "application/xml",
        ".pvtu": "application/xml",
        ".s2p": "text/touchstone",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")


def _file_record(path: Path, root: Path, role: str, required: bool,
                 source_path: str | None = None) -> FileRecord:
    return FileRecord(
        path=path.relative_to(root).as_posix(),
        role=role,
        media_type=_guess_media_type(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        required=required,
        source_path=source_path,
        generated_by="qresaudit-palace 0.4.0",
    )


def read_palace_eigenmodes(csv_path: Path) -> list[dict[str, Any]]:
    """Read Palace eigenmode CSV output."""
    modes: list[dict[str, Any]] = []
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            modes.append({
                "mode": int(row.get("m", row.get("mode", 0))),
                "frequency_real_hz": float(row.get("Freq. (Hz)", row.get("frequency_real", 0))),
                "frequency_imag_hz": float(row.get("Loss (Hz)", row.get("frequency_imag", 0))),
                "q_hfss_unloaded": float(row.get("Q", row.get("q", 0))),
            })
    return modes


def read_palace_mesh_stats(mesh_dir: Path) -> dict[str, Any]:
    """Read Palace mesh statistics."""
    stats_file = mesh_dir / "mesh_stats.csv"
    if not stats_file.is_file():
        return {"tetrahedra": 0, "triangles": 0, "vertices": 0}
    with stats_file.open() as f:
        reader = csv.DictReader(f)
        row = next(reader)
        return {
            "tetrahedra": int(float(row.get("elements", row.get("tetrahedra", 0)))),
            "triangles": int(float(row.get("faces", row.get("triangles", 0)))),
            "vertices": int(float(row.get("vertices", 0))),
        }


def convert_palace_run(palace_output_dir: Path,
                       output_bundle: Path,
                       project_name: str = "palace_run",
                       design_name: str = "default") -> Path:
    """Convert a Palace simulation output directory into a QResAudit bundle.

    Parameters
    ----------
    palace_output_dir : Path
        Directory containing Palace output files (postpro/, eigenmode.csv, etc.)
    output_bundle : Path
        Destination directory for the QResAudit bundle.
    project_name : str
        Project name for the manifest.
    design_name : str
        Design name for the manifest.

    Returns
    -------
    Path to the created bundle.
    """
    prepare_bundle_directories(output_bundle)
    files: list[FileRecord] = []
    timestamp = datetime.now(timezone.utc)

    # Detect solution type
    eigenmode_csv = palace_output_dir / "eigenmode.csv"
    ports_csv = palace_output_dir / "ports.csv"
    is_driven = ports_csv.is_file()
    is_eigen = eigenmode_csv.is_file()

    if is_driven:
        solution_kind = SolutionKind.DRIVEN_MODAL
    elif is_eigen:
        solution_kind = SolutionKind.EIGENMODE
    else:
        raise ValueError("no eigenmode.csv or ports.csv found in Palace output")

    run_id = run_id_for({
        "project": project_name,
        "palace_output": str(palace_output_dir.resolve()),
    })

    # Eigenmode data
    eigenmode_record = None
    if is_eigen:
        modes_data = read_palace_eigenmodes(eigenmode_csv)
        mode_count = len(modes_data)

        # Write canonical modes CSV
        import pandas as pd
        modes_df = pd.DataFrame(modes_data)
        target = output_bundle / "modes" / "eigenmodes.csv"
        modes_df.to_csv(target, index=False)
        files.append(_file_record(target, output_bundle, "eigenmodes", True))
        files.append(_file_record(eigenmode_csv, output_bundle, "eigenmodes_raw", False))

        eigenmode_record = EigenmodeRecord(
            path="modes/eigenmodes.csv",
            mode_count=mode_count,
        )

    # Touchstone data
    touchstone_record = None
    if is_driven:
        for snp in sorted(palace_output_dir.glob("*.s*p")):
            target = output_bundle / "network" / snp.name
            target.write_bytes(snp.read_bytes())
            files.append(_file_record(target, output_bundle, "touchstone", True))
            from qresaudit.io.touchstone import load_network, network_metadata
            network = load_network(target)
            metadata = network_metadata(
                network,
                target.relative_to(output_bundle).as_posix(),
                [f"port_{i+1}" for i in range(network.nports)],
                source_file=target,
            )
            touchstone_record = TouchstoneRecord.model_validate(metadata)
            break

    # Field data
    field_records: list[FieldRecord] = []
    postpro_dir = palace_output_dir / "postpro"
    if postpro_dir.is_dir():
        for vtu_file in sorted(postpro_dir.glob("*.vtu")):
            # Copy raw VTU
            raw_target = output_bundle / "fields" / "raw" / vtu_file.name
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            raw_target.write_bytes(vtu_file.read_bytes())
            files.append(_file_record(raw_target, output_bundle, "field_raw", True))

            # For now, produce a placeholder HDF5 — full VTU→HDF5 conversion
            # would use vtk/pyvista to extract structured grid data
            field_records.append(FieldRecord(
                path=f"fields/raw/{vtu_file.name}",
                raw_path=f"fields/raw/{vtu_file.name}",
                quantity="E" if "e_field" in vtu_file.name.lower() else "H",
                complex_data=False,
                vector=True,
                units="V/m",
                coordinate_units="m",
                coordinate_system="Global",
                grid_type="Cartesian",
                region_name="default",
                assignment=["AllObjects"],
                object_type="Vol",
                solution="palace_solution",
                normalization=NormalizationKind.USER_SCALED,
                shape=[0],
                point_count=0,
                representation=FieldRepresentation.REAL_GAUGE,
            ))

    # Manifest
    manifest = HFSSRunManifest(
        exporter_version="0.4.0",  # palace adapter version
        bundle_status=ExportStatus.COMPLETE,
        run_id=run_id,
        export_timestamp_utc=timestamp,
        project_name=project_name,
        project_file_name=f"{project_name}.json",
        project_file_sha256=None,
        design_name=design_name,
        design_type="Palace",
        solution_kind=solution_kind,
        setup_name="palace",
        sweep_name=None,
        solution_reference="palace : LastAdaptive",
        variation_id=run_id,
        variation={},
        project_variables={},
        design_variables={},
        solved_variation={},
        evidence_profile=EvidenceProfile.STANDARD,
        aedt_version="N/A (Palace)",
        pyaedt_version="N/A (Palace)",
        python_version="3.x",
        operating_system="platform",
        model_units="m",
        reference_coordinate_system="Global",
        ports=[],
        touchstone=touchstone_record,
        eigenmode=eigenmode_record,
        fields=field_records,
        files=files,
        diagnostics=[],
    )

    write_manifest(output_bundle / "manifest.json", manifest)
    write_checksums(output_bundle)
    return output_bundle


class PalaceAdapter:
    """Adapter for Palace simulation outputs to QResAudit bundles."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        if not self.output_dir.is_dir():
            raise FileNotFoundError(f"Palace output directory not found: {output_dir}")

    def to_bundle(self, output: Path, **kwargs: Any) -> Path:
        return convert_palace_run(self.output_dir, output, **kwargs)

    def detect_solution_type(self) -> SolutionKind | None:
        if (self.output_dir / "ports.csv").is_file():
            return SolutionKind.DRIVEN_MODAL
        if (self.output_dir / "eigenmode.csv").is_file():
            return SolutionKind.EIGENMODE
        return None
