"""Phase 2 analysis and audit modules — portable scientific analysis of HFSS evidence.

All modules work offline without AEDT or PyAEDT.
"""

from qresaudit.analysis.audit import (
    AuditReport,
    AuditVerdict,
    audit_bundle,
    render_audit_html,
    render_audit_markdown,
    write_audit_output,
)
from qresaudit.analysis.compare import ComparisonResult, compare_bundles
from qresaudit.analysis.convergence import (
    ConvergenceDiagnostic,
    audit_convergence,
    convergence_summary_json,
    convergence_to_dataframe,
)
from qresaudit.analysis.field_integration import (
    FieldIntegrationResult,
    compute_energy,
    effective_mode_volume,
    integrate_bundle_fields,
    normalize_field,
)
from qresaudit.analysis.fitting import (
    ResonatorFitResult,
    detect_resonances,
    fit_bundle_resonator,
    fit_resonator,
    notch_model,
    peak_model,
    reflection_model,
)
from qresaudit.analysis.mode_tracking import (
    AvoidedCrossing,
    ModeBranch,
    assign_modes,
    compute_overlap_matrix,
    detect_crossings,
    field_overlap,
    track_modes,
)
from qresaudit.analysis.optimization import (
    OptimizationCandidate,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationResult,
    bayesian_optimization,
    compute_pareto_front,
    fabrication_tolerance_analysis,
    is_dominated,
    random_latin_hypercube,
)
from qresaudit.analysis.participation import (
    LossEstimate,
    ParticipationResult,
    compute_participation,
    compute_participation_bundle,
    load_regions_config,
)
from qresaudit.analysis.spin_resonator import (
    SpinCouplingResult,
    SpinSampleConfig,
    SpinSweepResult,
    analyze_spin_coupling,
    effective_g_tensor,
    ensemble_coupling,
    magnetic_filling_factor,
    single_spin_coupling,
    sweep_parameter,
    thermal_polarization,
    zero_point_magnetic_field,
)
from qresaudit.models.v0_2 import ModeOverlapResult  # defined in models, re-used across modules

__all__ = [
    # audit
    "AuditReport",
    "AuditVerdict",
    # mode tracking
    "AvoidedCrossing",
    # compare
    "ComparisonResult",
    # convergence
    "ConvergenceDiagnostic",
    # field integration
    "FieldIntegrationResult",
    # participation
    "LossEstimate",
    "ModeBranch",
    "ModeOverlapResult",
    # optimization
    "OptimizationCandidate",
    "OptimizationConstraint",
    "OptimizationObjective",
    "OptimizationResult",
    "ParticipationResult",
    # fitting
    "ResonatorFitResult",
    # spin resonator
    "SpinCouplingResult",
    "SpinSampleConfig",
    "SpinSweepResult",
    "analyze_spin_coupling",
    "assign_modes",
    "audit_bundle",
    "audit_convergence",
    "bayesian_optimization",
    "compare_bundles",
    "compute_energy",
    "compute_overlap_matrix",
    "compute_pareto_front",
    "compute_participation",
    "compute_participation_bundle",
    "convergence_summary_json",
    "convergence_to_dataframe",
    "detect_crossings",
    "detect_resonances",
    "effective_g_tensor",
    "effective_mode_volume",
    "ensemble_coupling",
    "fabrication_tolerance_analysis",
    "field_overlap",
    "fit_bundle_resonator",
    "fit_resonator",
    "integrate_bundle_fields",
    "is_dominated",
    "load_regions_config",
    "magnetic_filling_factor",
    "normalize_field",
    "notch_model",
    "peak_model",
    "random_latin_hypercube",
    "reflection_model",
    "render_audit_html",
    "render_audit_markdown",
    "single_spin_coupling",
    "sweep_parameter",
    "thermal_polarization",
    "track_modes",
    "write_audit_output",
    "zero_point_magnetic_field",
]
