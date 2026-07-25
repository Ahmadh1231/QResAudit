"""Field integration and normalization — compute energy, mode volume, filling factors.

Supports Cartesian, cylindrical, and spherical grids with Jacobians.
Normalization targets: zero-point energy (ħω/2), one-photon (ħω),
n-photon energy, or user-defined classical energy.

Commands:
    qresaudit fields inspect BUNDLE
    qresaudit fields integrate BUNDLE --region SpinSample
    qresaudit fields normalize BUNDLE --mode 1 --energy zero-point
"""

from pathlib import Path
from typing import Any

import numpy as np

from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.models.manifest import FieldRecord
from qresaudit.models.v0_2 import FieldIntegrationResult

# Physical constants
HBAR = 1.054571817e-34  # J·s
EPSILON_0 = 8.8541878128e-12  # F/m
MU_0 = 4.0 * np.pi * 1e-7  # H/m


def cartesian_volume_element(
    grid_shape: tuple[int, ...], axis_values: dict[str, np.ndarray]
) -> np.ndarray:
    """Compute dV for each cell center in a Cartesian structured grid."""
    dx = axis_values["x"][1] - axis_values["x"][0] if len(axis_values.get("x", [])) > 1 else 0.0
    dy = axis_values["y"][1] - axis_values["y"][0] if len(axis_values.get("y", [])) > 1 else 0.0
    dz = axis_values["z"][1] - axis_values["z"][0] if len(axis_values.get("z", [])) > 1 else 0.0
    return np.full(grid_shape, dx * dy * dz)


def cylindrical_volume_element(r: np.ndarray, dr: float, dphi: float, dz: float) -> np.ndarray:
    """dV = r * dr * dphi * dz for cylindrical grid."""
    result: np.ndarray = np.asarray(np.abs(r) * dr * dphi * dz, dtype=float)
    return result


def spherical_volume_element(r: np.ndarray, dr: float, dtheta: float, dphi: float) -> np.ndarray:
    """dV = r² * sin(theta) * dr * dtheta * dphi for spherical grid."""
    theta = np.linspace(0, np.pi, r.shape[1]) if r.ndim > 1 else np.array([np.pi / 2])
    sin_theta = np.sin(theta)
    result: np.ndarray = np.asarray(
        (r**2)[:, np.newaxis] * sin_theta[np.newaxis, :] * dr * dtheta * dphi,
        dtype=float,
    )
    return result


def compute_energy(
    coords: np.ndarray,
    e_field: np.ndarray,
    h_field: np.ndarray,
    dV: np.ndarray | None = None,
    epsilon_r: float = 1.0,
    mu_r: float = 1.0,
    phasor_convention: str = "peak",
) -> dict[str, float]:
    """Compute electric and magnetic energy from field data.

    Parameters
    ----------
    coords : np.ndarray
        Coordinate array (N, 3) in meters.
    e_field : np.ndarray
        Electric field (N, 3) in V/m.
    h_field : np.ndarray
        Magnetic field (N, 3) in A/m.
    dV : np.ndarray | None
        Volume element array (N,). If None, computed as uniform grid.
    epsilon_r : float
        Relative permittivity.
    mu_r : float
        Relative permeability.

    Returns
    -------
    dict with keys: electric_energy_j, magnetic_energy_j, total_energy_j
    """
    coords = np.asarray(coords, dtype=float)
    e_field = np.asarray(e_field)
    h_field = np.asarray(h_field)
    if coords.ndim != 2 or coords.shape[1] != 3 or not np.all(np.isfinite(coords)):
        raise ValueError("coordinates must be a finite (N, 3) array")
    for name, field in (("electric", e_field), ("magnetic", h_field)):
        if field.shape[0] != coords.shape[0] or field.ndim not in {1, 2}:
            raise ValueError(f"{name} field must contain one value per coordinate")
        if field.ndim == 2 and field.shape[1] != 3:
            raise ValueError(f"{name} vector field must have shape (N, 3)")
        if not np.all(np.isfinite(field)):
            raise ValueError(f"{name} field must be finite")
    if phasor_convention not in {"peak", "rms"}:
        raise ValueError("phasor_convention must be 'peak' or 'rms'")
    if epsilon_r <= 0 or mu_r <= 0:
        raise ValueError("relative permittivity and permeability must be positive")
    if dV is None:
        raise ValueError("explicit volume elements are required for energy integration")

    dV = np.asarray(dV).ravel()
    if len(dV) != coords.shape[0]:
        raise ValueError("volume elements must contain one value per coordinate")
    if np.any(~np.isfinite(dV)) or np.any(dV < 0):
        raise ValueError("volume elements must be finite and non-negative")
    factor = 0.25 if phasor_convention == "peak" else 0.5

    # Electric energy: U_e = (1/2) ε₀ ε_r ∫ |E|² dV
    e_squared = np.sum(np.abs(e_field) ** 2, axis=-1) if e_field.ndim == 2 else np.abs(e_field) ** 2
    u_e = factor * EPSILON_0 * epsilon_r * float(np.sum(e_squared * dV))

    # Magnetic energy: U_m = (1/2) μ₀ μ_r ∫ |H|² dV
    h_squared = np.sum(np.abs(h_field) ** 2, axis=-1) if h_field.ndim == 2 else np.abs(h_field) ** 2
    u_m = factor * MU_0 * mu_r * float(np.sum(h_squared * dV))

    return {
        "electric_energy_j": u_e,
        "magnetic_energy_j": u_m,
        "total_energy_j": u_e + u_m,
    }


def effective_mode_volume(
    e_field: np.ndarray, coords: np.ndarray, dV: np.ndarray | None = None, epsilon_r: float = 1.0
) -> float:
    """Compute effective mode volume: V_eff = ∫ ε|E|² dV / max(ε|E|²)."""
    if epsilon_r <= 0:
        raise ValueError("relative permittivity must be positive")
    if dV is None:
        raise ValueError("explicit volume elements are required for mode volume")
    dV = np.asarray(dV).ravel()
    if len(dV) != coords.shape[0]:
        raise ValueError("volume elements must contain one value per coordinate")
    if np.any(~np.isfinite(dV)) or np.any(dV < 0):
        raise ValueError("volume elements must be finite and non-negative")

    e_squared = np.sum(np.abs(e_field) ** 2, axis=-1) if e_field.ndim == 2 else np.abs(e_field) ** 2
    energy_density = EPSILON_0 * epsilon_r * e_squared * dV
    total_energy = float(np.sum(energy_density))
    max_density = float(np.max(EPSILON_0 * epsilon_r * e_squared))
    if max_density == 0:
        return float("inf")
    return total_energy / max_density


def structured_volume_weights(coords: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
    """Build tensor-product trapezoidal volume weights for a 3D Cartesian grid."""
    coords = np.asarray(coords, dtype=float)
    if metadata.get("topology") != "structured":
        raise ValueError("volume integration requires a structured field grid")
    if metadata.get("axis_order") != ["x", "y", "z"]:
        raise ValueError("structured field axis order must be x, y, z")
    order = str(metadata.get("flattening_order", "C"))
    if order not in {"C", "F"}:
        raise ValueError("structured field flattening order must be C or F")
    shape = tuple(int(value) for value in metadata.get("shape", []))
    if len(shape) != 3 or int(np.prod(shape, dtype=np.int64)) != len(coords):
        raise ValueError("structured field shape does not match its coordinates")

    axis_weights: list[np.ndarray] = []
    for index, axis_name in enumerate(("x", "y", "z")):
        axis = np.unique(coords[:, index])
        if len(axis) != shape[index]:
            raise ValueError(f"{axis_name}-axis coordinate count does not match field shape")
        if len(axis) < 2:
            raise ValueError("3D volume integration requires at least two points on every axis")
        differences = np.diff(axis)
        if np.any(differences <= 0):
            raise ValueError(f"{axis_name}-axis coordinates must be strictly increasing")
        weights = np.empty_like(axis)
        weights[0] = differences[0] / 2.0
        weights[-1] = differences[-1] / 2.0
        if len(axis) > 2:
            weights[1:-1] = (axis[2:] - axis[:-2]) / 2.0
        axis_weights.append(weights)

    mesh = np.meshgrid(*axis_weights, indexing="ij")
    weights = mesh[0] * mesh[1] * mesh[2]
    return np.asarray(weights.ravel(order=order), dtype=float)


def _field_record_key(record: FieldRecord) -> tuple[object, ...]:
    return (
        record.mode,
        record.region_name,
        record.frequency_hz,
        record.excitation,
        tuple(sorted(record.variation.items())),
    )


def pair_electric_magnetic_records(
    electric_records: list[FieldRecord], magnetic_records: list[FieldRecord]
) -> list[tuple[FieldRecord, FieldRecord]]:
    """Pair E/H records by physical context and reject missing or duplicate evidence."""
    electric = {_field_record_key(record): record for record in electric_records}
    magnetic = {_field_record_key(record): record for record in magnetic_records}
    if len(electric) != len(electric_records) or len(magnetic) != len(magnetic_records):
        raise ValueError("duplicate field records share the same physical context")
    if electric.keys() != magnetic.keys():
        missing_h = sorted(str(key) for key in electric.keys() - magnetic.keys())
        missing_e = sorted(str(key) for key in magnetic.keys() - electric.keys())
        raise ValueError(f"unpaired field evidence; missing H={missing_h}, missing E={missing_e}")
    if not electric:
        raise ValueError("no paired electric and magnetic field evidence found")
    return [(electric[key], magnetic[key]) for key in electric]


def normalize_field(
    e_field: np.ndarray,
    h_field: np.ndarray,
    coords: np.ndarray,
    target_energy_j: float,
    dV: np.ndarray | None = None,
    epsilon_r: float = 1.0,
    mu_r: float = 1.0,
    phasor_convention: str = "peak",
) -> tuple[np.ndarray, np.ndarray, float]:
    """Normalize fields to achieve a target total energy.

    Returns (E_norm, H_norm, alpha) where alpha is the scaling factor.
    """
    if not np.isfinite(target_energy_j) or target_energy_j <= 0:
        raise ValueError("target energy must be finite and positive")
    energy = compute_energy(
        coords,
        e_field,
        h_field,
        dV,
        epsilon_r,
        mu_r,
        phasor_convention,
    )
    current_energy = energy["total_energy_j"]
    if current_energy <= 0:
        raise ValueError("cannot normalize a zero-energy field")
    alpha = np.sqrt(target_energy_j / current_energy)
    return e_field * alpha, h_field * alpha, float(alpha)


# Energy conventions
def ZERO_POINT_ENERGY(omega: float) -> float:
    return 0.5 * HBAR * omega  # ħω/2


def ONE_PHOTON_ENERGY(omega: float) -> float:
    return HBAR * omega  # ħω


def N_PHOTON_ENERGY(omega: float, n: float) -> float:
    return n * HBAR * omega  # n·ħω


def integrate_bundle_fields(
    bundle: Path,
    mode: int | None = None,
    region_name: str | None = None,
    epsilon_r: float = 1.0,
    mu_r: float = 1.0,
) -> list[FieldIntegrationResult]:
    """Integrate field energies from a validated bundle."""
    manifest = load_manifest(bundle / "manifest.json")

    results: list[FieldIntegrationResult] = []
    e_records = [f for f in manifest.fields if f.quantity == "E"]
    h_records = [f for f in manifest.fields if f.quantity == "H"]

    if mode is not None:
        e_records = [f for f in e_records if f.mode == mode]
        h_records = [f for f in h_records if f.mode == mode]
    if region_name is not None:
        e_records = [f for f in e_records if f.region_name == region_name]
        h_records = [f for f in h_records if f.region_name == region_name]

    for e_rec, h_rec in pair_electric_magnetic_records(e_records, h_records):
        e_coords, e_vals, _, e_meta = read_field_hdf5(safe_bundle_path(bundle, e_rec.path))
        h_coords, h_vals, _, h_meta = read_field_hdf5(safe_bundle_path(bundle, h_rec.path))
        if not np.array_equal(e_coords, h_coords):
            raise ValueError("paired electric and magnetic fields use different coordinates")
        grid_keys = ("topology", "shape", "axis_order", "flattening_order")
        if {key: e_meta.get(key) for key in grid_keys} != {
            key: h_meta.get(key) for key in grid_keys
        }:
            raise ValueError("paired electric and magnetic fields use different grids")
        if e_rec.phasor_convention != h_rec.phasor_convention:
            raise ValueError("paired electric and magnetic fields use different phasor conventions")
        convention_value = e_rec.phasor_convention.value
        if convention_value.endswith("_peak"):
            phasor_convention = "peak"
        elif convention_value.endswith("_rms"):
            phasor_convention = "rms"
        else:
            raise ValueError("field phasor convention is unknown or not applicable")

        dV = structured_volume_weights(e_coords, e_meta)
        topology = e_meta.get("topology", "unstructured")

        energy = compute_energy(
            e_coords,
            e_vals,
            h_vals,
            dV,
            epsilon_r,
            mu_r,
            phasor_convention,
        )
        v_eff = effective_mode_volume(e_vals, e_coords, dV, epsilon_r)

        peak_e = (
            float(np.max(np.linalg.norm(e_vals, axis=-1)))
            if e_vals.ndim == 2
            else float(np.max(np.abs(e_vals)))
        )
        peak_h = (
            float(np.max(np.linalg.norm(h_vals, axis=-1)))
            if h_vals.ndim == 2
            else float(np.max(np.abs(h_vals)))
        )
        rms_e = (
            float(np.sqrt(np.mean(np.sum(np.abs(e_vals) ** 2, axis=-1))))
            if e_vals.ndim == 2
            else float(np.sqrt(np.mean(np.abs(e_vals) ** 2)))
        )
        rms_h = (
            float(np.sqrt(np.mean(np.sum(np.abs(h_vals) ** 2, axis=-1))))
            if h_vals.ndim == 2
            else float(np.sqrt(np.mean(np.abs(h_vals) ** 2)))
        )

        results.append(
            FieldIntegrationResult(
                region=e_rec.region_name,
                electric_energy_j=energy["electric_energy_j"],
                magnetic_energy_j=energy["magnetic_energy_j"],
                total_energy_j=energy["total_energy_j"],
                energy_imbalance=float(
                    abs(energy["electric_energy_j"] - energy["magnetic_energy_j"])
                    / (energy["total_energy_j"] + 1e-30)
                ),
                peak_e_field_v_per_m=peak_e,
                peak_h_field_a_per_m=peak_h,
                rms_e_field_v_per_m=rms_e,
                rms_h_field_a_per_m=rms_h,
                effective_mode_volume_m3=v_eff,
                filling_factor=0.0,
                normalization_factor=1.0,
                target_energy_j=energy["total_energy_j"],
                grid_resolution_m=[],
                integration_method="structured" if topology == "structured" else "uniform_dV",
                jacobian_used=False,
            )
        )

    return results
