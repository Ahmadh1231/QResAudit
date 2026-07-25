"""Participation and loss estimation — compute volume participation ratios and loss budgets.

p_k = U_k / U_total          (volume participation ratio)
1/Q_loss = Σ p_k · tan(δ_k)  (loss estimate)

Surface participation is deferred until interface/layer-thickness contracts exist.

Commands:
    qresaudit participation BUNDLE --regions regions.yaml
    qresaudit loss-estimate BUNDLE --materials materials.yaml
"""

from pathlib import Path

import numpy as np
import yaml

from qresaudit.analysis.field_integration import (
    compute_energy,
)
from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.models.v0_2 import (
    LossEstimate,
    MaterialRecord,
    ParticipationResult,
)


def normalized_participation(energies: dict[str, float]) -> dict[str, float]:
    """Normalize non-negative regional energies into participation ratios."""
    if not energies:
        raise ValueError("at least one regional energy is required")
    values = np.asarray(list(energies.values()), dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("regional energies must be finite and non-negative")
    total = float(np.sum(values))
    if total <= 0:
        raise ValueError("total regional energy must be positive")
    return {name: float(energy / total) for name, energy in energies.items()}


def tls_quality_factor(
    participation: dict[str, float],
    loss_tangents: dict[str, float],
) -> float:
    """Return the TLS-limited Q from ``1/Q = sum(p_i * tan_delta_i)``."""
    if set(participation) - set(loss_tangents):
        missing = sorted(set(participation) - set(loss_tangents))
        raise ValueError(f"missing loss tangents for regions: {', '.join(missing)}")
    p_values = np.asarray(list(participation.values()), dtype=float)
    tan_values = np.asarray([loss_tangents[name] for name in participation], dtype=float)
    if np.any(~np.isfinite(p_values)) or np.any(p_values < 0):
        raise ValueError("participation ratios must be finite and non-negative")
    if np.any(~np.isfinite(tan_values)) or np.any(tan_values < 0):
        raise ValueError("loss tangents must be finite and non-negative")
    inverse_q = float(np.dot(p_values, tan_values))
    return float("inf") if inverse_q == 0 else 1.0 / inverse_q


def compute_participation(
    bundle: Path,
    regions: dict[str, MaterialRecord],
    mode: int | None = None,
    epsilon_r_global: float = 1.0,
    mu_r_global: float = 1.0,
) -> tuple[list[ParticipationResult], LossEstimate]:
    """Compute volume participation ratios and loss estimates.

    Parameters
    ----------
    bundle : Path
        Validated bundle directory.
    regions : dict[str, MaterialRecord]
        Mapping of material/region names to properties.
    mode : int | None
        Filter to a specific eigenmode.
    epsilon_r_global, mu_r_global : float
        Default material properties for regions not in the dictionary.

    Returns
    -------
    (participation_results, loss_estimate)
    """
    manifest = load_manifest(bundle / "manifest.json")

    e_records = [f for f in manifest.fields if f.quantity == "E"]
    h_records = [f for f in manifest.fields if f.quantity == "H"]
    if mode is not None:
        e_records = [f for f in e_records if f.mode == mode]
        h_records = [f for f in h_records if f.mode == mode]

    participation_results: list[ParticipationResult] = []
    total_e_energy = 0.0
    total_m_energy = 0.0
    total_volume = 0.0

    for e_rec, h_rec in zip(e_records, h_records, strict=False):
        e_coords, e_vals, _, _e_meta = read_field_hdf5(safe_bundle_path(bundle, e_rec.path))
        _h_coords, h_vals, _, _h_meta = read_field_hdf5(safe_bundle_path(bundle, h_rec.path))

        region = e_rec.region_name
        material = regions.get(region)

        # Default volume element
        dV = np.ones(e_coords.shape[0])

        eps_r = material.relative_permittivity if material else epsilon_r_global
        mu_r = material.relative_permeability if material else mu_r_global
        tan_delta_e = material.dielectric_loss_tangent if material else 0.0
        tan_delta_m = material.magnetic_loss_tangent if material else 0.0

        energy = compute_energy(e_coords, e_vals, h_vals, dV, eps_r, mu_r)
        u_e = energy["electric_energy_j"]
        u_m = energy["magnetic_energy_j"]

        total_e_energy += u_e
        total_m_energy += u_m
        region_volume = float(np.sum(dV))
        total_volume += region_volume

        participation_results.append(
            ParticipationResult(
                region=region,
                material=material.name if material else "unknown",
                electric_energy_j=u_e,
                electric_participation=0.0,  # filled after total known
                magnetic_energy_j=u_m,
                magnetic_participation=0.0,
                loss_tangent_dielectric=tan_delta_e,
                loss_tangent_magnetic=tan_delta_m,
                volume_m3=region_volume,
                point_count=e_coords.shape[0],
                coverage_fraction=1.0,
            )
        )

    total_energy = total_e_energy + total_m_energy

    # Compute participation ratios
    for result in participation_results:
        result.electric_participation = (
            result.electric_energy_j / total_energy if total_energy > 0 else 0.0
        )
        result.magnetic_participation = (
            result.magnetic_energy_j / total_energy if total_energy > 0 else 0.0
        )

        # Estimated Q contribution from this region's dielectric loss
        if result.loss_tangent_dielectric > 0:
            result.estimated_q_contribution = 1.0 / (
                result.electric_participation * result.loss_tangent_dielectric
            )

    # Build loss estimate
    dielectric_q_inv = sum(
        p.electric_participation * p.loss_tangent_dielectric for p in participation_results
    )
    magnetic_q_inv = sum(
        p.magnetic_participation * p.loss_tangent_magnetic for p in participation_results
    )

    dielectric_q = 1.0 / dielectric_q_inv if dielectric_q_inv > 0 else float("inf")
    magnetic_q = 1.0 / magnetic_q_inv if magnetic_q_inv > 0 else float("inf")
    total_q = (
        1.0 / (dielectric_q_inv + magnetic_q_inv)
        if (dielectric_q_inv + magnetic_q_inv) > 0
        else float("inf")
    )

    sum_check = sum(p.electric_participation for p in participation_results)

    loss = LossEstimate(
        total_q_loss=float(total_q) if total_q != float("inf") else None,
        dielectric_q=float(dielectric_q) if dielectric_q != float("inf") else None,
        magnetic_q=float(magnetic_q) if magnetic_q != float("inf") else None,
        conductor_q=None,  # surface participation deferred
        total_tan_delta=float(dielectric_q_inv),
        per_region=participation_results,
        converged=True,
        resolution_sensitivity=None,
        missing_regions=[],
        sum_check=float(sum_check),
    )

    return participation_results, loss


def load_regions_config(path: Path) -> dict[str, MaterialRecord]:
    """Load a regions/materials YAML configuration file.

    Expected format:
    ```yaml
    regions:
      Substrate:
        relative_permittivity: 11.7
        dielectric_loss_tangent: 1e-4
        relative_permeability: 1.0
      Vacuum:
        relative_permittivity: 1.0
        dielectric_loss_tangent: 0.0
    ```
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("regions config must be a YAML mapping")

    regions_data = raw.get("regions", raw)
    result: dict[str, MaterialRecord] = {}
    for name, props in regions_data.items():
        if isinstance(props, dict):
            result[str(name)] = MaterialRecord(
                name=str(name),
                relative_permittivity=float(props.get("relative_permittivity", 1.0)),
                relative_permeability=float(props.get("relative_permeability", 1.0)),
                dielectric_loss_tangent=float(props.get("dielectric_loss_tangent", 0.0)),
                magnetic_loss_tangent=float(props.get("magnetic_loss_tangent", 0.0)),
                bulk_conductivity_s_per_m=float(props.get("bulk_conductivity", 0.0)),
                is_pec=bool(props.get("is_pec", False)),
                is_lossy=float(props.get("dielectric_loss_tangent", 0.0)) > 0
                or float(props.get("magnetic_loss_tangent", 0.0)) > 0,
            )
    return result


def compute_participation_bundle(
    bundle: Path,
    regions_path: Path | None = None,
    mode: int | None = None,
) -> tuple[list[ParticipationResult], LossEstimate]:
    """Convenience wrapper: load regions from file and compute participation."""
    regions = load_regions_config(regions_path) if regions_path is not None else {}
    return compute_participation(bundle, regions, mode=mode)
