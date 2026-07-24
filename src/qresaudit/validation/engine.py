import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from qresaudit.hashing import read_checksums, sha256_file
from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.csv import read_eigenmodes, read_s_parameters
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.io.hfss_convergence import parse_convergence
from qresaudit.io.touchstone import load_network
from qresaudit.models.common import (
    Diagnostic,
    EvidenceProfile,
    ExportStatus,
    FieldRepresentation,
    NormalizationKind,
    PhasorConvention,
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
            checksum_paths = set(checksums)
            missing_checksum_entries = seen - checksum_paths
            for relative in sorted(missing_checksum_entries):
                diagnostics.append(
                    error(
                        "VALIDATION_CHECKSUM_ENTRY_MISSING",
                        "Manifest file is absent from checksum index",
                        relative,
                    )
                )
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
    expected = seen | {"manifest.json", "checksums.sha256"}
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            diagnostics.append(
                error("VALIDATION_SYMLINK_FORBIDDEN", "Symlinks are not allowed", relative)
            )
        elif path.is_file() and relative not in expected:
            diagnostics.append(
                error("VALIDATION_UNEXPECTED_FILE", "File is not listed in manifest", relative)
            )
    return diagnostics


def _solution_contract(bundle: Path, manifest: HFSSRunManifest, strict: bool) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if manifest.schema_version != "0.1.0":
        if manifest.project_file_sha256 is None:
            diagnostics.append(
                error("VALIDATION_PROJECT_HASH_MISSING", "Source project hash is required")
            )
        if len(manifest.run_id) != 32:
            diagnostics.append(error("VALIDATION_RUN_ID_WEAK", "Run ID must contain 128 bits"))
    if manifest.bundle_status not in {ExportStatus.COMPLETE, ExportStatus.COMPLETE_WITH_WARNINGS}:
        diagnostics.append(
            error("VALIDATION_BUNDLE_INCOMPLETE", f"Bundle state is {manifest.bundle_status}")
        )
    required_roles: set[str] = set()
    if manifest.evidence_profile in {EvidenceProfile.STANDARD, EvidenceProfile.STRICT}:
        required_roles.update({"convergence", "mesh_stats"})
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
        if manifest.evidence_profile is EvidenceProfile.STRICT:
            selected_modes = {field.mode for field in manifest.fields}
            for mode in sorted(mode for mode in selected_modes if mode is not None):
                quantities = {field.quantity for field in manifest.fields if field.mode == mode}
                if not {"E", "H"}.issubset(quantities):
                    diagnostics.append(
                        error(
                            "VALIDATION_EIGENMODE_FIELDS_MISSING",
                            f"Mode {mode} lacks E and H fields",
                        )
                    )
    if manifest.evidence_profile is EvidenceProfile.STRICT and not manifest.fields:
        diagnostics.append(error("VALIDATION_REQUIRED_FILE_MISSING", "Bundle has no field records"))
    if strict:
        for record in manifest.files:
            if record.role == "convergence" and record.path.endswith(".csv"):
                try:
                    rows = parse_convergence(bundle / record.path)
                    if "converged" in rows and len(rows) and not bool(rows.iloc[-1]["converged"]):
                        diagnostics.append(
                            error(
                                "VALIDATION_UNCONVERGED",
                                "Final adaptive pass is unconverged",
                                record.path,
                            )
                        )
                except Exception as exc:
                    diagnostics.append(
                        error(
                            "CONVERGENCE_FILE_UNREADABLE",
                            str(exc),
                            record.path,
                        )
                    )
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
    if not record.port_order_verified:
        diagnostic = (
            error(
                "VALIDATION_TOUCHSTONE_PORT_ORDER_UNVERIFIED",
                "Touchstone port order is not independently identified",
                record.path,
            )
            if manifest.evidence_profile is EvidenceProfile.STRICT
            else warning(
                "VALIDATION_TOUCHSTONE_PORT_ORDER_UNVERIFIED",
                "Touchstone port order is not independently identified",
                record.path,
            )
        )
        diagnostics.append(diagnostic)
    actual_z0 = np.asarray(network.z0)
    if record.reference_impedance_real_ohm:
        expected_real = np.asarray(record.reference_impedance_real_ohm)
        expected_imag = np.asarray(record.reference_impedance_imag_ohm)
        if (
            expected_real.shape != actual_z0.shape
            or expected_imag.shape != actual_z0.shape
            or not np.allclose(expected_real + 1j * expected_imag, actual_z0)
        ):
            diagnostics.append(
                error(
                    "VALIDATION_TOUCHSTONE_IMPEDANCE_MISMATCH",
                    "Manifest reference impedances differ from the network",
                    record.path,
                )
            )
    if record.renormalized:
        if (
            not record.source_impedance_preserved
            or not record.source_impedance_path
            or not record.source_reference_impedance_real_ohm
            or not record.source_reference_impedance_imag_ohm
        ):
            diagnostics.append(
                error(
                    "VALIDATION_TOUCHSTONE_SOURCE_IMPEDANCE_MISSING",
                    "Renormalized Touchstone lacks preserved source-normalization evidence",
                    record.path,
                )
            )
        else:
            try:
                source_network = load_network(
                    safe_bundle_path(bundle, record.source_impedance_path)
                )
                source_z0 = np.asarray(source_network.z0)
                source_real = np.asarray(record.source_reference_impedance_real_ohm)
                source_imag = np.asarray(record.source_reference_impedance_imag_ohm)
                if (
                    source_real.shape != source_z0.shape
                    or source_imag.shape != source_z0.shape
                    or not np.allclose(source_real + 1j * source_imag, source_z0)
                ):
                    diagnostics.append(
                        error(
                            "VALIDATION_TOUCHSTONE_SOURCE_IMPEDANCE_MISMATCH",
                            "Preserved source impedances differ from the source network",
                            record.source_impedance_path,
                        )
                    )
            except Exception as exc:
                diagnostics.append(
                    error(
                        "VALIDATION_TOUCHSTONE_SOURCE_IMPEDANCE_UNREADABLE",
                        str(exc),
                        record.source_impedance_path,
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
            expected_shape = (
                [
                    *[int(value) for value in metadata.get("shape", [])],
                    *([3] if field.vector else []),
                ]
                if metadata.get("topology") == "structured"
                else list(values.shape)
            )
            if expected_shape != field.shape:
                raise ValueError("manifest field shape differs")
            if len({tuple(point) for point in coordinates}) != len(coordinates):
                raise ValueError("field coordinates contain duplicate points")
            if str(metadata.get("normalization", "")) != field.normalization.value:
                raise ValueError("normalization metadata differs from manifest")
            if manifest.schema_version != "0.1.0":
                if str(metadata.get("representation", "")) != field.representation.value:
                    raise ValueError("field representation metadata differs from manifest")
                if str(metadata.get("phasor_convention", "")) != field.phasor_convention.value:
                    raise ValueError("phasor convention metadata differs from manifest")
            if (
                manifest.schema_version != "0.1.0"
                and field.representation is FieldRepresentation.MAGNITUDE_ONLY
            ):
                raise ValueError("magnitude-only fields are insufficient for phase-sensitive use")
            if (
                manifest.schema_version != "0.1.0"
                and field.representation
                in {
                    FieldRepresentation.COMPLEX_PHASOR,
                    FieldRepresentation.QUADRATURE_RECONSTRUCTED,
                }
                and field.phasor_convention is PhasorConvention.UNKNOWN
            ):
                raise ValueError("complex field is missing an explicit phasor convention")
            if metadata.get("topology") == "structured":
                shape = [int(value) for value in metadata.get("shape", [])]
                if len(shape) != 3 or int(np.prod(shape)) != field.point_count:
                    raise ValueError("structured grid shape is invalid")
                if metadata.get("axis_order") != field.axis_order:
                    raise ValueError("structured grid axis order differs")
                if metadata.get("flattening_order") != field.flattening_order:
                    raise ValueError("structured grid flattening order differs")
            if (
                manifest.schema_version != "0.1.0"
                and manifest.solution_kind.value.startswith("driven")
                and (field.frequency_hz is None or not field.excitation)
            ):
                raise ValueError("driven field is missing explicit frequency or excitation context")
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
        for column in ("frequency_real_hz", "frequency_imag_hz", "q_hfss_unloaded"):
            if column not in modes:
                continue
            present = modes[column].dropna().to_numpy(dtype=float)
            if not np.all(np.isfinite(present)):
                return [
                    error("VALIDATION_EIGENMODE_NONFINITE", f"{column} contains nonfinite values")
                ]
        if "frequency_real_hz" in modes and np.any(modes["frequency_real_hz"] <= 0):
            return [error("VALIDATION_EIGENFREQUENCY_INVALID", "Eigenfrequencies must be positive")]
        if "q_hfss_unloaded" in modes:
            q_values = modes["q_hfss_unloaded"].dropna().to_numpy(dtype=float)
            if np.any(q_values < 0):
                return [error("VALIDATION_Q_INVALID", "Eigenmode Q values cannot be negative")]
            if np.any(q_values == 0):
                return [
                    warning(
                        "VALIDATION_Q_ZERO",
                        "Zero Q is preserved as a physical value; use null for missing data",
                    )
                ]
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
