"""Reproducible final design reports from caller-supplied evidence."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DesignReport:
    title: str
    design: dict[str, Any]
    evidence: list[dict[str, Any]]
    assumptions: list[str]
    provenance: dict[str, Any]
    status: str


def build_design_report(
    title: str,
    design: dict[str, Any],
    *,
    evidence: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
) -> DesignReport:
    supplied = evidence or []
    status = (
        "PASS"
        if supplied and all(item.get("status") == "PASS" for item in supplied)
        else "NOT_EVALUATED"
    )
    canonical = json.dumps(
        {"title": title, "design": design, "evidence": supplied, "assumptions": assumptions or []},
        sort_keys=True,
        default=str,
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return DesignReport(
        title,
        design,
        supplied,
        assumptions
        or ["No unprovided solver, experiment, literature, or AI evidence is inferred."],
        {"content_sha256": digest, "reproducible": True},
        status,
    )


def write_design_report(report: DesignReport, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return output
