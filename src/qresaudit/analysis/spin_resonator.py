"""Spin-resonator physics — magnetic coupling, cooperativity, and spin ensemble analysis.

Commands:
    qresaudit spin analyze BUNDLE --ensemble erbium.yaml
    qresaudit spin sweep BUNDLE --parameter orientation
"""

from pathlib import Path

import numpy as np

from qresaudit.analysis.field_integration import (
    HBAR,
    MU_0,
    ZERO_POINT_ENERGY,
    normalize_field,
)
from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.models.v0_2 import (
    SpinCouplingResult,
    SpinSampleConfig,
    SpinSweepResult,
)

# Physical constants
MU_B = 9.274009994e-24  # Bohr magneton (J/T)
K_B = 1.380649e-23  # Boltzmann constant (J/K)


def rotation_matrix_euler(alpha: float, beta: float, gamma: float) -> np.ndarray:
    """Z-Y-Z Euler rotation matrix (active rotation)."""
    ca, sa = np.cos(alpha), np.sin(alpha)
    cb, sb = np.cos(beta), np.sin(beta)
    cg, sg = np.cos(gamma), np.sin(gamma)
    return np.array(
        [
            [ca * cb * cg - sa * sg, -ca * cb * sg - sa * cg, ca * sb],
            [sa * cb * cg + ca * sg, -sa * cb * sg + ca * cg, sa * sb],
            [-sb * cg, sb * sg, cb],
        ]
    )


def effective_g_tensor(g_principal: list[float], orientation_euler_deg: list[float]) -> np.ndarray:
    """Build the effective g-tensor in the lab frame."""
    g_diag = np.diag(g_principal)
    alpha, beta, gamma = np.radians(orientation_euler_deg)
    R = rotation_matrix_euler(alpha, beta, gamma)
    return R @ g_diag @ R.T  # type: ignore[no-any-return]


def zero_point_magnetic_field(
    b_field_t: np.ndarray, coords: np.ndarray, dV: np.ndarray | None = None
) -> tuple[float, float]:
    """Compute RMS and peak zero-point B-field in Tesla.

    Returns (B_rms, B_peak) in Tesla.
    """
    if dV is None:
        dV = np.ones(coords.shape[0])

    b_squared = (
        np.sum(np.abs(b_field_t) ** 2, axis=-1) if b_field_t.ndim == 2 else np.abs(b_field_t) ** 2
    )
    b_rms = float(np.sqrt(np.mean(b_squared)))

    b_magnitude = np.sqrt(b_squared)
    b_peak = float(np.max(b_magnitude))

    return b_rms, b_peak


def single_spin_coupling(g_eff: float, b_zpf_rms_t: float, b_static_t: np.ndarray) -> float:
    """Compute single-spin coupling strength in Hz.

    g_single = g·μ_B·B_zpf / h
    """
    return float(abs(g_eff) * MU_B * b_zpf_rms_t / (2.0 * np.pi * HBAR))


def ensemble_coupling(
    g_single_hz: float, n_spins: float, thermal_polarization: float = 1.0
) -> float:
    """Compute ensemble coupling: g_ens = g_single · √(N_spins) · √(polarization)."""
    return float(g_single_hz * np.sqrt(abs(n_spins)) * np.sqrt(abs(thermal_polarization)))


def thermal_polarization(
    spin_number: float,
    temperature_k: float,
    frequency_hz: float,
    b_static_t: np.ndarray,
    g_eff: float,
) -> float:
    """Thermal polarization P = tanh(ħω / 2kT).

    For spin ensembles at low temperature, this reduces the effective
    spin number participating in the collective coupling.
    """
    if temperature_k <= 0:
        return 1.0
    # Zeeman energy splitting
    delta_e = g_eff * MU_B * np.linalg.norm(b_static_t)
    thermal = K_B * temperature_k
    if thermal <= 0:
        return 1.0
    return float(np.tanh(spin_number * delta_e / (2.0 * thermal)))


def magnetic_filling_factor(
    h_field: np.ndarray,
    coords: np.ndarray,
    region_mask: np.ndarray | None = None,
    dV: np.ndarray | None = None,
) -> float:
    """Compute the magnetic filling factor in a sample region.

    η = ∫_sample |B₁|² dV / ∫_total |B₁|² dV

    If region_mask is provided, integrate only within that region.
    """
    if dV is None:
        dV = np.ones(coords.shape[0])

    b_squared = np.sum(np.abs(h_field) ** 2, axis=-1) * (MU_0**2)  # |B|² from H

    sample_b_squared = b_squared * region_mask if region_mask is not None else b_squared

    total = float(np.sum(b_squared * dV))
    sample = float(np.sum(sample_b_squared * dV))

    return sample / total if total > 0 else 0.0


def analyze_spin_coupling(
    bundle: Path, sample_config: SpinSampleConfig, mode: int = 1
) -> SpinCouplingResult:
    """Analyze spin-resonator coupling from a validated bundle.

    Assumes the bundle contains H-field (magnetic field) data.
    """
    manifest = load_manifest(bundle / "manifest.json")

    # Find H-field for the target mode
    h_records = [f for f in manifest.fields if f.quantity == "H" and f.mode == mode]
    if not h_records:
        raise ValueError(f"no H-field found for mode {mode}")

    h_rec = h_records[0]
    coords, h_raw, _, meta = read_field_hdf5(safe_bundle_path(bundle, h_rec.path))
    frequency = float(meta.get("frequency_hz", h_rec.frequency_hz or 0))

    # HFSS eigenmode fields are normalized to peak |E|=1 V/m
    # We need to re-normalize to zero-point energy
    e_records = [f for f in manifest.fields if f.quantity == "E" and f.mode == mode]
    _e_coords, e_raw, _, _e_meta = (
        read_field_hdf5(safe_bundle_path(bundle, e_records[0].path))
        if e_records
        else (None, None, None, {})
    )

    dV = np.ones(coords.shape[0])

    # Normalize to zero-point energy
    target_energy = ZERO_POINT_ENERGY(2.0 * np.pi * frequency) if frequency > 0 else 1.0
    if e_raw is not None:
        _e_norm, h_norm, alpha = normalize_field(e_raw, h_raw, coords, target_energy, dV)
    else:
        # Normalize H directly using magnetic energy
        u_m = 0.5 * MU_0 * float(np.sum(np.sum(np.abs(h_raw) ** 2, axis=-1) * dV))
        alpha = np.sqrt(target_energy / u_m) if u_m > 0 else 1.0
        h_norm = h_raw * alpha

    # Convert H (A/m) to B (T): B = μ₀·H
    b_field = h_norm * MU_0

    b_static = np.array(sample_config.static_b_field_t)

    # Effective g-tensor
    g_tensor = effective_g_tensor(
        sample_config.g_tensor_principal,
        sample_config.g_tensor_orientation_euler_deg,
    )

    # Apply cavity orientation to static field
    b_static_rot = g_tensor @ b_static if np.any(b_static) else b_static
    g_eff = (
        float(np.linalg.norm(b_static_rot) / (np.linalg.norm(b_static) + 1e-30))
        if np.any(b_static)
        else abs(sample_config.g_tensor_principal[0])
    )

    b_rms, b_peak = zero_point_magnetic_field(b_field, coords, dV)

    filling = magnetic_filling_factor(h_raw, coords, None, dV)

    g_single = single_spin_coupling(g_eff, b_rms, b_static)
    polarization = thermal_polarization(
        sample_config.spin_number,
        sample_config.temperature_k,
        frequency,
        b_static,
        g_eff,
    )
    n_effective = sample_config.spin_density_per_m3 * (1.0)  # approximate volume

    g_ens = ensemble_coupling(g_single, n_effective, polarization)

    # Cavity decay rate
    kappa = float(2.0 * np.pi * frequency / 1000.0)  # approximate, Q~1000

    # Spin decay rate from linewidths
    gamma_spin = (
        2.0
        * np.pi
        * max(
            sample_config.inhomogeneous_linewidth_hz,
            sample_config.homogeneous_linewidth_hz,
        )
    )

    cooperativity = (4.0 * g_ens**2) / (kappa * gamma_spin) if kappa > 0 and gamma_spin > 0 else 0.0

    return SpinCouplingResult(
        sample_name=sample_config.name,
        frequency_hz=float(frequency),
        g_effective=float(g_eff),
        zero_point_b_field_rms_t=b_rms,
        zero_point_b_field_peak_t=b_peak,
        magnetic_filling_factor=filling,
        single_spin_coupling_hz=g_single,
        ensemble_coupling_hz=g_ens,
        thermal_polarization=float(polarization),
        cooperativity=float(cooperativity),
        strong_coupling=g_ens > (kappa / 4.0) and g_ens > (gamma_spin / 4.0),
        cavity_decay_rate_hz=float(kappa),
        spin_decay_rate_hz=float(gamma_spin),
        collective_coupling_hz=float(g_ens),
        effective_spin_number=n_effective,
    )


def sweep_parameter(
    bundle: Path, sample_config: SpinSampleConfig, parameter: str, values: list[float]
) -> SpinSweepResult:
    """Sweep a spin-sample parameter and return coupling vs parameter data.

    Currently supports: 'orientation' (B-field rotation axis sweep).
    """
    couplings: list[float] = []
    cooperativities: list[float] = []

    for val in values:
        if parameter == "orientation":
            # Sweep B-field orientation about z-axis
            cfg = sample_config.model_copy(deep=True)
            cfg.static_b_field_orientation_euler_deg = [0.0, 0.0, val]
            try:
                result = analyze_spin_coupling(bundle, cfg)
                couplings.append(result.ensemble_coupling_hz)
                cooperativities.append(result.cooperativity)
            except Exception:
                couplings.append(0.0)
                cooperativities.append(0.0)
        elif parameter == "temperature":
            cfg = sample_config.model_copy(deep=True)
            cfg.temperature_k = val
            try:
                result = analyze_spin_coupling(bundle, cfg)
                couplings.append(result.ensemble_coupling_hz)
                cooperativities.append(result.cooperativity)
            except Exception:
                couplings.append(0.0)
                cooperativities.append(0.0)
        elif parameter == "b_field_strength":
            cfg = sample_config.model_copy(deep=True)
            cfg.static_b_field_t = [0.0, 0.0, val]
            try:
                result = analyze_spin_coupling(bundle, cfg)
                couplings.append(result.ensemble_coupling_hz)
                cooperativities.append(result.cooperativity)
            except Exception:
                couplings.append(0.0)
                cooperativities.append(0.0)

    best_idx = int(np.argmax(couplings)) if couplings else 0

    return SpinSweepResult(
        parameter=parameter,
        values=values,
        couplings_hz=couplings,
        cooperativities=cooperativities,
        optimal_value=values[best_idx] if values and best_idx < len(values) else None,
        optimal_coupling_hz=couplings[best_idx] if best_idx < len(couplings) else None,
        optimal_cooperativity=cooperativities[best_idx]
        if best_idx < len(cooperativities)
        else None,
    )
