"""Report completeness of real-solver golden evidence without inventing substitutes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from qresaudit.validation.engine import validate_bundle

FAMILIES = ("cpw_resonator", "idc_resonator", "spiral_resonator", "eigenmode_cavity")
REQUIRED = (
    "bundle/manifest.json",
    "bundle/checksums.sha256",
    "expected_results.json",
    "manual_review.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect_family(root: Path, family: str) -> dict[str, object]:
    family_root = root / family
    missing = [relative for relative in REQUIRED if not (family_root / relative).is_file()]
    issues: list[str] = []
    if missing:
        return {"complete": False, "missing": missing, "issues": issues}

    bundle = family_root / "bundle"
    validation = validate_bundle(bundle, strict=True)
    issues.extend(f"{diagnostic.code}: {diagnostic.message}" for diagnostic in validation.errors)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    quantities = {record.get("quantity") for record in manifest.get("fields", [])}
    if not {"E", "H"} <= quantities:
        issues.append("paired E and H field exports are required")
    roles = {record.get("role") for record in manifest.get("files", [])}
    if "convergence" not in roles:
        issues.append("convergence evidence is required")
    if "mesh_stats" not in roles:
        issues.append("mesh statistics are required")
    if manifest.get("solution_kind") != "eigenmode" and manifest.get("touchstone") is None:
        issues.append("driven simulations require Touchstone evidence")

    expected = json.loads((family_root / "expected_results.json").read_text(encoding="utf-8"))
    for key in (
        "solver",
        "solver_version",
        "project_sha256",
        "bundle_inventory_sha256",
        "metrics",
        "reviewer",
    ):
        if not expected.get(key):
            issues.append(f"expected_results.json is missing {key}")
    if expected.get("project_sha256") != manifest.get("project_file_sha256"):
        issues.append("expected project SHA-256 does not match the manifest")
    inventory_hash = _sha256(bundle / "checksums.sha256")
    if expected.get("bundle_inventory_sha256") != inventory_hash:
        issues.append("expected bundle inventory SHA-256 does not match checksums.sha256")

    review = json.loads((family_root / "manual_review.json").read_text(encoding="utf-8"))
    if review.get("status") != "PASS":
        issues.append("manual review status must be PASS")
    for key in ("reviewer", "reviewed_at_utc", "independent_machine", "metrics_verified"):
        if not review.get(key):
            issues.append(f"manual_review.json is missing {key}")
    if review.get("metrics_verified") is not True:
        issues.append("manual review must explicitly verify numerical metrics")

    return {"complete": not issues, "missing": missing, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless every real-solver family is complete",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "examples" / "golden"
    families = {family: _inspect_family(root, family) for family in FAMILIES}
    result = {
        "complete": all(bool(item["complete"]) for item in families.values()),
        "synthetic_data_satisfies_gate": False,
        "families": families,
    }
    print(json.dumps(result, indent=2))
    return 1 if args.require_complete and not result["complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
