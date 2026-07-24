import re
from pathlib import Path

import numpy as np
import skrf as rf

from qresaudit.exceptions import DataFormatError

_FREQUENCY_UNIT_NAMES = {
    "HZ": "Hz",
    "KHZ": "kHz",
    "MHZ": "MHz",
    "GHZ": "GHz",
}


def load_network(path: Path) -> rf.Network:
    try:
        network = rf.Network(str(path))
    except Exception as exc:
        raise DataFormatError("TOUCHSTONE_PARSE_FAILED") from exc
    if network.nports < 1:
        raise DataFormatError("TOUCHSTONE_NO_PORTS")
    if not np.all(np.isfinite(network.f)):
        raise DataFormatError("TOUCHSTONE_NONFINITE_FREQUENCY")
    if not np.all(np.diff(network.f) > 0):
        raise DataFormatError("TOUCHSTONE_NONMONOTONIC_FREQUENCY")
    if not np.all(np.isfinite(network.s)):
        raise DataFormatError("TOUCHSTONE_NONFINITE_S")
    return network


def write_s_parameter_csv(network: rf.Network, path: Path) -> Path:
    columns = ["frequency_hz"]
    arrays: list[np.ndarray] = [network.f]
    for destination in range(network.nports):
        for source in range(network.nports):
            label = f"S{destination + 1}_{source + 1}"
            columns.extend((f"re_{label}", f"im_{label}"))
            arrays.extend(
                (network.s[:, destination, source].real, network.s[:, destination, source].imag)
            )
    matrix = np.column_stack(arrays)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, matrix, delimiter=",", header=",".join(columns), comments="", fmt="%.17g")
    return path


def touchstone_file_metadata(path: Path) -> dict[str, str | float | None]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    version = "1.0"
    matrix_format = "full"
    frequency_unit: str | None = None
    parameter_type: str | None = None
    data_format: str | None = None
    header_reference_impedance_ohm: float | None = None
    version_match = re.search(r"(?im)^\s*\[Version\]\s+(\S+)", text)
    if version_match:
        version = version_match.group(1)
    matrix_match = re.search(r"(?im)^\s*\[Matrix\s+Format\]\s+(\S+)", text)
    if matrix_match:
        matrix_format = matrix_match.group(1).lower()
    option_match = re.search(r"(?im)^\s*#\s*(\S+)\s+(\S+)\s+(\S+)", text)
    if option_match:
        frequency_unit, parameter_type, data_format = (
            value.upper() for value in option_match.groups()
        )
        frequency_unit = _FREQUENCY_UNIT_NAMES.get(frequency_unit, frequency_unit)
    reference_match = re.search(
        r"(?im)^\s*#(?:\s+\S+){3}\s+R\s+"
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
        text,
    )
    if reference_match:
        header_reference_impedance_ohm = float(reference_match.group(1))
    return {
        "touchstone_version": version,
        "frequency_unit": frequency_unit,
        "parameter_type": parameter_type,
        "data_format": data_format,
        "matrix_format": matrix_format,
        "header_reference_impedance_ohm": header_reference_impedance_ohm,
    }


def network_metadata(
    network: rf.Network,
    path: str,
    port_names: list[str],
    *,
    source_file: Path | None = None,
) -> dict[str, object]:
    z0 = np.asarray(network.z0)
    file_metadata = (
        touchstone_file_metadata(source_file)
        if source_file is not None
        else {
            "touchstone_version": "1.0",
            "frequency_unit": None,
            "parameter_type": None,
            "data_format": None,
            "matrix_format": "full",
            "header_reference_impedance_ohm": None,
        }
    )
    parsed_names = getattr(network, "port_names", None)
    if isinstance(parsed_names, list) and len(parsed_names) == network.nports:
        port_order_verified = True
        names = [str(value) for value in parsed_names]
    else:
        port_order_verified = False
        names = (
            port_names
            if len(port_names) == network.nports
            else [f"port_{index + 1}" for index in range(network.nports)]
        )
    return {
        "path": path,
        "number_of_ports": network.nports,
        "frequency_unit": file_metadata["frequency_unit"]
        or str(getattr(network.frequency, "unit", "Hz")),
        "parameter_type": file_metadata["parameter_type"] or "S",
        "data_format": file_metadata["data_format"] or "RI",
        "renormalized": False,
        "reference_impedance_ohm": None,
        "header_reference_impedance_ohm": file_metadata["header_reference_impedance_ohm"],
        "reference_impedance_real_ohm": np.real(z0).tolist(),
        "reference_impedance_imag_ohm": np.imag(z0).tolist(),
        "renormalization_impedance_ohm": None,
        "source_impedance_preserved": True,
        "source_impedance_path": None,
        "source_reference_impedance_real_ohm": [],
        "source_reference_impedance_imag_ohm": [],
        "touchstone_version": file_metadata["touchstone_version"],
        "wave_definition": str(getattr(network, "s_def", "power")),
        "matrix_format": file_metadata["matrix_format"],
        "port_names": names,
        "source_excitation_names": port_names,
        "port_order_verified": port_order_verified,
        "frequency_min_hz": float(network.f[0]),
        "frequency_max_hz": float(network.f[-1]),
        "point_count": len(network.f),
    }
