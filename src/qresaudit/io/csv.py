from pathlib import Path

import pandas as pd


def read_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    data = pd.read_csv(path)
    missing = required_columns - set(data.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
    return data


def read_eigenmodes(path: Path) -> pd.DataFrame:
    return read_csv(
        path,
        {
            "mode",
            "frequency_real_hz",
            "frequency_imag_hz",
            "q_hfss_unloaded",
            "source_solution",
            "variation_id",
        },
    )


def read_s_parameters(path: Path) -> pd.DataFrame:
    data = read_csv(path, {"frequency_hz"})
    complex_columns = [name for name in data.columns if name.startswith(("re_S", "im_S"))]
    if not complex_columns:
        raise ValueError("S-parameter CSV has no complex data columns")
    return data
