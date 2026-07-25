"""Guarded leading-order estimates for quantum microwave circuits."""

import math
from dataclasses import dataclass

H = 6.62607015e-34
HBAR = H / (2 * math.pi)
E_CHARGE = 1.602176634e-19
PHI0 = H / (2 * E_CHARGE)


def _positive(value: float, name: str) -> float:
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")
    return value


def josephson_energy(critical_current_a: float) -> float:
    """Return Josephson energy in joules: E_J = I_c Phi_0 / (2 pi)."""
    return _positive(critical_current_a, "critical current") * PHI0 / (2 * math.pi)


@dataclass(frozen=True)
class TransmonEstimate:
    frequency_hz: float
    anharmonicity_hz: float
    approximation: str = "leading-order large-EJ/EC transmon expansion"


def transmon_estimate(ec_hz: float, ej_hz: float) -> TransmonEstimate:
    _positive(ec_hz, "Ec")
    _positive(ej_hz, "Ej")
    if ej_hz / ec_hz < 20:
        raise ValueError("leading-order transmon estimate requires Ej/Ec >= 20")
    return TransmonEstimate(
        frequency_hz=math.sqrt(8 * ec_hz * ej_hz) - ec_hz,
        anharmonicity_hz=-ec_hz,
    )


def transmon_frequency(ec_hz: float, ej_hz: float, n_g: float = 0.0) -> float:
    """Compatibility wrapper; n_g is accepted but not used at leading order."""
    if not math.isfinite(n_g):
        raise ValueError("n_g must be finite")
    return transmon_estimate(ec_hz, ej_hz).frequency_hz


def squid_effective_ej(ej_sum_hz: float, asymmetry: float, phase: float) -> float:
    _positive(ej_sum_hz, "Ej")
    if not 0 <= asymmetry <= 1 or not math.isfinite(phase):
        raise ValueError("SQUID asymmetry must be in [0, 1] and phase must be finite")
    half_phase = phase / 2
    return ej_sum_hz * math.sqrt(
        math.cos(half_phase) ** 2 + asymmetry**2 * math.sin(half_phase) ** 2
    )


def dispersive_shift(coupling_hz: float, detuning_hz: float, anharmonicity_hz: float) -> float:
    """Return transmon dispersive shift; inputs are ordinary frequencies in hertz."""
    if not all(math.isfinite(value) for value in (coupling_hz, detuning_hz, anharmonicity_hz)):
        raise ValueError("dispersive inputs must be finite")
    if coupling_hz < 0:
        raise ValueError("coupling must be non-negative")
    if detuning_hz == 0 or detuning_hz + anharmonicity_hz == 0:
        raise ValueError("dispersive approximation is singular at resonance")
    return coupling_hz**2 * anharmonicity_hz / (detuning_hz * (detuning_hz + anharmonicity_hz))


def tls_q(participation: float, loss_tangent: float) -> float:
    if (
        not all(math.isfinite(value) for value in (participation, loss_tangent))
        or not 0 <= participation <= 1
        or loss_tangent < 0
    ):
        raise ValueError("participation must be in [0, 1] and loss tangent non-negative")
    loss = participation * loss_tangent
    return math.inf if loss == 0 else 1 / loss


def tls_q_total(channels: dict[str, tuple[float, float]]) -> float:
    if any(
        not all(math.isfinite(value) for value in (participation, tangent))
        or not 0 <= participation <= 1
        or tangent < 0
        for participation, tangent in channels.values()
    ):
        raise ValueError("invalid TLS participation or loss tangent")
    inverse_q = sum(participation * tangent for participation, tangent in channels.values())
    return math.inf if inverse_q == 0 else 1 / inverse_q


def cooperativity(g_hz: float, kappa_hz: float, gamma_hz: float) -> float:
    _positive(kappa_hz, "kappa")
    _positive(gamma_hz, "gamma")
    if g_hz < 0 or not math.isfinite(g_hz):
        raise ValueError("coupling must be finite and non-negative")
    return 4 * g_hz**2 / (kappa_hz * gamma_hz)
