import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from qresaudit import __version__
from qresaudit.exceptions import BundleValidationError, PreflightError
from qresaudit.hashing import run_id_for, sha256_file, write_checksums
from qresaudit.io.bundle import atomic_staging, write_manifest
from qresaudit.models.common import ExportStatus, Severity
from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import FileRecord, HFSSRunManifest
from qresaudit.validation.engine import validate_bundle
from qresaudit_hfss.adapters.base import adapter_for
from qresaudit_hfss.adapters.common import file_record
from qresaudit_hfss.capabilities import detect_capabilities
from qresaudit_hfss.exports.reports import export_existing_reports
from qresaudit_hfss.inspect import inspect_design, run_preflight
from qresaudit_hfss.provenance import evaluated_variables, project_hash
from qresaudit_hfss.session import open_hfss_session


def load_config(path: Path, project_override: Path | None = None) -> ExportConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    if project_override is not None:
        raw.setdefault("project", {})["path"] = str(project_override)
    config = ExportConfig.model_validate(raw)
    if not config.project.path.is_absolute():
        config.project.path = (path.parent / config.project.path).resolve()
    for field in config.fields:
        sample = field.grid.sample_points_file
        if sample is not None and not sample.is_absolute():
            field.grid.sample_points_file = (path.parent / sample).resolve()
    return config


def _json_file(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return path


def _write_log(staging: Path, event: str, **data: Any) -> None:
    record = {"time": datetime.now(UTC).isoformat(), "level": "INFO", "event": event, **data}
    with (staging / "logs" / "export.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, default=str) + "\n")


def _static_records(staging: Path) -> list[FileRecord]:
    roles = {
        "export_config.resolved.yaml": ("configuration", True),
        "design_variables.json": ("design_variables", True),
        "project_variables.json": ("project_variables", True),
        "solved_variation.json": ("solved_variation", True),
        "reports/report_index.json": ("report_index", False),
        "fields/field_index.json": ("field_index", True),
        "logs/export.jsonl": ("structured_log", False),
    }
    return [
        file_record(staging / relative, staging, role, required)
        for relative, (role, required) in roles.items()
        if (staging / relative).is_file()
    ]


def export_bundle(config: ExportConfig, output: Path, *, force: bool = False) -> Path:
    if ".aedtresults" in {part.lower() for part in output.parts}:
        raise PreflightError("output may not be inside an .aedtresults directory")
    source_project_hash = project_hash(config.project.path)
    stable_identity = {
        "project_sha256": source_project_hash,
        "design": config.project.design,
        "setup": config.solution.setup,
        "sweep": config.solution.sweep,
        "variation": config.solution.variation,
        "exporter_version": __version__,
        "config": config.model_dump(mode="json", exclude={"keep_failed"}),
    }
    run_id = run_id_for(stable_identity)

    def validate_published(path: Path) -> None:
        published = validate_bundle(path, strict=config.strict)
        if not published.valid:
            raise BundleValidationError("published bundle failed final validation")

    with atomic_staging(
        output,
        force=force,
        keep_failed=config.keep_failed,
        validate_final=validate_published,
    ) as staging:
        _write_log(staging, "export.started", project=config.project.path.name)
        with open_hfss_session(config.project) as app:
            inspection = inspect_design(app)
            diagnostics = run_preflight(inspection, config)
            if any(item.severity == Severity.ERROR for item in diagnostics):
                raise PreflightError(
                    "; ".join(f"{item.code}: {item.message}" for item in diagnostics)
                )
            if inspection.solution_kind is None:
                raise PreflightError("HFSS_UNSUPPORTED_SOLUTION_TYPE")
            capabilities = detect_capabilities(app)
            adapter = adapter_for(app, config, capabilities)
            diagnostics.extend(adapter.preflight())
            if any(item.severity == Severity.ERROR for item in diagnostics):
                raise PreflightError(
                    "; ".join(f"{item.code}: {item.message}" for item in diagnostics)
                )
            resolved_path = staging / "export_config.resolved.yaml"
            resolved_path.write_text(
                yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
                encoding="utf-8",
            )
            _json_file(staging / "design_variables.json", inspection.design_variables)
            _json_file(staging / "project_variables.json", inspection.project_variables)
            _json_file(staging / "solved_variation.json", config.solution.variation)
            primary_files, touchstone, eigenmode = adapter.export_primary_results(staging)
            evidence_files = adapter.export_evidence(staging)
            field_files, fields = adapter.export_fields(staging)
            report_files, report_index, report_diagnostics = export_existing_reports(
                app,
                config,
                inspection.reports,
                staging,
            )
            diagnostics.extend(report_diagnostics)
            _json_file(
                staging / "fields" / "field_index.json",
                [field.model_dump(mode="json") for field in fields],
            )
            _json_file(
                staging / "reports" / "report_index.json",
                {
                    "available_reports": inspection.reports,
                    "exported_reports": report_index,
                },
            )
            _write_log(
                staging,
                "export.data_complete",
                file_count=len(primary_files + evidence_files + field_files + report_files),
            )
            files = (
                primary_files
                + evidence_files
                + field_files
                + report_files
                + _static_records(staging)
            )
            project_variables = evaluated_variables(inspection.project_variables)
            design_variables = evaluated_variables(inspection.design_variables)
            solved_variation = evaluated_variables(config.solution.variation)
            manifest = HFSSRunManifest(
                exporter_version=__version__,
                bundle_status=ExportStatus.COMPLETE,
                run_id=run_id,
                export_timestamp_utc=datetime.now(UTC),
                project_name=inspection.project_name,
                project_file_name=config.project.path.name,
                project_file_sha256=source_project_hash,
                design_name=inspection.design_name,
                design_type=inspection.design_type,
                solution_kind=inspection.solution_kind,
                setup_name=config.solution.setup,
                sweep_name=config.solution.sweep,
                solution_reference=(
                    f"{config.solution.setup} : {config.solution.sweep}"
                    if config.solution.sweep
                    else f"{config.solution.setup} : LastAdaptive"
                ),
                variation_id=run_id,
                variation=solved_variation,
                project_variables=project_variables,
                design_variables=design_variables,
                solved_variation=solved_variation,
                evidence_profile=config.evidence_profile,
                aedt_version=str(
                    getattr(app, "aedt_version_id", config.project.aedt_version or "unknown")
                ),
                pyaedt_version=capabilities.version,
                python_version=platform.python_version(),
                operating_system=platform.platform(),
                model_units=inspection.model_units,
                reference_coordinate_system="Global",
                ports=touchstone.port_names if touchstone is not None else inspection.ports,
                touchstone=touchstone,
                eigenmode=eigenmode,
                fields=fields,
                files=files,
                diagnostics=diagnostics,
            )
            write_manifest(staging / "manifest.json", manifest)
        write_checksums(staging)
        result = validate_bundle(staging, strict=config.strict)
        if not result.valid:
            raise BundleValidationError(
                "; ".join(f"{item.code}: {item.message}" for item in result.errors)
            )
        if result.warnings:
            manifest.bundle_status = ExportStatus.COMPLETE_WITH_WARNINGS
            manifest.diagnostics.extend(result.warnings)
            write_manifest(staging / "manifest.json", manifest)
            write_checksums(staging)
            final_result = validate_bundle(staging, strict=config.strict)
            if not final_result.valid:
                raise BundleValidationError("finalized bundle failed revalidation")
        _write_log(staging, "export.completed", bundle_status=manifest.bundle_status.value)
        # The log changed after checksum generation.
        log_record = next(
            (item for item in manifest.files if item.path == "logs/export.jsonl"), None
        )
        if log_record is not None:
            log_path = staging / log_record.path
            log_record.sha256 = sha256_file(log_path)
            log_record.size_bytes = log_path.stat().st_size
            write_manifest(staging / "manifest.json", manifest)
        write_checksums(staging)
        if not validate_bundle(staging, strict=config.strict).valid:
            raise BundleValidationError("published-state validation failed")
    return output
