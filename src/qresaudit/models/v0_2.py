"""Schema 0.2 records — enrich bundle evidence into structured, queryable records.

These records are NOT part of the bundle manifest; they are derived
during audit/analysis and live in the analysis output directory.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qresaudit.models.common import (
    FieldRepresentation,
    PhasorConvention,
    Severity,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── grid & coordinate records ──────────────────────────────────────────


class GridRecord(StrictModel):
    topology: str = "unstructured"
    coordinate_type: str = "Cartesian"
    coordinate_system: str = "Global"
    shape: list[int] = Field(default_factory=list)
    axis_order: list[str] = Field(default_factory=lambda: ["x", "y", "z"])
    flattening_order: str = "C"
    point_count: int = Field(ge=0)
    region_name: str = ""
    coordinate_units: str = "m"


class FieldRepresentationRecord(StrictModel):
    representation: FieldRepresentation = FieldRepresentation.COMPLEX_PHASOR
    phasor_convention: PhasorConvention = PhasorConvention.UNKNOWN
    is_complex: bool = True
    is_vector: bool = True
    component_count: int = Field(ge=0)


# ── excitation & port records ──────────────────────────────────────────


class ExcitationRecord(StrictModel):
    name: str
    amplitude: float = 1.0
    phase_deg: float = 0.0
    frequency_hz: float = Field(gt=0)
    solved_impedance_ohm: float | None = None
    terminal_type: str | None = None  # e.g. "wave_port", "lumped_port"


class PortRecord(StrictModel):
    name: str
    number: int = Field(ge=1)
    excitation_name: str
    terminal_names: list[str] = Field(default_factory=list)
    deembed_distance_mm: float | None = None
    calibration_type: str | None = None


class ReferenceImpedanceRecord(StrictModel):
    source_impedance_real_ohm: list[list[float]] = Field(default_factory=list)
    source_impedance_imag_ohm: list[list[float]] = Field(default_factory=list)
    renormalized_impedance_real_ohm: list[list[float]] = Field(default_factory=list)
    renormalized_impedance_imag_ohm: list[list[float]] = Field(default_factory=list)
    wave_definition: str = "power"
    is_renormalized: bool = False


# ── convergence & mesh records ─────────────────────────────────────────


class AdaptivePassRecord(StrictModel):
    pass_number: int = Field(ge=1)
    tetrahedra: int = Field(ge=0)
    frequency_hz: float | None = None
    frequency_change_fraction: float | None = None
    maximum_delta_s: float | None = None
    converged: bool = False
    elapsed_time_s: float | None = None
    peak_memory_bytes: int | None = None
    solver_message: str | None = None
    raw_evidence_path: str | None = None


class MeshStatisticsRecord(StrictModel):
    pass_number: int = Field(ge=1)
    tetrahedra: int = Field(ge=0)
    triangles: int = Field(ge=0)
    vertices: int = Field(ge=0)
    element_quality_min: float | None = None
    element_quality_mean: float | None = None
    skewness_max: float | None = None
    raw_evidence_path: str | None = None


# ── material & boundary records ────────────────────────────────────────


class MaterialRecord(StrictModel):
    name: str
    relative_permittivity: float = 1.0
    relative_permeability: float = 1.0
    dielectric_loss_tangent: float = 0.0
    magnetic_loss_tangent: float = 0.0
    bulk_conductivity_s_per_m: float = 0.0
    is_pec: bool = False
    is_lossy: bool = False
    temperature_k: float | None = None


class BoundaryRecord(StrictModel):
    name: str
    kind: str  # e.g. "radiation", "pec", "pml", "symmetry_h", "lumped_rlc"
    faces: list[str] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)


# ── analysis & diagnostic records ──────────────────────────────────────


class AnalysisRecord(StrictModel):
    """Structured container for any quantitative analysis result."""
    kind: str
    name: str
    value: float | list[float] | None = None
    unit: str | None = None
    uncertainty: float | None = None
    confidence_interval_95: tuple[float, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class DiagnosticRecord(StrictModel):
    """Serialisable form of a Diagnostic for audit report inclusion."""
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    severity: Severity
    message: str
    path: str | None = None
    context: dict[str, str | int | float | bool] = Field(default_factory=dict)


# ── convergence diagnostics ────────────────────────────────────────────


class ConvergenceDiagnostic(StrictModel):
    """Complete convergence audit for a single adaptive solution."""
    passes: list[AdaptivePassRecord] = Field(default_factory=list)
    total_passes: int = 0
    final_frequency_hz: float | None = None
    final_frequency_change_fraction: float | None = None
    final_max_delta_s: float | None = None
    is_converged: bool = False
    mesh_growth_ratio: float | None = None
    is_monotonic_frequency: bool = False
    is_monotonic_delta_s: bool = False
    oscillation_detected: bool = False
    stagnation_detected: bool = False
    insufficient_passes: bool = True
    requested_max_delta_s: float | None = None
    achieved_max_delta_s: float | None = None
    false_convergence_risk: str = "not_evaluated"  # low / medium / high / not_evaluated
    limiting_value_extrapolation_hz: float | None = None
    limiting_value_uncertainty_hz: float | None = None
    solver_messages: list[str] = Field(default_factory=list)


# ── resonator fit result ───────────────────────────────────────────────


class ResonatorFitResult(StrictModel):
    """Result of fitting a resonator model to S-parameter data."""
    model: str  # "notch", "peak", "reflection"
    f0_hz: float
    f0_uncertainty_hz: float = 0.0
    q_loaded: float
    q_loaded_uncertainty: float = 0.0
    q_coupling_absolute: float | None = None
    q_coupling_uncertainty: float | None = None
    q_internal: float | None = None
    q_internal_uncertainty: float | None = None
    coupling_coefficient: float | None = None
    cable_delay_ns: float = 0.0
    cable_delay_uncertainty_ns: float = 0.0
    background_slope_real: float = 0.0
    background_slope_imag: float = 0.0
    background_intercept_real: float = 0.0
    background_intercept_imag: float = 0.0
    residual_rms: float = 0.0
    residual_max: float = 0.0
    condition_number: float | None = None
    optimizer_converged: bool = False
    optimizer_message: str = ""
    chi_squared: float | None = None
    degrees_of_freedom: int = 0
    reduced_chi_squared: float | None = None
    aic: float | None = None
    bic: float | None = None
    bootstrap_samples: int = 0
    bootstrap_confidence_95: dict[str, tuple[float, float]] = Field(default_factory=dict)
    parameter_correlation: dict[str, dict[str, float]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fit_timestamp_utc: datetime | None = None


# ── mode tracking ──────────────────────────────────────────────────────


class ModeOverlapResult(StrictModel):
    mode_a: int
    mode_b: int
    electric_overlap: float = 0.0
    magnetic_overlap: float = 0.0
    total_overlap: float = 0.0
    frequency_a_hz: float = 0.0
    frequency_b_hz: float = 0.0
    frequency_difference_hz: float = 0.0


class ModeBranch(StrictModel):
    branch_id: int
    modes: list[int] = Field(default_factory=list)
    frequencies_hz: list[float] = Field(default_factory=list)
    is_continuous: bool = True
    has_crossing: bool = False
    has_avoided_crossing: bool = False
    hybridization_region: bool = False
    confidence: float = 1.0


class AvoidedCrossing(StrictModel):
    parameter_name: str
    parameter_value: float
    mode_a: int
    mode_b: int
    minimum_separation_hz: float
    coupling_strength_hz: float | None = None


# ── field integration ──────────────────────────────────────────────────


class FieldIntegrationResult(StrictModel):
    region: str
    electric_energy_j: float = 0.0
    magnetic_energy_j: float = 0.0
    total_energy_j: float = 0.0
    energy_imbalance: float = 0.0  # |U_e - U_m| / U_total, should vanish at resonance
    peak_e_field_v_per_m: float = 0.0
    peak_h_field_a_per_m: float = 0.0
    rms_e_field_v_per_m: float = 0.0
    rms_h_field_a_per_m: float = 0.0
    effective_mode_volume_m3: float | None = None
    filling_factor: float = 0.0
    normalization_factor: float = 1.0
    target_energy_j: float = 0.0
    grid_resolution_m: list[float] = Field(default_factory=list)
    integration_method: str = ""
    jacobian_used: bool = False


# ── participation ──────────────────────────────────────────────────────


class ParticipationResult(StrictModel):
    region: str
    material: str
    electric_energy_j: float = 0.0
    electric_participation: float = 0.0
    magnetic_energy_j: float = 0.0
    magnetic_participation: float = 0.0
    loss_tangent_dielectric: float = 0.0
    loss_tangent_magnetic: float = 0.0
    estimated_q_contribution: float | None = None
    volume_m3: float = 0.0
    point_count: int = 0
    coverage_fraction: float = 1.0
    participation_uncertainty: float | None = None


class LossEstimate(StrictModel):
    total_q_loss: float | None = None
    dielectric_q: float | None = None
    magnetic_q: float | None = None
    conductor_q: float | None = None
    total_tan_delta: float | None = None
    per_region: list[ParticipationResult] = Field(default_factory=list)
    converged: bool = False
    resolution_sensitivity: float | None = None
    missing_regions: list[str] = Field(default_factory=list)
    sum_check: float = 0.0  # sum of participation ratios, should be ~1.0


# ── bundle comparison ──────────────────────────────────────────────────


class ComparisonResult(StrictModel):
    bundle_a: str
    bundle_b: str
    schema_versions_match: bool = True
    solution_kinds_match: bool = True
    provenance_differences: list[str] = Field(default_factory=list)
    variable_differences: list[str] = Field(default_factory=list)
    mesh_differences: list[str] = Field(default_factory=list)
    convergence_differences: list[str] = Field(default_factory=list)
    resonant_frequency_difference_hz: float | None = None
    resonant_frequency_relative: float | None = None
    q_differences: dict[str, float] = Field(default_factory=dict)
    s_parameter_rms_difference: float | None = None
    s_parameter_max_difference: float | None = None
    mode_overlap: list[ModeOverlapResult] = Field(default_factory=list)
    field_overlap_matrix: list[list[float]] = Field(default_factory=list)
    integrated_quantity_differences: dict[str, float] = Field(default_factory=dict)
    participation_differences: dict[str, float] = Field(default_factory=dict)
    diagnostic_differences: list[str] = Field(default_factory=list)
    classification: str = "NUMERICAL_DIFFERENCE"


# ── audit report ───────────────────────────────────────────────────────


class AuditVerdict(StrictModel):
    section: str
    check: str
    result: str = "NOT_EVALUATED"  # PASS / WARNING / FAIL / NOT_EVALUATED
    detail: str = ""
    diagnostics: list[str] = Field(default_factory=list)


class AuditReport(StrictModel):
    bundle_path: str
    audit_timestamp_utc: datetime
    schema_version: str = "0.2.0"
    auditor_version: str = "0.2.0"
    verdicts: list[AuditVerdict] = Field(default_factory=list)
    convergence: ConvergenceDiagnostic | None = None
    fit_results: dict[str, ResonatorFitResult] = Field(default_factory=dict)
    mode_branches: list[ModeBranch] = Field(default_factory=list)
    avoided_crossings: list[AvoidedCrossing] = Field(default_factory=list)
    field_integration: list[FieldIntegrationResult] = Field(default_factory=list)
    participation: LossEstimate | None = None
    diagnostics_raw: list[DiagnosticRecord] = Field(default_factory=list)


# ── spin resonator ─────────────────────────────────────────────────────


class SpinSampleConfig(StrictModel):
    name: str = "sample"
    spin_density_per_m3: float = 0.0
    spin_species: str = "Er3+"
    g_tensor_principal: list[float] = Field(default_factory=lambda: [15.0, 15.0, 15.0])
    g_tensor_orientation_euler_deg: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    crystal_class: str = ""
    inhomogeneous_linewidth_hz: float = 0.0
    homogeneous_linewidth_hz: float = 0.0
    spin_number: float = 0.5
    temperature_k: float = 0.01
    static_b_field_t: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    static_b_field_orientation_euler_deg: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])


class SpinCouplingResult(StrictModel):
    sample_name: str
    frequency_hz: float
    g_effective: float
    zero_point_b_field_rms_t: float = 0.0
    zero_point_b_field_peak_t: float = 0.0
    magnetic_filling_factor: float = 0.0
    single_spin_coupling_hz: float = 0.0
    ensemble_coupling_hz: float = 0.0
    thermal_polarization: float = 0.0
    cooperativity: float = 0.0
    strong_coupling: bool = False
    cavity_decay_rate_hz: float = 0.0
    spin_decay_rate_hz: float = 0.0
    collective_coupling_hz: float | None = None
    effective_spin_number: float = 0.0


class SpinSweepResult(StrictModel):
    parameter: str
    values: list[float] = Field(default_factory=list)
    couplings_hz: list[float] = Field(default_factory=list)
    cooperativities: list[float] = Field(default_factory=list)
    optimal_value: float | None = None
    optimal_coupling_hz: float | None = None
    optimal_cooperativity: float | None = None


# ── optimization ───────────────────────────────────────────────────────


class OptimizationObjective(StrictModel):
    name: str
    expression: str
    target: float | None = None
    weight: float = 1.0
    minimize: bool = True
    tolerance: float | None = None


class OptimizationConstraint(StrictModel):
    name: str
    expression: str
    kind: str = "inequality"  # inequality / equality
    bound: float = 0.0
    tolerance: float = 1e-6


class OptimizationCandidate(StrictModel):
    id: str
    variables: dict[str, float]
    objectives: dict[str, float]
    constraints: dict[str, float]
    is_feasible: bool = True
    dominated: bool = False
    rank: int = 0


class OptimizationResult(StrictModel):
    method: str
    candidates: list[OptimizationCandidate] = Field(default_factory=list)
    pareto_front: list[OptimizationCandidate] = Field(default_factory=list)
    best_candidate: OptimizationCandidate | None = None
    iterations: int = 0
    evaluations: int = 0
    converged: bool = False
    elapsed_time_s: float = 0.0
    surrogate_model_r2: float | None = None
    surrogate_model_name: str | None = None
    acquisition_function: str | None = None
    fabrication_tolerance_results: dict[str, dict[str, float]] = Field(default_factory=dict)
