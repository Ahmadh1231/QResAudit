"""Resonator fitting — extract Q factors and resonance parameters from S-parameter data.

Supports notch, peak, and reflection resonator models with cable delay removal,
complex background correction, uncertainty estimation via covariance and bootstrap,
model comparison (AIC/BIC), and synthetic validation fixtures.

Command:
    qresaudit fit BUNDLE --response S21 --model notch
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares, minimize

from qresaudit.io.bundle import load_manifest, safe_bundle_path
from qresaudit.io.touchstone import load_network
from qresaudit.models.v0_2 import ResonatorFitResult


def _cable_delay_phase(frequency: np.ndarray, delay_ns: float) -> np.ndarray:
    """Phase factor from cable delay: exp(2j * pi * f * tau)."""
    tau = delay_ns * 1e-9
    return np.exp(2j * np.pi * frequency * tau)


def _background_model(
    frequency: np.ndarray,
    slope_real: float,
    slope_imag: float,
    intercept_real: float,
    intercept_imag: float,
) -> np.ndarray:
    """Complex linear background: (a + b*f) + j*(c + d*f)."""
    bg_real = slope_real * frequency + intercept_real
    bg_imag = slope_imag * frequency + intercept_imag
    return bg_real + 1j * bg_imag


def notch_model(
    freq: np.ndarray,
    f0: float,
    ql: float,
    qc: float,
    delay: float = 0.0,
    bg_real: float = 0.0,
    bg_imag: float = 0.0,
    bg_slope_real: float = 0.0,
    bg_slope_imag: float = 0.0,
) -> np.ndarray:
    """Notch (transmission dip) resonator model: S21 = 1 - Ql/|Qc| / (1 + 2j Ql (f-f0)/f0).

    Parameters
    ----------
    f0 : float
        Resonance frequency (Hz).
    ql : float
        Loaded quality factor.
    qc : float
        Absolute coupling quality factor (|Qc|).
    delay : float
        Cable delay (ns).
    bg_real, bg_imag, bg_slope_real, bg_slope_imag : float
        Complex background parameters.
    """
    detuning = 2.0 * ql * (freq - f0) / f0
    s21 = 1.0 - (ql / abs(qc)) / (1.0 + 1j * detuning)
    phase = _cable_delay_phase(freq, delay)
    bg = _background_model(freq, bg_slope_real, bg_slope_imag, bg_real, bg_imag)
    return (s21 + bg) * phase  # type: ignore[no-any-return]


def peak_model(
    freq: np.ndarray,
    f0: float,
    ql: float,
    qc: float,
    delay: float = 0.0,
    bg_real: float = 0.0,
    bg_imag: float = 0.0,
    bg_slope_real: float = 0.0,
    bg_slope_imag: float = 0.0,
) -> np.ndarray:
    """Peak (transmission maximum) resonator model."""
    detuning = 2.0 * ql * (freq - f0) / f0
    s21 = (ql / abs(qc)) / (1.0 + 1j * detuning)
    phase = _cable_delay_phase(freq, delay)
    bg = _background_model(freq, bg_slope_real, bg_slope_imag, bg_real, bg_imag)
    return (s21 + bg) * phase  # type: ignore[no-any-return]


def reflection_model(
    freq: np.ndarray,
    f0: float,
    ql: float,
    qc: float,
    delay: float = 0.0,
    bg_real: float = 0.0,
    bg_imag: float = 0.0,
    bg_slope_real: float = 0.0,
    bg_slope_imag: float = 0.0,
) -> np.ndarray:
    """Reflection (S11) resonator model."""
    detuning = 2.0 * ql * (freq - f0) / f0
    s11 = 1.0 - (2.0 * ql / abs(qc)) / (1.0 + 1j * detuning)
    phase = _cable_delay_phase(freq, delay)
    bg = _background_model(freq, bg_slope_real, bg_slope_imag, bg_real, bg_imag)
    return (s11 + bg) * phase  # type: ignore[no-any-return]


def fit_resonator(
    freq_hz: np.ndarray,
    s_data: np.ndarray,
    response: str = "S21",
    model: str = "notch",
    f0_guess: float | None = None,
    ql_guess: float = 1000.0,
    qc_guess: float = 5000.0,
    cable_delay_guess_ns: float = 0.0,
    use_bootstrap: bool = True,
    bootstrap_samples: int = 200,
    bootstrap_seed: int = 0,
) -> ResonatorFitResult:
    """Fit a resonator model to S-parameter data.

    Parameters
    ----------
    freq_hz : np.ndarray
        Frequency axis in Hz.
    s_data : np.ndarray
        Complex S-parameter data (2D for multi-port, flattened to the target trace).
    response : str
        S-parameter label, e.g. "S21".
    model : str
        One of "notch", "peak", "reflection".
    f0_guess : float | None
        Initial frequency guess. Auto-detected if None.
    ql_guess, qc_guess : float
        Initial Q factor guesses.
    cable_delay_guess_ns : float
        Initial cable delay guess in nanoseconds.
    use_bootstrap : bool
        Whether to compute bootstrap uncertainties.
    bootstrap_samples : int
        Number of bootstrap resamples.
    bootstrap_seed : int
        Seed for reproducible residual resampling.

    Returns
    -------
    ResonatorFitResult
    """
    if model not in {"notch", "peak", "reflection"}:
        raise ValueError(f"unsupported model: {model}")

    model_func = {"notch": notch_model, "peak": peak_model, "reflection": reflection_model}[model]

    freq_hz = np.asarray(freq_hz, dtype=float).ravel()
    # Flatten S-data to 1D if needed
    s_flat = np.asarray(s_data).ravel()
    if len(s_flat) != len(freq_hz):
        raise ValueError("S-parameter data length must match frequency axis")

    if len(freq_hz) < 16 or not np.all(np.isfinite(freq_hz)):
        raise ValueError("at least 16 finite frequency samples are required")
    if not np.all(np.isfinite(s_flat.real)) or not np.all(np.isfinite(s_flat.imag)):
        raise ValueError("S-parameter data must be finite")
    if np.any(np.diff(freq_hz) <= 0):
        raise ValueError("frequency samples must be strictly increasing")
    if ql_guess <= 0 or qc_guess <= 0:
        raise ValueError("Q guesses must be positive")

    # Auto-detect f0 from magnitude minimum/maximum
    if f0_guess is None:
        mag = np.abs(s_flat)
        if model in {"notch", "reflection"}:
            f0_guess = float(freq_hz[np.argmin(mag)])
        else:
            f0_guess = float(freq_hz[np.argmax(mag)])

    # Ensure f0_guess is within frequency range
    f0_guess = max(freq_hz[0] + 1.0, min(freq_hz[-1] - 1.0, f0_guess))

    frequency_span = float(freq_hz[-1] - freq_hz[0])
    baseline = complex(np.mean(np.concatenate((s_flat[:5], s_flat[-5:]))))
    ideal_baseline = 1.0 if model in {"notch", "reflection"} else 0.0
    background_guess = baseline - ideal_baseline
    p0_internal = np.asarray(
        [
            f0_guess,
            np.log(ql_guess),
            np.log(qc_guess),
            cable_delay_guess_ns,
            background_guess.real,
            background_guess.imag,
            0.0,
            0.0,
        ],
        dtype=float,
    )
    internal_bounds = (
        np.asarray([freq_hz[0], np.log(1.0), np.log(1.0), -100.0, -10.0, -10.0, -10.0, -10.0]),
        np.asarray([freq_hz[-1], np.log(1e12), np.log(1e12), 100.0, 10.0, 10.0, 10.0, 10.0]),
    )

    def _wrap_model(
        f: np.ndarray,
        f0: float,
        ql: float,
        qc: float,
        delay: float,
        bg_r: float,
        bg_i: float,
        bg_sr: float,
        bg_si: float,
    ) -> np.ndarray:
        return model_func(f, f0, ql, qc, delay, bg_r, bg_i, bg_sr, bg_si)

    def _unpack_internal(params: np.ndarray) -> np.ndarray:
        return np.asarray(
            [
                params[0],
                np.exp(params[1]),
                np.exp(params[2]),
                params[3],
                params[4],
                params[5],
                params[6] / frequency_span,
                params[7] / frequency_span,
            ],
            dtype=float,
        )

    def _complex_residual(params: np.ndarray) -> np.ndarray:
        prediction = _wrap_model(freq_hz, *_unpack_internal(params))
        residual = prediction - s_flat
        return np.concatenate((residual.real, residual.imag))

    fit = least_squares(
        _complex_residual,
        p0_internal,
        bounds=internal_bounds,
        x_scale=np.asarray(
            [frequency_span, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            dtype=float,
        ),
        max_nfev=50_000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    popt = _unpack_internal(fit.x)
    pcov = None
    condition_number = None
    fit_warnings: list[str] = []
    try:
        information = fit.jac.T @ fit.jac
        condition_number = float(np.linalg.cond(information))
        residual_degrees_of_freedom = max(1, 2 * len(freq_hz) - len(fit.x))
        residual_variance = float(np.sum(fit.fun**2) / residual_degrees_of_freedom)
        covariance_internal = np.linalg.pinv(information) * residual_variance
        transform = np.diag(
            [1.0, popt[1], popt[2], 1.0, 1.0, 1.0, 1.0 / frequency_span, 1.0 / frequency_span]
        )
        pcov = transform @ covariance_internal @ transform.T
    except np.linalg.LinAlgError:
        fit_warnings.append("parameter covariance could not be estimated")
    optimizer_converged = bool(fit.success)
    optimizer_message = str(fit.message)

    f0, ql, qc, delay, bg_r, bg_i, bg_sr, bg_si = [float(np.real(v)) for v in popt]

    # Compute residuals
    fitted = _wrap_model(freq_hz, *popt)
    residuals = s_flat - fitted
    residual_rms = float(np.sqrt(np.mean(np.abs(residuals) ** 2)))
    residual_max = float(np.max(np.abs(residuals)))

    # Q factor decomposition
    ql_abs = abs(ql)
    qc_abs = abs(qc)
    # 1/Qi = 1/Ql - 1/|Qc| for notch; for peak/reflection adjust
    if model == "notch":
        inverse_q_internal = 1.0 / ql_abs - 1.0 / qc_abs
        qi = 1.0 / inverse_q_internal if inverse_q_internal > 0 else None
        if qi is None:
            fit_warnings.append("notch parameters do not imply a positive internal Q")
    else:
        qi = None
        fit_warnings.append(f"internal Q is not identified by the {model} model")

    coupling_coeff = ql_abs / qc_abs if qc_abs > 0 else None

    # Parameter uncertainties from covariance
    uncertainties = {}
    if pcov is not None:
        try:
            perr = np.sqrt(np.diag(pcov))
            param_names = [
                "f0_hz",
                "q_loaded",
                "q_coupling",
                "delay_ns",
                "bg_r",
                "bg_i",
                "bg_sr",
                "bg_si",
            ]
            uncertainties = {n: float(v) for n, v in zip(param_names, perr, strict=False)}
        except (FloatingPointError, ValueError) as exc:
            fit_warnings.append(f"parameter uncertainty calculation failed: {exc}")

    f0_unc = uncertainties.get("f0_hz", 0.0)
    ql_unc = uncertainties.get("q_loaded", 0.0)
    qc_unc = uncertainties.get("q_coupling", 0.0)
    if not uncertainties:
        fit_warnings.append("fit uncertainty is unavailable")
    if condition_number is not None and condition_number > 1e12:
        fit_warnings.append("fit is ill-conditioned; parameter uncertainties may be unreliable")

    # Compute AIC and BIC for model comparison
    n_params = 8
    n_points = 2 * len(freq_hz)
    rss = max(float(np.sum(np.abs(residuals) ** 2)), np.finfo(float).tiny)
    log_likelihood = -0.5 * n_points * np.log(2 * np.pi * rss / n_points) - 0.5 * n_points
    aic = 2 * n_params - 2 * log_likelihood
    bic = n_params * np.log(n_points) - 2 * log_likelihood

    dof = n_points - n_params

    # Bootstrap uncertainties
    bootstrap_conf = {}
    if use_bootstrap:
        try:
            b_conf = _bootstrap_confidence(
                _wrap_model,
                freq_hz,
                s_flat,
                popt,
                (
                    [freq_hz[0], 1.0, 1.0, -100.0, -10.0, -10.0, -np.inf, -np.inf],
                    [freq_hz[-1], 1e12, 1e12, 100.0, 10.0, 10.0, np.inf, np.inf],
                ),
                n_samples=bootstrap_samples,
                seed=bootstrap_seed,
            )
            bootstrap_conf = b_conf
        except Exception:
            fit_warnings.append("bootstrap uncertainty estimation failed")
        if not bootstrap_conf:
            fit_warnings.append("bootstrap produced too few successful samples")

    return ResonatorFitResult(
        model=model,
        f0_hz=float(f0),
        f0_uncertainty_hz=float(f0_unc),
        q_loaded=float(ql_abs),
        q_loaded_uncertainty=float(ql_unc),
        q_coupling_absolute=float(qc_abs),
        q_coupling_uncertainty=float(qc_unc),
        q_internal=float(qi) if qi is not None and np.isfinite(qi) else None,
        q_internal_uncertainty=None,
        coupling_coefficient=float(coupling_coeff) if coupling_coeff is not None else None,
        cable_delay_ns=float(delay),
        cable_delay_uncertainty_ns=float(uncertainties.get("delay_ns", 0.0)),
        background_slope_real=float(bg_sr),
        background_slope_imag=float(bg_si),
        background_intercept_real=float(bg_r),
        background_intercept_imag=float(bg_i),
        residual_rms=residual_rms,
        residual_max=residual_max,
        condition_number=condition_number,
        optimizer_converged=optimizer_converged,
        optimizer_message=optimizer_message,
        chi_squared=None,
        degrees_of_freedom=int(dof),
        reduced_chi_squared=None,
        aic=float(aic),
        bic=float(bic),
        bootstrap_samples=bootstrap_samples if use_bootstrap else 0,
        bootstrap_confidence_95=bootstrap_conf,
        parameter_correlation={},
        warnings=fit_warnings,
        fit_timestamp_utc=datetime.now(UTC),
    )


def _bootstrap_confidence(
    model_func: Callable[..., np.ndarray],
    freq: np.ndarray,
    s_data: np.ndarray,
    popt: np.ndarray,
    bounds: tuple[list[float], list[float]],
    n_samples: int = 200,
    seed: int = 0,
) -> dict[str, tuple[float, float]]:
    """Estimate 95% confidence intervals via parametric bootstrap."""
    n = len(freq)
    rng = np.random.default_rng(seed)
    fitted = model_func(freq, *popt)
    residuals = s_data - fitted
    param_samples: dict[str, list[float]] = {}

    for _ in range(n_samples):
        # Resample residuals
        idx = rng.integers(0, n, n)
        boot_data = fitted + residuals[idx]

        def _cost(p, f, s):
            pred = model_func(f, *p)
            return float(np.sum(np.abs(pred - s) ** 2))

        b_opt: np.ndarray | None = None
        try:
            opt_result = minimize(
                _cost,
                popt,
                args=(freq, boot_data),
                method="L-BFGS-B",
                bounds=[(lo, hi) for lo, hi in zip(bounds[0], bounds[1], strict=False)],
                options={"maxiter": 500},
            )
            b_opt = opt_result.x
        except Exception:
            b_opt = None

        if b_opt is not None:
            param_names = [
                "f0_hz",
                "q_loaded",
                "q_coupling",
                "delay_ns",
                "bg_r",
                "bg_i",
                "bg_sr",
                "bg_si",
            ]
            for name, val in zip(param_names, b_opt, strict=False):
                param_samples.setdefault(name, []).append(float(val))

    result: dict[str, tuple[float, float]] = {}
    for name, values in param_samples.items():
        if len(values) >= 50:
            lo, hi = np.percentile(values, [2.5, 97.5])
            result[name] = (float(lo), float(hi))

    return result


def detect_resonances(
    freq_hz: np.ndarray,
    s_mag_db: np.ndarray,
    min_depth_db: float = 3.0,
    min_separation_hz: float = 1e6,
) -> list[float]:
    """Detect resonance frequencies from |S21| in dB.

    Returns detected f0 values in Hz.
    """
    # Find local minima
    from scipy.signal import argrelextrema

    minima_idx = argrelextrema(s_mag_db, np.less)[0]

    resonances: list[float] = []
    for idx in minima_idx:
        # Check depth relative to surrounding
        depth = 0.0
        for offset in range(1, min(5, idx + 1)):
            depth = max(depth, float(s_mag_db[idx + offset] - s_mag_db[idx]))
        for offset in range(1, min(5, len(s_mag_db) - idx)):
            depth = max(depth, float(s_mag_db[idx - offset] - s_mag_db[idx]))

        if depth >= min_depth_db:
            f0 = float(freq_hz[idx])
            # Check separation from already-found resonances
            if all(abs(f0 - r) >= min_separation_hz for r in resonances):
                resonances.append(f0)

    return sorted(resonances)


def _collect_trace(network: Any, port_out: int, port_in: int) -> np.ndarray:
    """Extract the S(port_out, port_in) trace from a scikit-rf Network."""
    return np.asarray(network.s[:, port_out - 1, port_in - 1])


def fit_bundle_resonator(
    bundle: Path,
    response: str = "S21",
    model: str = "notch",
    f0_guess: float | None = None,
    **kwargs: Any,
) -> ResonatorFitResult:
    """Fit resonator(s) from a validated bundle's Touchstone data."""
    manifest = load_manifest(bundle / "manifest.json")
    if manifest.touchstone is None:
        raise ValueError("bundle has no Touchstone data")

    network = load_network(safe_bundle_path(bundle, manifest.touchstone.path))

    # Parse response label like "S21"
    port_out = int(response[1])
    port_in = int(response[2])
    s_trace = _collect_trace(network, port_out, port_in)

    return fit_resonator(
        np.asarray(network.f),
        s_trace,
        response=response,
        model=model,
        f0_guess=f0_guess,
        **kwargs,
    )
