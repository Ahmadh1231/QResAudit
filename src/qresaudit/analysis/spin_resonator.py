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
    pair_electric_magnetic_records,
    structured_volume_weights,
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
    dV = np.asarray(dV, dtype=float).ravel()
    if len(dV) != coords.shape[0] or np.any(~np.isfinite(dV)) or np.any(dV < 0):
        raise ValueError("volume weights must be finite, non-negative, and match coordinates")

    b_squared = (
        np.sum(np.abs(b_field_t) ** 2, axis=-1) if b_field_t.ndim == 2 else np.abs(b_field_t) ** 2
    )
    volume = float(np.sum(dV))
    if volume <= 0:
        raise ValueError("sample volume must be positive")
    b_rms = float(np.sqrt(np.sum(b_squared * dV) / volume))

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
    if n_spins < 0 or not np.isfinite(n_spins):
        raise ValueError("spin count must be finite and non-negative")
    if not 0 <= thermal_polarization <= 1 or not np.isfinite(thermal_polarization):
        raise ValueError("thermal polarization must be finite and between zero and one")
    return float(g_single_hz * np.sqrt(n_spins) * np.sqrt(thermal_polarization))


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
    if spin_number != 0.5:
        raise ValueError("the tanh polarization model is valid only for spin-1/2")
    if frequency_hz < 0:
        raise ValueError("frequency must be non-negative")
    if temperature_k <= 0:
        return 1.0
    # Zeeman energy splitting
    delta_e = g_eff * MU_B * np.linalg.norm(b_static_t)
    thermal = K_B * temperature_k
    if thermal <= 0:
        return 1.0
    return float(np.tanh(abs(delta_e) / (2.0 * thermal)))


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
    dV = np.asarray(dV, dtype=float).ravel()
    if len(dV) != coords.shape[0] or np.any(~np.isfinite(dV)) or np.any(dV < 0):
        raise ValueError("volume weights must be finite, non-negative, and match coordinates")
    if region_mask is not None:
        region_mask = np.asarray(region_mask, dtype=bool).ravel()
        if len(region_mask) != coords.shape[0]:
            raise ValueError("region mask must match coordinates")

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
    if sample_config.sample_region_name is None:
        raise ValueError("sample_region_name is required for spin coupling analysis")
    if sample_config.total_field_region_name is None:
        raise ValueError("total_field_region_name is required for spin coupling analysis")
    if sample_config.cavity_q_loaded is None:
        raise ValueError("cavity_q_loaded is required for spin coupling analysis")

    total_e_records = [
        field
        for field in manifest.fields
        if field.quantity == "E"
        and field.mode == mode
        and field.region_name == sample_config.total_field_region_name
    ]
    total_h_records = [
        field
        for field in manifest.fields
        if field.quantity == "H"
        and field.mode == mode
        and field.region_name == sample_config.total_field_region_name
    ]
    pairs = pair_electric_magnetic_records(total_e_records, total_h_records)
    if len(pairs) != 1:
        raise ValueError("spin analysis requires exactly one total-field E/H pair")
    total_e_record, total_h_record = pairs[0]
    total_coords, e_raw, _, total_e_meta = read_field_hdf5(
        safe_bundle_path(bundle, total_e_record.path)
    )
    total_h_coords, h_total_raw, _, total_h_meta = read_field_hdf5(
        safe_bundle_path(bundle, total_h_record.path)
    )
    if not np.array_equal(total_coords, total_h_coords):
        raise ValueError("total electric and magnetic fields use different coordinates")
    grid_keys = ("topology", "shape", "axis_order", "flattening_order")
    if {key: total_e_meta.get(key) for key in grid_keys} != {
        key: total_h_meta.get(key) for key in grid_keys
    }:
        raise ValueError("total electric and magnetic fields use different grids")
    if total_e_record.phasor_convention != total_h_record.phasor_convention:
        raise ValueError("total electric and magnetic fields use different phasor conventions")
    total_d_v = structured_volume_weights(total_coords, total_e_meta)

    sample_h_records = [
        field
        for field in manifest.fields
        if field.quantity == "H"
        and field.mode == mode
        and field.region_name == sample_config.sample_region_name
    ]
    if len(sample_h_records) != 1:
        raise ValueError("spin analysis requires exactly one sample-region H field")
    sample_h_record = sample_h_records[0]
    sample_coords, h_sample_raw, _, sample_meta = read_field_hdf5(
        safe_bundle_path(bundle, sample_h_record.path)
    )
    sample_d_v = structured_volume_weights(sample_coords, sample_meta)
    if (
        sample_h_record.solution != total_h_record.solution
        or sample_h_record.variation != total_h_record.variation
        or sample_h_record.normalization != total_h_record.normalization
        or sample_h_record.phasor_convention != total_h_record.phasor_convention
    ):
        raise ValueError("sample and total fields do not share a normalization context")
    frequency = float(total_e_meta.get("frequency_hz", total_e_record.frequency_hz or 0))
    if frequency <= 0:
        raise ValueError("a positive field frequency is required")
    convention_value = total_e_record.phasor_convention.value
    if convention_value.endswith("_peak"):
        phasor_convention = "peak"
    elif convention_value.endswith("_rms"):
        phasor_convention = "rms"
    else:
        raise ValueError("field phasor convention is unknown or not applicable")

    # Normalize to zero-point energy
    target_energy = ZERO_POINT_ENERGY(2.0 * np.pi * frequency)
    _e_norm, _h_total_norm, alpha = normalize_field(
        e_raw,
        h_total_raw,
        total_coords,
        target_energy,
        total_d_v,
        phasor_convention=phasor_convention,
    )
    h_norm = h_sample_raw * alpha

    # Convert H (A/m) to B (T): B = μ₀·H
    b_field = h_norm * MU_0

    b_static = rotation_matrix_euler(
        *np.radians(sample_config.static_b_field_orientation_euler_deg)
    ) @ np.array(sample_config.static_b_field_t)

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

    b_rms, b_peak = zero_point_magnetic_field(b_field, sample_coords, sample_d_v)
    sample_magnetic = float(np.sum(np.sum(np.abs(h_sample_raw) ** 2, axis=-1) * sample_d_v))
    total_magnetic = float(np.sum(np.sum(np.abs(h_total_raw) ** 2, axis=-1) * total_d_v))
    filling = sample_magnetic / total_magnetic if total_magnetic > 0 else 0.0
    if not 0 <= filling <= 1.0 + 1e-9:
        raise ValueError("sample magnetic energy exceeds total magnetic energy")
    filling = min(filling, 1.0)

    g_single = single_spin_coupling(g_eff, b_rms, b_static)
    polarization = thermal_polarization(
        sample_config.spin_number,
        sample_config.temperature_k,
        frequency,
        b_static,
        g_eff,
    )
    sample_volume = float(np.sum(sample_d_v))
    n_effective = sample_config.spin_density_per_m3 * sample_volume

    g_ens = ensemble_coupling(g_single, n_effective, polarization)

    # Cavity decay rate
    kappa = float(frequency / sample_config.cavity_q_loaded)

    # Spin decay rate from linewidths
    gamma_spin = max(
        sample_config.inhomogeneous_linewidth_hz,
        sample_config.homogeneous_linewidth_hz,
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
    if parameter not in {"orientation", "temperature", "b_field_strength"}:
        raise ValueError("unsupported spin sweep parameter")
    if not values:
        raise ValueError("spin sweep requires at least one value")

    for val in values:
        if parameter == "orientation":
            # Sweep B-field orientation about z-axis
            cfg = sample_config.model_copy(deep=True)
            cfg.static_b_field_orientation_euler_deg = [0.0, 0.0, val]
            result = analyze_spin_coupling(bundle, cfg)
            couplings.append(result.ensemble_coupling_hz)
            cooperativities.append(result.cooperativity)
        elif parameter == "temperature":
            cfg = sample_config.model_copy(deep=True)
            cfg.temperature_k = val
            result = analyze_spin_coupling(bundle, cfg)
            couplings.append(result.ensemble_coupling_hz)
            cooperativities.append(result.cooperativity)
        elif parameter == "b_field_strength":
            cfg = sample_config.model_copy(deep=True)
            cfg.static_b_field_t = [0.0, 0.0, val]
            result = analyze_spin_coupling(bundle, cfg)
            couplings.append(result.ensemble_coupling_hz)
            cooperativities.append(result.cooperativity)

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
