"""Generate the checked-in stabilization JSON Schemas."""

import json
from pathlib import Path

from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import HFSSRunManifest

ROOT = Path(__file__).parents[1] / "schemas"
SCHEMAS = {
    "export-config-0.1.schema.json": ExportConfig,
    "manifest-0.1.schema.json": HFSSRunManifest,
}


def main() -> None:
    for name, model in SCHEMAS.items():
        (ROOT / name).write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
