"""Version-aware, evidence-preserving profile reader."""

import re
from pathlib import Path


def parse_profile(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    values: dict[str, object] = {"raw_evidence_path": str(path), "raw_text": text}
    for line in text.splitlines():
        match = re.match(r"\s*([^:=]+)\s*[:=]\s*(.+?)\s*$", line)
        if match:
            key, value = match.groups()
            values[key.strip().lower().replace(" ", "_")] = value
    values["parser_version"] = "0.1.1"
    return values
