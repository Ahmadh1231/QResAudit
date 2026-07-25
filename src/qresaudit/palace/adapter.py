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
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qresaudit import __version__
from qresaudit.hashing import run_id_for, sha256_file, write_checksums
from qresaudit.io.bundle import prepare_bundle_directories, write_manifest
from qresaudit.models.common import (
    EvidenceProfile,
    ExportStatus,
    SolutionKind,
    warning,
)
from qresaudit.models.manifest import (
    EigenmodeRecord,
    FileRecord,
    HFSSRunManifest,
    TouchstoneRecord,
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


def _file_record(
    path: Path, root: Path, role: str, required: bool, source_path: str | None = None
) -> FileRecord:
    return FileRecord(
        path=path.relative_to(root).as_posix(),
        role=role,
        media_type=_guess_media_type(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        required=required,
        source_path=source_path,
        generated_by=f"qresaudit-palace {__version__}",
    )


def read_palace_eigenmodes(csv_path: Path) -> list[dict[str, Any]]:
    """Read Palace eigenmode CSV output."""
    modes: list[dict[str, Any]] = []
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            modes.append(
                {
                    "mode": int(row.get("m", row.get("mode", 0))),
                    "frequency_real_hz": float(row.get("Freq. (Hz)", row.get("frequency_real", 0))),
                    "frequency_imag_hz": float(row.get("Loss (Hz)", row.get("frequency_imag", 0))),
                    "q_hfss_unloaded": float(row.get("Q", row.get("q", 0))),
                }
            )
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


def convert_palace_run(
    palace_output_dir: Path,
    output_bundle: Path,
    project_name: str = "palace_run",
    design_name: str = "default",
) -> Path:
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
    if not palace_output_dir.is_dir():
        raise FileNotFoundError(f"Palace output directory not found: {palace_output_dir}")
    if output_bundle.exists():
        raise FileExistsError(f"destination already exists: {output_bundle}")
    prepare_bundle_directories(output_bundle)
    files: list[FileRecord] = []
    timestamp = datetime.now(UTC)
    solver_config = palace_output_dir / "config.json"
    if not solver_config.is_file():
        raise ValueError("Palace output must include config.json for solver provenance")
    provenance_target = output_bundle / "provenance" / "palace_config.json"
    provenance_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(solver_config, provenance_target)
    files.append(_file_record(provenance_target, output_bundle, "solver_config", True))

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

    run_id = run_id_for(
        {
            "project": project_name,
            "palace_output": str(palace_output_dir.resolve()),
        }
    )

    # Eigenmode data
    eigenmode_record = None
    if is_eigen:
        modes_data = read_palace_eigenmodes(eigenmode_csv)
        for mode in modes_data:
            mode["source_solution"] = "palace : LastAdaptive"
            mode["variation_id"] = run_id
        mode_count = len(modes_data)

        # Write canonical modes CSV
        import pandas as pd

        modes_df = pd.DataFrame(modes_data)
        target = output_bundle / "modes" / "eigenmodes.csv"
        modes_df.to_csv(target, index=False)
        files.append(_file_record(target, output_bundle, "eigenmodes", True))
        raw_target = output_bundle / "modes" / "raw_eigenmode.csv"
        shutil.copy2(eigenmode_csv, raw_target)
        files.append(_file_record(raw_target, output_bundle, "eigenmodes_raw", False))

        eigenmode_record = EigenmodeRecord(
            path="modes/eigenmodes.csv",
            mode_count=mode_count,
        )

    # Touchstone data
    touchstone_record = None
    if is_driven:
        for snp in sorted(palace_output_dir.glob("*.s*p")):
            target = output_bundle / "network" / snp.name
            shutil.copy2(snp, target)
            files.append(_file_record(target, output_bundle, "touchstone", True))
            from qresaudit.io.touchstone import load_network, network_metadata

            network = load_network(target)
            metadata = network_metadata(
                network,
                target.relative_to(output_bundle).as_posix(),
                [f"port_{i + 1}" for i in range(network.nports)],
                source_file=target,
            )
            touchstone_record = TouchstoneRecord.model_validate(metadata)
            break
        if touchstone_record is None:
            raise ValueError("driven Palace output lacks a Touchstone .sNp file")

    # Preserve native field files without creating misleading canonical records.
    raw_fields_present = False
    postpro_dir = palace_output_dir / "postpro"
    if postpro_dir.is_dir():
        for vtu_file in sorted(postpro_dir.glob("*.vtu")):
            raw_fields_present = True
            raw_target = output_bundle / "fields" / "raw" / vtu_file.name
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(vtu_file, raw_target)
            files.append(_file_record(raw_target, output_bundle, "field_raw", False))

    # Manifest
    manifest = HFSSRunManifest(
        exporter_version=__version__,
        bundle_status=(
            ExportStatus.COMPLETE_WITH_WARNINGS if raw_fields_present else ExportStatus.COMPLETE
        ),
        run_id=run_id,
        export_timestamp_utc=timestamp,
        project_name=project_name,
        project_file_name=provenance_target.name,
        project_file_sha256=sha256_file(provenance_target),
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
        evidence_profile=EvidenceProfile.MINIMAL,
        aedt_version="N/A (Palace)",
        pyaedt_version="N/A (Palace)",
        python_version=platform.python_version(),
        operating_system=f"{platform.system()} {platform.release()}",
        model_units="m",
        reference_coordinate_system="Global",
        ports=touchstone_record.port_names if touchstone_record is not None else [],
        touchstone=touchstone_record,
        eigenmode=eigenmode_record,
        fields=[],
        files=files,
        diagnostics=(
            [
                warning(
                    "PALACE_FIELDS_RAW_ONLY",
                    "Native VTU fields were preserved but are not canonical analysis inputs",
                )
            ]
            if raw_fields_present
            else []
        ),
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
