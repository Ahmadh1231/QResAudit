import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from qresaudit.hashing import sha256_file
from qresaudit.io.field_tab import PARSER_VERSION, ParsedField


def write_field_hdf5(path: Path, parsed: ParsedField, metadata: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(parsed.values, dtype=np.complex128)
    effective = {
        "quantity": parsed.quantity,
        "value_units": parsed.value_units,
        "coordinate_units": parsed.coordinate_units,
        "parser_version": PARSER_VERSION,
        **metadata,
    }
    with h5py.File(path, "w") as h5:
        coordinates = h5.create_group("coordinates")
        coordinates.create_dataset(
            "points",
            data=np.asarray(parsed.coordinates_m, dtype=np.float64),
            compression="gzip",
            shuffle=True,
        )
        field = h5.create_group("field")
        field.create_dataset("real", data=np.real(values), compression="gzip", shuffle=True)
        field.create_dataset("imag", data=np.imag(values), compression="gzip", shuffle=True)
        magnitude = np.linalg.norm(values, axis=-1) if parsed.is_vector else np.abs(values)
        field.create_dataset("magnitude", data=magnitude, compression="gzip", shuffle=True)
        meta = h5.create_group("metadata")
        for key, value in effective.items():
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, separators=(",", ":"))
            meta.attrs[key] = value
    return path


def read_field_hdf5(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    with h5py.File(path, "r") as h5:
        coordinates = np.asarray(h5["coordinates/points"][...])
        real = np.asarray(h5["field/real"][...])
        imag = np.asarray(h5["field/imag"][...])
        magnitude = np.asarray(h5["field/magnitude"][...])
        metadata = {key: value for key, value in h5["metadata"].attrs.items()}
    return coordinates, real + 1j * imag, magnitude, metadata


def source_metadata(raw_path: Path) -> dict[str, str]:
    return {"source_raw_file": raw_path.name, "source_raw_sha256": sha256_file(raw_path)}
