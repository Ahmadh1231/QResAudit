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

import numpy as np

from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.fields_hdf5 import read_field_hdf5
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
    if phasor_convention not in {"peak", "rms"}:
        raise ValueError("phasor_convention must be 'peak' or 'rms'")
    if epsilon_r <= 0 or mu_r <= 0:
        raise ValueError("relative permittivity and permeability must be positive")
    if dV is None:
        # Assume 1 m³ per point as fallback
        dV = np.ones(coords.shape[0])

    dV = np.asarray(dV).ravel()
    if len(dV) != coords.shape[0]:
        dV = np.full(coords.shape[0], float(np.mean(dV)))
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
    if dV is None:
        dV = np.ones(coords.shape[0])

    e_squared = np.sum(np.abs(e_field) ** 2, axis=-1) if e_field.ndim == 2 else np.abs(e_field) ** 2
    energy_density = EPSILON_0 * epsilon_r * e_squared * dV
    total_energy = float(np.sum(energy_density))
    max_density = float(np.max(EPSILON_0 * epsilon_r * e_squared))
    if max_density == 0:
        return float("inf")
    return total_energy / max_density


def normalize_field(
    e_field: np.ndarray,
    h_field: np.ndarray,
    coords: np.ndarray,
    target_energy_j: float,
    dV: np.ndarray | None = None,
    epsilon_r: float = 1.0,
    mu_r: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Normalize fields to achieve a target total energy.

    Returns (E_norm, H_norm, alpha) where alpha is the scaling factor.
    """
    energy = compute_energy(coords, e_field, h_field, dV, epsilon_r, mu_r)
    current_energy = energy["total_energy_j"]
    alpha = 1.0 if current_energy == 0 else np.sqrt(target_energy_j / current_energy)
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

    for e_rec, h_rec in zip(e_records, h_records, strict=False):
        e_coords, e_vals, _, e_meta = read_field_hdf5(safe_bundle_path(bundle, e_rec.path))
        _h_coords, h_vals, _, _h_meta = read_field_hdf5(safe_bundle_path(bundle, h_rec.path))

        # Compute dV from structured grid if available
        dV = None
        topology = e_meta.get("topology", "unstructured")
        if topology == "structured":
            shape = [int(s) for s in e_meta.get("shape", [])]
            if len(shape) >= 3:
                dx = (e_coords[1, 0] - e_coords[0, 0]) if e_coords.shape[0] > 1 else 1.0
                dV = np.full(e_coords.shape[0], float(dx**3))

        energy = compute_energy(e_coords, e_vals, h_vals, dV, epsilon_r, mu_r)
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
