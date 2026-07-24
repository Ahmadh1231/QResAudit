import mimetypes
from pathlib import Path
from typing import Any

from qresaudit.hashing import sha256_file
from qresaudit.io.hfss_convergence import parse_convergence
from qresaudit.io.hfss_mesh import parse_mesh
from qresaudit.models.manifest import FileRecord
from qresaudit_hfss.exports.evidence import export_evidence


def file_record(
    path: Path,
    staging: Path,
    role: str,
    required: bool,
    *,
    source_path: str | None = None,
    generated_by: str = "qresaudit-hfss 0.1.1",
) -> FileRecord:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileRecord(
        path=path.relative_to(staging).as_posix(),
        role=role,
        media_type=media_type,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        required=required,
        source_path=source_path,
        generated_by=generated_by,
    )


def evidence_records(app: Any, config: Any, staging: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path, role, required in export_evidence(app, config, staging):
        records.append(file_record(path, staging, role, required))
        if role == "convergence_raw":
            canonical = staging / "convergence" / "adaptive_passes.csv"
            parse_convergence(path).to_csv(canonical, index=False)
            records.append(
                file_record(
                    canonical,
                    staging,
                    "convergence",
                    required,
                    source_path=path.relative_to(staging).as_posix(),
                )
            )
        elif role == "mesh_stats_raw":
            canonical = staging / "mesh" / "mesh_stats.csv"
            parse_mesh(path).to_csv(canonical, index=False)
            records.append(
                file_record(
                    canonical,
                    staging,
                    "mesh_stats",
                    required,
                    source_path=path.relative_to(staging).as_posix(),
                )
            )
    return records
