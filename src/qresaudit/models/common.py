from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SolutionKind(StrEnum):
    DRIVEN_MODAL = "driven_modal"
    DRIVEN_TERMINAL = "driven_terminal"
    EIGENMODE = "eigenmode"


class EvidenceProfile(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    STRICT = "strict"


class FieldRepresentation(StrEnum):
    REAL_GAUGE = "real_gauge"
    COMPLEX_PHASOR = "complex_phasor"
    PHASE_EVALUATED_REAL = "phase_evaluated_real"
    QUADRATURE_RECONSTRUCTED = "quadrature_reconstructed"
    MAGNITUDE_ONLY = "magnitude_only"


class PhasorConvention(StrEnum):
    EXP_POSITIVE_IWT_PEAK = "exp_positive_iwt_peak"
    EXP_NEGATIVE_IWT_PEAK = "exp_negative_iwt_peak"
    EXP_POSITIVE_IWT_RMS = "exp_positive_iwt_rms"
    EXP_NEGATIVE_IWT_RMS = "exp_negative_iwt_rms"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NormalizationKind(StrEnum):
    DRIVEN_EXCITATION_DEPENDENT = "driven_excitation_dependent"
    HFSS_EIGENMODE_PEAK_1 = "hfss_eigenmode_peak_1"
    USER_SCALED = "user_scaled"
    UNKNOWN = "unknown"


class ExportStatus(StrEnum):
    BUILDING = "building"
    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    FAILED = "failed"


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    severity: Severity
    message: str
    path: str | None = None
    context: dict[str, str | int | float | bool] = Field(default_factory=dict)


def diagnostic(
    code: str,
    severity: Severity,
    message: str,
    path: str | None = None,
    **context: Any,
) -> Diagnostic:
    safe = {
        key: value for key, value in context.items() if isinstance(value, str | int | float | bool)
    }
    return Diagnostic(code=code, severity=severity, message=message, path=path, context=safe)


def error(code: str, message: str, path: str | None = None, **context: Any) -> Diagnostic:
    return diagnostic(code, Severity.ERROR, message, path, **context)


def warning(code: str, message: str, path: str | None = None, **context: Any) -> Diagnostic:
    return diagnostic(code, Severity.WARNING, message, path, **context)


def info(code: str, message: str, path: str | None = None, **context: Any) -> Diagnostic:
    return diagnostic(code, Severity.INFO, message, path, **context)
