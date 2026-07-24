from pathlib import Path

import numpy as np
import skrf as rf

from qresaudit.exceptions import DataFormatError


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


def network_metadata(network: rf.Network, path: str, port_names: list[str]) -> dict[str, object]:
    z0 = np.asarray(network.z0)
    reference = float(np.real(z0.flat[0])) if z0.size else None
    return {
        "path": path,
        "number_of_ports": network.nports,
        "frequency_unit": "Hz",
        "parameter_type": "S",
        "data_format": "RI",
        "renormalized": False,
        "reference_impedance_ohm": reference,
        "port_names": port_names,
        "frequency_min_hz": float(network.f[0]),
        "frequency_max_hz": float(network.f[-1]),
        "point_count": len(network.f),
    }
