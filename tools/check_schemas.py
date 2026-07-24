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
        if actual != model.model_json_schema():
            print(f"schema mismatch: {path}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
