"""Fail when checked-in stabilization schemas differ from the models."""

import json
from pathlib import Path

from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import HFSSRunManifest

ROOT = Path(__file__).parents[1] / "schemas"
SCHEMAS = {
    "export-config-0.1.schema.json": ExportConfig,
    "manifest-0.1.schema.json": HFSSRunManifest,
}


def main() -> int:
    failed = False
    for name, model in SCHEMAS.items():
        path = ROOT / name
        actual = json.loads(path.read_text(encoding="utf-8"))
        expected = model.model_json_schema()
        if actual != expected:
            print(f"schema mismatch: {path}")
            # Show top-level key differences
            actual_keys = set(actual.keys())
            expected_keys = set(expected.keys())
            if actual_keys != expected_keys:
                print(f"  keys only in checked-in: {actual_keys - expected_keys}")
                print(f"  keys only in live model: {expected_keys - actual_keys}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
