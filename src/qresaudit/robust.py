"""Fabrication-aware robust design calculations (offline and reproducible)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RobustResult:
    samples: int
    seed: int
    mean: dict[str, float]
    standard_deviation: dict[str, float]
    quantiles: dict[str, dict[str, float]]
    feasible_fraction: float
    confidence_interval_95: tuple[float, float]
    sensitivity: dict[str, float]
    provenance: dict[str, object]


def correlated_robust_analysis(
    nominal: dict[str, float],
    sigma: dict[str, float],
    correlation: np.ndarray,
    evaluator: Callable[[dict[str, float]], dict[str, float]],
    *,
    samples: int = 1000,
    seed: int = 0,
    constraints: Callable[[dict[str, float]], bool] | None = None,
) -> RobustResult:
    names = list(nominal)
    if not names or set(sigma) != set(names) or samples < 1:
        raise ValueError("nominal/sigma must match and samples must be positive")
    if not all(np.isfinite(value) for value in nominal.values()) or not all(
        np.isfinite(value) for value in sigma.values()
    ):
        raise ValueError("nominal and sigma values must be finite")
    n = len(names)
    corr = np.asarray(correlation, dtype=float)
    if corr.shape != (n, n) or not np.all(np.isfinite(corr)) or not np.allclose(corr, corr.T):
        raise ValueError("correlation must be a finite symmetric square matrix")
    if np.any(np.asarray(list(sigma.values())) < 0) or not np.allclose(np.diag(corr), 1):
        raise ValueError("sigma must be non-negative and correlation diagonal must be one")
    try:
        np.linalg.cholesky(corr + np.eye(n) * 1e-12)
    except np.linalg.LinAlgError as exc:
        raise ValueError("correlation must be positive semidefinite") from exc
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(np.zeros(n), corr, size=samples)
    outputs = [
        evaluator({k: float(nominal[k] + sigma[k] * d[i]) for i, k in enumerate(names)})
        for d in draws
    ]
    if not outputs or any(not all(np.isfinite(v) for v in item.values()) for item in outputs):
        raise ValueError("evaluator outputs must be finite")
    keys = sorted(outputs[0])
    if not keys or any(set(output) != set(keys) for output in outputs):
        raise ValueError("evaluator outputs must have consistent non-empty keys")
    arr = {k: np.asarray([o[k] for o in outputs], dtype=float) for k in keys}
    feasible = np.asarray([constraints(o) if constraints else True for o in outputs], dtype=bool)
    primary = arr[keys[0]]
    se = float(np.std(primary, ddof=1) / math.sqrt(samples)) if samples > 1 else 0.0
    sensitivity = {}
    for i, name in enumerate(names):
        sensitivity[name] = (
            float(np.corrcoef(draws[:, i], primary)[0, 1]) if np.std(primary) > 0 else 0.0
        )
    return RobustResult(
        samples,
        seed,
        {k: float(np.mean(v)) for k, v in arr.items()},
        {k: float(np.std(v, ddof=1)) if samples > 1 else 0.0 for k, v in arr.items()},
        {
            k: {
                q: float(np.quantile(v, p)) for q, p in (("p05", 0.05), ("p50", 0.5), ("p95", 0.95))
            }
            for k, v in arr.items()
        },
        float(np.mean(feasible)),
        (float(np.mean(primary) - 1.96 * se), float(np.mean(primary) + 1.96 * se)),
        sensitivity,
        {
            "method": "correlated_normal_monte_carlo",
            "seed": seed,
            "samples": samples,
            "primary_metric": keys[0],
            "units": "inherited from evaluator",
        },
    )
