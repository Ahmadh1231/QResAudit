"""Readers for mesh statistics exports; unknown vendor columns remain evidence."""

from pathlib import Path
from typing import Any

import pandas as pd

CANONICAL_COLUMNS = ["pass_number", "tetrahedra", "triangles", "vertices", "raw_evidence_path"]


def parse_mesh(path: Path) -> pd.DataFrame:
    try:
        table = pd.read_csv(path)
    except Exception:
        table = pd.read_csv(path, sep=r"\s+", engine="python", comment="#")
    aliases = {str(c).strip().lower().replace(" ", "_"): c for c in table.columns}
    if table.empty:
        raise ValueError("mesh-statistics export contains no rows")

    def find(*names: str) -> Any | None:
        return next((aliases[n] for n in names if n in aliases), None)

    out = pd.DataFrame()
    p = find("pass_number", "pass", "iteration")
    if find("tetrahedra", "tetra", "elements") is None:
        raise ValueError("mesh-statistics export has no tetrahedra/elements column")
    out["pass_number"] = pd.to_numeric(table[p], errors="coerce") if p else range(1, len(table) + 1)
    for dest, names in [
        ("tetrahedra", ("tetrahedra", "tetra", "elements")),
        ("triangles", ("triangles", "faces")),
        ("vertices", ("vertices", "nodes")),
    ]:
        src = find(*names)
        out[dest] = pd.to_numeric(table[src], errors="coerce") if src else float("nan")
    out["raw_evidence_path"] = str(path)
    out.attrs["raw_text"] = path.read_text(encoding="utf-8-sig", errors="replace")
    return out[CANONICAL_COLUMNS]
