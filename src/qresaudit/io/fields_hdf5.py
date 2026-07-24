import json
from pathlib import Path
from typing import Any, Literal, cast

import h5py
import numpy as np

from qresaudit.exceptions import FieldGridOrderingError
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
    topology = str(
        metadata.get(
            "topology", "structured" if metadata.get("grid_type") == "Cartesian" else "unstructured"
        )
    )
    if topology not in {"structured", "unstructured"}:
        raise ValueError("field topology must be structured or unstructured")
    if len(values) != len(parsed.coordinates_m):
        raise ValueError("field coordinates and values have inconsistent lengths")
    if not np.all(np.isfinite(parsed.coordinates_m)) or not np.all(np.isfinite(values)):
        raise ValueError("field coordinates and values must be finite")
    schema_version = str(metadata.get("schema_version", "0.1.1"))
    logical_shape = [int(value) for value in metadata.get("shape", [len(values)])]
    if topology == "structured" and int(np.prod(logical_shape, dtype=np.int64)) != len(values):
        raise ValueError("structured grid shape does not match field point count")
    stored_values = values
    structured_axes: dict[str, np.ndarray] = {}
    if topology == "structured":
        axis_order = list(metadata.get("axis_order", ["x", "y", "z"]))
        if axis_order != ["x", "y", "z"]:
            raise ValueError("structured grid axis_order must be ['x', 'y', 'z']")
        order = cast(Literal["C", "F"], str(metadata.get("flattening_order", "C")))
        if order not in {"C", "F"}:
            raise ValueError("flattening order must be C or F")
        axis_values = metadata.get("axes", {})
        for index, axis in enumerate(("x", "y", "z")):
            values_for_axis = np.asarray(
                axis_values.get(axis, np.unique(parsed.coordinates_m[:, index])),
                dtype=np.float64,
            )
            if values_for_axis.ndim != 1 or len(values_for_axis) != logical_shape[index]:
                raise ValueError(f"structured {axis}-axis length does not match grid shape")
            if not np.all(np.isfinite(values_for_axis)):
                raise ValueError(f"structured {axis}-axis values must be finite")
            structured_axes[axis] = values_for_axis
        mesh = np.meshgrid(
            structured_axes["x"],
            structured_axes["y"],
            structured_axes["z"],
            indexing="ij",
        )
        expected_coordinates = np.column_stack([component.ravel(order=order) for component in mesh])
        if not np.allclose(
            expected_coordinates,
            parsed.coordinates_m,
            rtol=1e-12,
            atol=1e-15,
        ):
            raise FieldGridOrderingError(
                "coordinate order does not match declared structured-grid ordering"
            )
        stored_shape: tuple[int, ...] = (
            (*logical_shape, int(values.shape[-1])) if parsed.is_vector else tuple(logical_shape)
        )
        stored_values = np.reshape(values, stored_shape, order=order)
    with h5py.File(path, "w") as h5:
        h5.attrs["schema_version"] = schema_version
        h5.attrs["topology"] = topology
        coordinates = h5.create_group("coordinates")
        coordinates.create_dataset(
            "points",
            data=np.asarray(parsed.coordinates_m, dtype=np.float64),
            compression="gzip",
            shuffle=True,
        )
        coordinates["points"].attrs["units"] = parsed.coordinate_units
        coordinates["points"].attrs["semantics"] = "sample_point_coordinates"
        coordinates["points"].attrs["dataset_axis_order"] = json.dumps(["point", "coordinate"])
        coordinates["points"].attrs["coordinate_labels"] = json.dumps(["x", "y", "z"])
        coordinates["points"].attrs["flattening_order"] = metadata.get("flattening_order", "C")
        if topology == "structured":
            for axis in ("x", "y", "z"):
                coordinates.create_dataset(
                    axis,
                    data=structured_axes[axis],
                )
        field = h5.create_group("field")
        field.create_dataset("real", data=np.real(stored_values), compression="gzip", shuffle=True)
        field.create_dataset("imag", data=np.imag(stored_values), compression="gzip", shuffle=True)
        magnitude = (
            np.linalg.norm(stored_values, axis=-1) if parsed.is_vector else np.abs(stored_values)
        )
        field.create_dataset("magnitude", data=magnitude, compression="gzip", shuffle=True)
        for name in ("real", "imag"):
            field[name].attrs["units"] = parsed.value_units
            field[name].attrs["semantics"] = "field_component"
            field[name].attrs["component_labels"] = json.dumps(
                ["x", "y", "z"] if parsed.is_vector else ["scalar"]
            )
            dataset_axis_order = (
                [*metadata.get("axis_order", ["x", "y", "z"]), "component"]
                if topology == "structured" and parsed.is_vector
                else (
                    metadata.get("axis_order", ["x", "y", "z"])
                    if topology == "structured"
                    else (["point", "component"] if parsed.is_vector else ["point"])
                )
            )
            field[name].attrs["dataset_axis_order"] = json.dumps(dataset_axis_order)
            field[name].attrs["flattening_order"] = metadata.get("flattening_order", "C")
        field["magnitude"].attrs["units"] = parsed.value_units
        field["magnitude"].attrs["semantics"] = "field_magnitude"
        field["magnitude"].attrs["dataset_axis_order"] = json.dumps(
            metadata.get("axis_order", ["x", "y", "z"]) if topology == "structured" else ["point"]
        )
        field["magnitude"].attrs["flattening_order"] = metadata.get("flattening_order", "C")
        meta = h5.create_group("metadata")
        for key, value in effective.items():
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, separators=(",", ":"))
            meta.attrs[key] = value
        grid = h5.create_group("grid")
        grid.attrs["shape"] = np.asarray(logical_shape, dtype=np.int64)
        grid.attrs["axis_order"] = json.dumps(metadata.get("axis_order", ["x", "y", "z"]))
        grid.attrs["flattening_order"] = metadata.get("flattening_order", "C")
        grid.attrs["coordinate_system"] = metadata.get("coordinate_system", "cartesian")
        if metadata.get("angular_units") is not None:
            grid.attrs["angular_units"] = metadata["angular_units"]
        field.attrs["representation"] = metadata.get("representation", "complex_phasor")
        field.attrs["phasor_convention"] = metadata.get("phasor_convention", "unknown")
        field.attrs["excitation_context"] = json.dumps(metadata.get("excitation_context", {}))
    return path


def read_field_hdf5(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    with h5py.File(path, "r") as h5:
        coordinates = np.asarray(h5["coordinates/points"][...])
        real = np.asarray(h5["field/real"][...])
        imag = np.asarray(h5["field/imag"][...])
        magnitude = np.asarray(h5["field/magnitude"][...])
        metadata = {key: _decode_attribute(value) for key, value in h5["metadata"].attrs.items()}
        metadata.setdefault(
            "schema_version", _decode_attribute(h5.attrs.get("schema_version", "0.1.0"))
        )
        metadata.setdefault("topology", _decode_attribute(h5.attrs.get("topology", "unstructured")))
        if "grid" in h5:
            metadata.setdefault("shape", _decode_attribute(h5["grid"].attrs.get("shape", [])))
            metadata.setdefault(
                "axis_order",
                _decode_attribute(h5["grid"].attrs.get("axis_order", '["x","y","z"]')),
            )
            metadata.setdefault(
                "flattening_order",
                _decode_attribute(h5["grid"].attrs.get("flattening_order", "C")),
            )
        topology = str(metadata.get("topology", "unstructured"))
        shape = tuple(int(value) for value in metadata.get("shape", []))
        if topology == "structured":
            if len(shape) != 3:
                raise ValueError("structured grid shape must contain three axes")
            vector = real.ndim == len(shape) + 1
            expected_value_shape = (*shape, 3) if vector else shape
            expected_magnitude_shape = shape
            shape_valid = (
                len(shape) == 3
                and int(np.prod(shape, dtype=np.int64)) == coordinates.shape[0]
                and real.shape == expected_value_shape
            )
            if metadata.get("axis_order") != ["x", "y", "z"]:
                raise ValueError("structured grid axis order is invalid")
            order = cast(Literal["C", "F"], str(metadata.get("flattening_order", "C")))
            if order not in {"C", "F"}:
                raise ValueError("flattening order must be C or F")
            try:
                stored_axes = [
                    np.asarray(h5[f"coordinates/{axis}"][...], dtype=np.float64)
                    for axis in ("x", "y", "z")
                ]
            except KeyError as exc:
                raise ValueError("structured coordinate-axis dataset is missing") from exc
            if any(
                axis.ndim != 1 or len(axis) != shape[index]
                for index, axis in enumerate(stored_axes)
            ):
                raise ValueError("structured coordinate-axis length is invalid")
            mesh = np.meshgrid(*stored_axes, indexing="ij")
            expected_coordinates = np.column_stack(
                [component.ravel(order=order) for component in mesh]
            )
            if not np.allclose(
                expected_coordinates,
                coordinates,
                rtol=1e-12,
                atol=1e-15,
            ):
                raise FieldGridOrderingError(
                    "stored coordinates do not match structured-grid ordering"
                )
            expected_dataset_axes = (
                ["x", "y", "z", "component"]
                if vector
                else [
                    "x",
                    "y",
                    "z",
                ]
            )
            for name in ("real", "imag"):
                actual_dataset_axes = _decode_attribute(
                    h5[f"field/{name}"].attrs.get("dataset_axis_order", "")
                )
                if actual_dataset_axes != expected_dataset_axes:
                    raise ValueError(f"field/{name} dataset axis order is invalid")
            magnitude_axes = _decode_attribute(
                h5["field/magnitude"].attrs.get("dataset_axis_order", "")
            )
            if magnitude_axes != ["x", "y", "z"]:
                raise ValueError("field/magnitude dataset axis order is invalid")
        else:
            expected_magnitude_shape = real.shape[:-1] if real.ndim > 1 else real.shape
            shape_valid = coordinates.shape[0] == real.shape[0]
        if (
            not shape_valid
            or real.shape != imag.shape
            or magnitude.shape != expected_magnitude_shape
        ):
            raise ValueError("HDF5 field datasets have inconsistent shapes")
        if (
            not np.all(np.isfinite(coordinates))
            or not np.all(np.isfinite(real))
            or not np.all(np.isfinite(imag))
        ):
            raise ValueError("HDF5 field datasets contain nonfinite values")
        values = real + 1j * imag
        if topology == "structured":
            point_count = coordinates.shape[0]
            values = values.reshape(
                (point_count, values.shape[-1]) if values.ndim == 4 else (point_count,),
                order=order,
            )
            magnitude = magnitude.reshape((point_count,), order=order)
    return coordinates, values, magnitude, metadata


def _decode_attribute(value: Any) -> Any:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, np.ndarray):
        return [_decode_attribute(item) for item in value.tolist()]
    return value


def source_metadata(raw_path: Path) -> dict[str, str]:
    return {"source_raw_file": raw_path.name, "source_raw_sha256": sha256_file(raw_path)}
