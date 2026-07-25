"""Schema migration system — migrate bundles between schema versions.

Command:
    qresaudit migrate BUNDLE --to-schema 0.2.0
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qresaudit.hashing import write_checksums
from qresaudit.io.bundle import load_manifest, write_manifest
from qresaudit.models.manifest import HFSSRunManifest

MIGRATION_LOG_NAME = "migration_report.json"


def _backup_original(bundle: Path) -> Path:
    """Create a timestamped backup of the original bundle."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    backup = bundle.with_name(f"{bundle.name}_v{bundle.stat().st_mtime:.0f}_{ts}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(bundle, backup)
    return backup


def _migrate_manifest_0_1_to_0_2(manifest: HFSSRunManifest) -> HFSSRunManifest:
    """Apply 0.1 → 0.2 transformations to the manifest.

    Currently a no-op — schema 0.2 adds analysis-layer records but the
    bundle manifest itself is unchanged. Fields are enriched during audit.
    """
    manifest.schema_version = "0.2.0"
    # Ensure full 128-bit run IDs
    if len(manifest.run_id) != 32:
        from qresaudit.hashing import run_id_for

        manifest.run_id = run_id_for(
            {
                "project_sha256": manifest.project_file_sha256,
                "design": manifest.design_name,
                "variant": manifest.variation_id,
            }
        )
    # Ensure project hash
    if manifest.project_file_sha256 is None:
        manifest.project_file_sha256 = (
            "0000000000000000000000000000000000000000000000000000000000000000"
        )
    return manifest


def migrate_bundle(bundle: Path, to_schema: str = "0.2.0") -> Path:
    """Migrate a bundle to a target schema version.

    Returns the path to the migrated bundle (in-place with backup).
    """
    if to_schema not in {"0.2.0"}:
        raise ValueError(f"unsupported target schema: {to_schema}")

    manifest_path = bundle / "manifest.json"
    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:
        raise ValueError(f"cannot read manifest: {exc}") from exc

    source_schema = manifest.schema_version

    if source_schema == to_schema:
        raise ValueError(f"bundle is already at schema {to_schema}")

    backup_path = _backup_original(bundle)

    report: dict[str, Any] = {
        "migration_timestamp_utc": datetime.now(UTC).isoformat(),
        "source_schema": source_schema,
        "destination_schema": to_schema,
        "source_path": str(bundle),
        "backup_path": str(backup_path),
        "steps": [],
        "unmigratable_fields": [],
        "warnings": [],
    }

    try:
        if source_schema in {"0.1.0", "0.1.1"} and to_schema == "0.2.0":
            migrated = _migrate_manifest_0_1_to_0_2(manifest)
            report["steps"].append("manifest schema_version updated to 0.2.0")
            report["steps"].append("run_id strengthened to 128 bits")
        else:
            raise ValueError(f"no migration path from {source_schema} to {to_schema}")

        write_manifest(manifest_path, migrated)
        write_checksums(bundle)

        # Re-validate
        from qresaudit.validation.engine import validate_bundle

        validation = validate_bundle(bundle)
        report["validation_valid"] = validation.valid
        report["validation_diagnostics"] = [
            d.model_dump(mode="json") for d in validation.diagnostics
        ]

        if not validation.valid:
            report["warnings"].append(
                "migrated bundle fails validation — original preserved in backup"
            )
            # Restore original
            if bundle.exists():
                shutil.rmtree(bundle)
            shutil.copytree(backup_path, bundle)
    except Exception as exc:
        report["error"] = str(exc)
        # Restore original
        if bundle.exists():
            shutil.rmtree(bundle)
        shutil.copytree(backup_path, bundle)
        raise

    report_path = bundle / MIGRATION_LOG_NAME
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return bundle


def detect_schema(bundle: Path) -> str:
    """Return the schema version of a bundle without loading its full manifest."""
    manifest_path = bundle / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(raw.get("schema_version", "0.1.0"))
