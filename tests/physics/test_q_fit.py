"""Scientific regression tests for complex resonator fitting."""

import numpy as np

from qresaudit.analysis.fitting import fit_resonator, notch_model


def test_complex_notch_fit_recovers_known_parameters_below_five_percent() -> None:
    rng = np.random.default_rng(20260725)
    f0 = 6.513e9
    q_loaded = 8_500.0
    q_coupling = 12_000.0
    frequency = np.linspace(f0 - 8e6, f0 + 8e6, 2_001)
    exact = notch_model(
        frequency,
        f0,
        q_loaded,
        q_coupling,
        delay=0.035,
        bg_real=0.01,
        bg_imag=-0.006,
    )
    noise = rng.normal(0.0, 2e-4, exact.size) + 1j * rng.normal(0.0, 2e-4, exact.size)

    result = fit_resonator(
        frequency,
        exact + noise,
        ql_guess=7_000.0,
        qc_guess=15_000.0,
        use_bootstrap=False,
    )

    assert result.optimizer_converged
    assert abs(result.f0_hz / f0 - 1.0) < 0.05
    assert abs(result.q_loaded / q_loaded - 1.0) < 0.05
    assert abs(result.q_coupling_absolute / q_coupling - 1.0) < 0.05


def test_fit_rejects_non_monotonic_frequency_axis() -> None:
    frequency = np.linspace(5.9e9, 6.1e9, 20)
    frequency[10] = frequency[9]
    with np.testing.assert_raises_regex(ValueError, "strictly increasing"):
        fit_resonator(frequency, np.ones(20, dtype=complex), use_bootstrap=False)
