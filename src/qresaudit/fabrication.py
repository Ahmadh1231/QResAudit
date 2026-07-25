"""Deterministic Monte Carlo yield analysis for fabrication variation."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class YieldResult:
    samples: int
    accepted: int
    yield_fraction: float
    standard_error: float
    seed: int


def monte_carlo_yield(
    nominal: dict[str, float],
    sigma: dict[str, float],
    predicate: Callable[[dict[str, float]], bool],
    samples: int = 1000,
    seed: int = 0,
) -> dict[str, float | int]:
    if samples < 1:
        raise ValueError("samples must be positive")
    if (
        set(sigma) - set(nominal)
        or any(not np.isfinite(value) for value in nominal.values())
        or any(not np.isfinite(value) or value < 0 for value in sigma.values())
    ):
        raise ValueError("sigma keys must be nominal parameters and values must be non-negative")
    rng = np.random.default_rng(seed)
    accepted = 0
    for _ in range(samples):
        point = {
            name: float(value + rng.normal(0, sigma.get(name, 0.0)))
            for name, value in nominal.items()
        }
        accepted += int(predicate(point))
    fraction = accepted / samples
    result = YieldResult(
        samples=samples,
        accepted=accepted,
        yield_fraction=fraction,
        standard_error=float(np.sqrt(fraction * (1 - fraction) / samples)),
        seed=seed,
    )
    return {
        "samples": result.samples,
        "accepted": result.accepted,
        "yield_fraction": result.yield_fraction,
        "standard_error": result.standard_error,
        "seed": result.seed,
    }
