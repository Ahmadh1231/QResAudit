"""Generate a compact, integrity-addressed simulation paper package."""

import hashlib
import json
from pathlib import Path
from typing import Any


def generate_paper_package(
    output: Path,
    *,
    methods: str,
    parameters: dict[str, Any],
    inputs: list[Path],
    uncertainty: dict[str, Any] | None = None,
) -> Path:
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"paper-package inputs are missing: {missing}")
    output.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "path": f"input-{index:03d}-{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for index, path in enumerate(inputs, start=1)
    ]
    manifest = {
        "package_version": "2.0.0",
        "evidence_status": "NOT_EVALUATED",
        "inputs": data,
        "uncertainty": uncertainty or {},
    }
    (output / "methods.md").write_text(methods.rstrip() + "\n", encoding="utf-8")
    (output / "parameters.json").write_text(
        json.dumps(parameters, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "supplementary-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "data-index.json").write_text(
        json.dumps({"figures": [], "data": data}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
