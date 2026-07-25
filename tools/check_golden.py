"""Report completeness of real-solver golden evidence without inventing substitutes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FAMILIES = ("cpw_resonator", "idc_resonator", "spiral_resonator", "eigenmode_cavity")
REQUIRED = ("bundle/manifest.json", "expected_results.json", "manual_review.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless every real-solver family is complete",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "examples" / "golden"
    families: dict[str, dict[str, object]] = {}
    for family in FAMILIES:
        missing = [relative for relative in REQUIRED if not (root / family / relative).is_file()]
        families[family] = {"complete": not missing, "missing": missing}
    result = {
        "complete": all(bool(item["complete"]) for item in families.values()),
        "synthetic_data_satisfies_gate": False,
        "families": families,
    }
    print(json.dumps(result, indent=2))
    return 1 if args.require_complete and not result["complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
