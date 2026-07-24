"""Conservative readers for exported HFSS adaptive-pass tables."""

from pathlib import Path
from typing import Any

import pandas as pd

CANONICAL_COLUMNS = [
    "pass_number",
    "frequency_hz",
    "max_delta_s_percent",
    "converged",
    "raw_evidence_path",
]


def parse_convergence(path: Path) -> pd.DataFrame:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        table = pd.read_csv(path)
    except Exception:
        table = pd.read_csv(path, sep=r"\s+", engine="python", comment="#")
    aliases = {str(c).strip().lower().replace(" ", "_"): c for c in table.columns}
    if table.empty:
        raise ValueError("convergence export contains no adaptive-pass rows")

    def col(*names: str) -> Any | None:
        return next((aliases[n] for n in names if n in aliases), None)

    out = pd.DataFrame()
    out["pass_number"] = (
        table[col("pass_number", "pass", "iteration")].astype(int)
        if col("pass_number", "pass", "iteration")
        else range(1, len(table) + 1)
    )
    f = col("frequency_hz", "frequency", "freq_hz")
    d = col("max_delta_s_percent", "delta_s_percent", "delta_s", "max_delta_s")
    c = col("converged", "convergence")
    if f is None and d is None and c is None:
        raise ValueError("convergence export has no recognized convergence columns")
    out["frequency_hz"] = pd.to_numeric(table[f], errors="coerce") if f else float("nan")
    out["max_delta_s_percent"] = pd.to_numeric(table[d], errors="coerce") if d else float("nan")
    out["converged"] = (
        table[c].map(lambda x: str(x).strip().lower() in {"1", "true", "yes", "converged", "pass"})
        if c
        else out["max_delta_s_percent"].notna()
    )
    out["raw_evidence_path"] = str(path)
    out.attrs["raw_text"] = raw
    out.attrs["vendor_format"] = "generic_csv"
    return out[CANONICAL_COLUMNS]
