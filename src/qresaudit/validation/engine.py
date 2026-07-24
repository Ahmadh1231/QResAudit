import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from qresaudit.hashing import read_checksums, sha256_file
from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.csv import read_eigenmodes, read_s_parameters
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.io.touchstone import load_network
from qresaudit.models.common import (
    Diagnostic,
    ExportStatus,
    NormalizationKind,
    Severity,
    error,
    info,
    warning,
)
from qresaudit.models.manifest import HFSSRunManifest
from qresaudit.units import RECOGNIZED_COORDINATE_UNITS, RECOGNIZED_FIELD_UNITS


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    diagnostics: tuple[Diagnostic, ...]

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == Severity.ERROR)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == Severity.WARNING)


def _files(bundle: Path, manifest: HFSSRunManifest) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    seen: set[str] = set()
    for record in manifest.files:
        if record.path in seen:
            diagnostics.append(
                error("VALIDATION_DUPLICATE_PATH", "Duplicate manifest path", record.path)
            )
            continue
        seen.add(record.path)
        try:
            path = safe_bundle_path(bundle, record.path)
        except ValueError as exc:
            diagnostics.append(error("VALIDATION_PATH_TRAVERSAL", str(exc), record.path))
            continue
        if not path.is_file():
            severity = Severity.ERROR if record.required else Severity.WARNING
            diagnostics.append(
                Diagnostic(
                    code="VALIDATION_REQUIRED_FILE_MISSING"
                    if record.required
                    else "VALIDATION_OPTIONAL_FILE_MISSING",
                    severity=severity,
                    message="Manifest file does not exist",
                    path=record.path,
                )
            )
            continue
        if path.stat().st_size != record.size_bytes:
            diagnostics.append(
                error("VALIDATION_SIZE_MISMATCH", "File size differs from manifest", record.path)
            )
        if sha256_file(path) != record.sha256:
            diagnostics.append(
                error(
                    "VALIDATION_CHECKSUM_MISMATCH", "File hash differs from manifest", record.path
                )
            )
    checksum_path = bundle / "checksums.sha256"
    if not checksum_path.is_file():
        diagnostics.append(
            error(
                "VALIDATION_REQUIRED_FILE_MISSING",
                "checksums.sha256 is missing",
                "checksums.sha256",
            )
        )
    else:
        try:
            checksums = read_checksums(checksum_path)
            for relative, digest in checksums.items():
                path = safe_bundle_path(bundle, relative)
                if not path.is_file() or sha256_file(path) != digest:
                    diagnostics.append(
                        error("VALIDATION_CHECKSUM_MISMATCH", "Checksum file mismatch", relative)
                    )
        except (OSError, ValueError) as exc:
            diagnostics.append(
                error("VALIDATION_CHECKSUM_FILE_INVALID", str(exc), "checksums.sha256")
            )
    return diagnostics


def _solution_contract(bundle: Path, manifest: HFSSRunManifest, strict: bool) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if manifest.bundle_status not in {ExportStatus.COMPLETE, ExportStatus.COMPLETE_WITH_WARNINGS}:
        diagnostics.append(
            error("VALIDATION_BUNDLE_INCOMPLETE", f"Bundle state is {manifest.bundle_status}")
        )
    required_roles = {"convergence", "mesh_stats"}
    actual_roles = {record.role for record in manifest.files if record.required}
    for role in sorted(required_roles - actual_roles):
        diagnostics.append(
            error("VALIDATION_REQUIRED_FILE_MISSING", f"Required role is absent: {role}")
        )
    if manifest.solution_kind.value.startswith("driven"):
        if manifest.touchstone is None:
            diagnostics.append(
                error("VALIDATION_REQUIRED_FILE_MISSING", "Driven bundle lacks Touchstone metadata")
            )
        if manifest.eigenmode is not None:
            diagnostics.append(
                error(
                    "VALIDATION_SOLUTION_CONTRADICTION", "Driven bundle contains eigenmode metadata"
                )
            )
    else:
        if manifest.eigenmode is None:
            diagnostics.append(
                error("VALIDATION_REQUIRED_FILE_MISSING", "Eigenmode bundle lacks mode metadata")
            )
        if manifest.touchstone is not None:
            diagnostics.append(
                error(
                    "VALIDATION_SOLUTION_CONTRADICTION",
                    "Eigenmode bundle contains Touchstone metadata",
                )
            )
        selected_modes = {field.mode for field in manifest.fields}
        for mode in sorted(mode for mode in selected_modes if mode is not None):
            quantities = {field.quantity for field in manifest.fields if field.mode == mode}
            if not {"E", "H"}.issubset(quantities):
                diagnostics.append(
                    error(
                        "VALIDATION_EIGENMODE_FIELDS_MISSING", f"Mode {mode} lacks E and H fields"
                    )
                )
    if not manifest.fields:
        diagnostics.append(error("VALIDATION_REQUIRED_FILE_MISSING", "Bundle has no field records"))
    if strict:
        for record in manifest.files:
            if record.role == "convergence" and record.path.endswith(".csv"):
                try:
                    rows = __import__("pandas").read_csv(bundle / record.path)
                    if "converged" in rows and len(rows) and not bool(rows.iloc[-1]["converged"]):
                        diagnostics.append(
                            error(
                                "VALIDATION_UNCONVERGED",
                                "Final adaptive pass is unconverged",
                                record.path,
                            )
                        )
                except Exception:
                    pass
    return diagnostics


def _touchstone(bundle: Path, manifest: HFSSRunManifest) -> list[Diagnostic]:
    record = manifest.touchstone
    if record is None:
        return []
    diagnostics: list[Diagnostic] = []
    try:
        network = load_network(safe_bundle_path(bundle, record.path))
    except Exception as exc:
        return [error("TOUCHSTONE_PARSE_FAILED", str(exc), record.path)]
    extension = Path(record.path).suffix.lower()
    if extension.startswith(".s") and extension.endswith("p"):
        try:
            filename_ports = int(extension[2:-1])
            if filename_ports != network.nports:
                diagnostics.append(
                    error(
                        "VALIDATION_TOUCHSTONE_PORT_MISMATCH",
                        "Filename and data port counts differ",
                        record.path,
                    )
                )
        except ValueError:
            pass
    if record.number_of_ports != network.nports or len(manifest.ports) != network.nports:
        diagnostics.append(
            error(
                "VALIDATION_TOUCHSTONE_PORT_MISMATCH",
                "Manifest and Touchstone port counts differ",
                record.path,
            )
        )
    csv_path = bundle / "reports" / "s_parameters.csv"
    if csv_path.is_file():
        try:
            data = read_s_parameters(csv_path)
            if not np.allclose(data["frequency_hz"], network.f, rtol=0, atol=1e-6):
                diagnostics.append(
                    error(
                        "VALIDATION_TOUCHSTONE_CSV_MISMATCH",
                        "Frequency axes differ",
                        csv_path.relative_to(bundle).as_posix(),
                    )
                )
            for destination in range(network.nports):
                for source in range(network.nports):
                    label = f"S{destination + 1}_{source + 1}"
                    csv_values = (
                        data[f"re_{label}"].to_numpy() + 1j * data[f"im_{label}"].to_numpy()
                    )
                    if not np.allclose(
                        csv_values, network.s[:, destination, source], rtol=1e-9, atol=1e-12
                    ):
                        diagnostics.append(
                            error(
                                "VALIDATION_TOUCHSTONE_CSV_MISMATCH",
                                f"{label} differs",
                                csv_path.relative_to(bundle).as_posix(),
                            )
                        )
        except Exception as exc:
            diagnostics.append(
                error("VALIDATION_S_PARAMETER_CSV_INVALID", str(exc), "reports/s_parameters.csv")
            )
    reciprocity = np.max(np.abs(network.s - np.swapaxes(network.s, 1, 2)))
    diagnostics.append(
        info("NETWORK_RECIPROCITY", "Maximum reciprocity residual", residual=float(reciprocity))
    )
    singular = np.linalg.svd(network.s, compute_uv=False)
    if float(np.max(singular)) > 1.0 + 1e-6:
        diagnostics.append(
            warning(
                "NETWORK_PASSIVITY",
                "Network has singular values above one",
                maximum=float(np.max(singular)),
            )
        )
    return diagnostics


def _fields(bundle: Path, manifest: HFSSRunManifest) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for field in manifest.fields:
        if field.normalization == NormalizationKind.UNKNOWN:
            diagnostics.append(
                error(
                    "VALIDATION_FIELD_NORMALIZATION_MISSING",
                    "Field normalization is unknown",
                    field.path,
                )
            )
        if (
            field.units not in RECOGNIZED_FIELD_UNITS
            or field.coordinate_units not in RECOGNIZED_COORDINATE_UNITS
        ):
            diagnostics.append(
                error("VALIDATION_UNKNOWN_UNIT", "Field has an unknown unit", field.path)
            )
        try:
            coordinates, values, magnitude, metadata = read_field_hdf5(
                safe_bundle_path(bundle, field.path)
            )
            if (
                coordinates.ndim != 2
                or coordinates.shape[1] != 3
                or not np.all(np.isfinite(coordinates))
            ):
                raise ValueError("coordinates must be finite with shape (N, 3)")
            if values.shape[0] != coordinates.shape[0]:
                raise ValueError("coordinate and value counts differ")
            if field.vector and (values.ndim != 2 or values.shape[1] != 3):
                raise ValueError("vector field must have shape (N, 3)")
            expected = np.linalg.norm(values, axis=-1) if field.vector else np.abs(values)
            if not np.all(np.isfinite(values)) or not np.allclose(
                magnitude, expected, rtol=1e-12, atol=1e-15
            ):
                raise ValueError("field values or magnitude are invalid")
            if field.point_count != coordinates.shape[0]:
                raise ValueError("manifest point count differs")
            if str(metadata.get("normalization", "")) != field.normalization.value:
                raise ValueError("normalization metadata differs from manifest")
            raw_path = safe_bundle_path(bundle, field.raw_path)
            if str(metadata.get("source_raw_sha256", "")) != sha256_file(raw_path):
                raise ValueError("source raw checksum differs")
        except Exception as exc:
            diagnostics.append(error("VALIDATION_FIELD_SHAPE_MISMATCH", str(exc), field.path))
    return diagnostics


def _modes(bundle: Path, manifest: HFSSRunManifest) -> list[Diagnostic]:
    if manifest.eigenmode is None:
        return []
    try:
        modes = read_eigenmodes(safe_bundle_path(bundle, manifest.eigenmode.path))
        available = {int(mode) for mode in modes["mode"]}
        selected = {field.mode for field in manifest.fields if field.mode is not None}
        if not selected.issubset(available):
            return [
                error(
                    "VALIDATION_MODE_MISSING", "Selected field mode is absent from eigenmode table"
                )
            ]
        if len(modes) != manifest.eigenmode.mode_count:
            return [
                error("VALIDATION_MODE_COUNT_MISMATCH", "Manifest mode count differs from table")
            ]
        return []
    except Exception as exc:
        return [error("VALIDATION_EIGENMODE_TABLE_INVALID", str(exc), manifest.eigenmode.path)]


def validate_bundle(path: Path, strict: bool = True) -> ValidationResult:
    diagnostics: list[Diagnostic] = []
    if not path.is_dir():
        return ValidationResult(
            False,
            (error("VALIDATION_BUNDLE_NOT_FOUND", "Bundle directory does not exist", str(path)),),
        )
    try:
        manifest = load_manifest(path / "manifest.json")
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        return ValidationResult(
            False, (error("VALIDATION_MANIFEST_INVALID", str(exc), "manifest.json"),)
        )
    diagnostics.extend(_files(path, manifest))
    diagnostics.extend(_solution_contract(path, manifest, strict))
    diagnostics.extend(_touchstone(path, manifest))
    diagnostics.extend(_fields(path, manifest))
    diagnostics.extend(_modes(path, manifest))
    return ValidationResult(
        valid=not any(item.severity == Severity.ERROR for item in diagnostics),
        diagnostics=tuple(diagnostics),
    )
