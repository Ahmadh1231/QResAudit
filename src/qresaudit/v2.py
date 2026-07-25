"""Solver-neutral v2 evidence models, adapters, and deterministic diagnosis."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Status(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SolverRecord(StrictModel):
    name: str = Field(min_length=1)
    version: str | None = None
    adapter: str = Field(min_length=1)


class PhysicsRecord(StrictModel):
    domains: set[str] = Field(default_factory=lambda: {"electromagnetics"})
    solution_type: str = "unknown"


class MeshRecord(StrictModel):
    topology: str = "unknown"
    elements: int | None = Field(default=None, ge=0)
    quality_min: float | None = None
    quality_mean: float | None = None


class FieldEvidence(StrictModel):
    quantity: str
    path: str
    units: str
    normalization: str
    phasor_convention: str = "unknown"
    topology: str = "unknown"

    @field_validator("path")
    @classmethod
    def relative_path_only(cls, value: str) -> str:
        _validate_relative_path(value)
        return value


class MaterialEvidence(StrictModel):
    name: str
    category: str
    properties: dict[str, float | str] = Field(default_factory=dict)


class BoundaryEvidence(StrictModel):
    name: str
    kind: str
    assignments: list[str] = Field(default_factory=list)


class SimulationManifest(StrictModel):
    schema_version: str = Field(default="2.0.0", pattern=r"^2\.")
    run_id: str = Field(min_length=1)
    solver: SolverRecord
    physics: PhysicsRecord
    provenance: dict[str, Any] = Field(default_factory=dict)
    conventions: dict[str, str] = Field(default_factory=dict)
    mesh: MeshRecord | None = None
    fields: list[FieldEvidence] = Field(default_factory=list)
    materials: list[MaterialEvidence] = Field(default_factory=list)
    boundaries: list[BoundaryEvidence] = Field(default_factory=list)
    capabilities: set[str] = Field(default_factory=set)
    evidence: dict[str, Status] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)

    @field_validator("files")
    @classmethod
    def relative_paths_only(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            _validate_relative_path(path)
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"invalid SHA-256 digest for {path}")
        return value


class AdapterProtocol(Protocol):
    solver: str

    def import_bundle(self, source: Path) -> SimulationManifest: ...


def _validate_relative_path(value: str) -> None:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or value in {"", "."}:
        raise ValueError(f"file path must be bundle-relative: {value}")


def _hash_files(source: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"bundle symlinks are forbidden: {path}")
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


@dataclass(frozen=True)
class PortableAdapter:
    """Import portable artifacts without pretending to parse proprietary databases."""

    solver: str
    supported_suffixes: tuple[str, ...] = (".s2p", ".csv", ".h5", ".json")

    def import_bundle(self, source: Path) -> SimulationManifest:
        source = Path(source)
        if not source.is_dir():
            raise FileNotFoundError(source)
        manifest_file = source / "simulation-manifest.json"
        if manifest_file.is_file():
            manifest = SimulationManifest.model_validate_json(
                manifest_file.read_text(encoding="utf-8")
            )
            if manifest.solver.name.casefold() != self.solver:
                raise ValueError(
                    f"manifest solver {manifest.solver.name!r} does not match {self.solver!r}"
                )
            actual = _hash_files(source)
            actual.pop("simulation-manifest.json", None)
            for path, expected_hash in manifest.files.items():
                if actual.get(path) != expected_hash:
                    raise ValueError(f"missing or changed manifest artifact: {path}")
            for field in manifest.fields:
                if field.path not in manifest.files:
                    raise ValueError(f"field is not covered by manifest hashes: {field.path}")
            return manifest

        files = _hash_files(source)
        capabilities = {
            suffix.removeprefix(".")
            for suffix in self.supported_suffixes
            if any(path.casefold().endswith(suffix) for path in files)
        }
        evidence = {capability: Status.WARNING for capability in capabilities}
        for expected in ("mesh", "fields", "materials", "boundaries", "convergence"):
            evidence.setdefault(expected, Status.NOT_EVALUATED)
        return SimulationManifest(
            run_id=source.name,
            solver=SolverRecord(name=self.solver, adapter=f"portable-{self.solver}"),
            physics=PhysicsRecord(),
            capabilities=capabilities,
            evidence=evidence,
            files=files,
            provenance={
                "source_bundle": str(source.resolve()),
                "validated": False,
                "note": "Files were hashed but solver semantics were not independently validated.",
            },
        )


ADAPTERS = {
    name: PortableAdapter(name)
    for name in ("hfss", "palace", "comsol", "cst", "sonnet", "openems", "elmer")
}


@dataclass(frozen=True)
class Finding:
    code: str
    status: Status
    message: str
    recommendation: str = ""
    evidence: tuple[str, ...] = ()


def _presence_finding(data: dict[str, Any], key: str, code: str) -> Finding:
    if key not in data:
        return Finding(code, Status.NOT_EVALUATED, f"{key} evidence is absent")
    value = data[key]
    if value is None or (hasattr(value, "__len__") and len(value) == 0):
        return Finding(code, Status.WARNING, f"{key} evidence is empty")
    if isinstance(value, dict) and value.get("validated") is True:
        requested_status = value.get("status")
        if requested_status in {status.value for status in Status}:
            return Finding(code, Status(requested_status), f"{key} evidence was validated")
    return Finding(code, Status.WARNING, f"{key} evidence is present but not validated")


def diagnose(data: dict[str, Any]) -> list[Finding]:
    """Apply transparent rules to an evidence summary."""
    findings: list[Finding] = []
    passes = data.get("convergence_passes")
    if passes is None:
        findings.append(
            Finding("CONVERGENCE_MISSING", Status.NOT_EVALUATED, "No convergence evidence")
        )
    elif len(passes) < 2:
        findings.append(
            Finding(
                "CONVERGENCE_SHORT",
                Status.WARNING,
                "Fewer than two adaptive passes",
                "Export the full adaptive-pass history.",
            )
        )
    else:
        final_change = data.get("final_frequency_change_fraction")
        requested = data.get("requested_frequency_change_fraction")
        if final_change is None or requested is None:
            findings.append(
                Finding(
                    "CONVERGENCE_CRITERION_UNKNOWN",
                    Status.WARNING,
                    "Adaptive history is present but convergence criteria are missing",
                )
            )
        elif not all(
            isinstance(value, int | float) and 0 <= float(value) < float("inf")
            for value in (final_change, requested)
        ):
            findings.append(
                Finding("CONVERGENCE_INVALID", Status.FAIL, "Convergence criteria are invalid")
            )
        elif final_change > requested:
            findings.append(
                Finding(
                    "CONVERGENCE_CRITERION_MISSED",
                    Status.FAIL,
                    f"Final frequency change {final_change:.3g} exceeds {requested:.3g}",
                    "Continue adaptive refinement or revise the mesh/model.",
                )
            )
        else:
            findings.append(
                Finding("CONVERGENCE_PRESENT", Status.PASS, "Adaptive history is present")
            )

    mesh = data.get("mesh_quality")
    if mesh is None:
        findings.append(Finding("MESH_MISSING", Status.NOT_EVALUATED, "No mesh evidence"))
    elif len(mesh) == 0:
        findings.append(Finding("MESH_EMPTY", Status.WARNING, "Mesh quality array is empty"))
    elif not all(
        isinstance(value, int | float) and float("-inf") < float(value) < float("inf")
        for value in mesh
    ):
        findings.append(
            Finding("MESH_INVALID", Status.FAIL, "Mesh quality contains nonfinite data")
        )
    elif min(mesh) < float(data.get("mesh_quality_min", 0.1)):
        findings.append(
            Finding(
                "MESH_QUALITY_LOW",
                Status.FAIL,
                "Mesh quality is below the configured threshold",
                "Inspect and refine the lowest-quality region.",
            )
        )
    else:
        findings.append(Finding("MESH_QUALITY_OK", Status.PASS, "Mesh quality meets threshold"))

    hotspots = data.get("field_hotspots")
    if hotspots is None:
        findings.append(_presence_finding(data, "field_hotspots", "FIELD_HOTSPOT"))
    elif len(hotspots) == 0:
        findings.append(Finding("FIELD_HOTSPOT", Status.WARNING, "Hotspot evidence is empty"))
    elif not all(
        isinstance(value, int | float) and float("-inf") < float(value) < float("inf")
        for value in hotspots
    ):
        findings.append(Finding("FIELD_HOTSPOT", Status.FAIL, "Hotspot evidence is nonfinite"))
    elif any(float(value) > float(data.get("hotspot_limit", 1.0)) for value in hotspots):
        findings.append(
            Finding(
                "FIELD_HOTSPOT",
                Status.WARNING,
                "One or more normalized hotspots exceed the configured limit",
                "Inspect local curvature, gaps, interfaces, and mesh resolution.",
            )
        )
    else:
        findings.append(Finding("FIELD_HOTSPOT", Status.PASS, "No hotspot exceeds the limit"))

    findings.extend(
        [
            _presence_finding(data, "participation", "PARTICIPATION"),
            _presence_finding(data, "coupling", "COUPLING"),
        ]
    )
    return findings


def answer_query(findings: list[Finding], query: str) -> str:
    """Render a local rule-based report without implying that an LLM ran."""
    terms = {term for term in query.casefold().split() if len(term) > 2}
    relevant = [
        finding
        for finding in findings
        if any(term in f"{finding.code} {finding.message}".casefold() for term in terms)
    ]
    rows = relevant or findings
    return "Local QResAudit rule-based report (no external AI execution):\n" + "\n".join(
        f"[{finding.status}] {finding.code}: {finding.message}"
        + (f" Recommendation: {finding.recommendation}" if finding.recommendation else "")
        for finding in rows
    )
