"""Cross-solver, analytic, and experimental scalar benchmarks."""

import math
from dataclasses import dataclass

from qresaudit.v2 import Status


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    status: Status
    absolute_error: float
    relative_error: float
    tolerance: float


def compare(name: str, predicted: float, reference: float, tolerance: float) -> BenchmarkResult:
    if not all(math.isfinite(value) for value in (predicted, reference, tolerance)):
        raise ValueError("benchmark values must be finite")
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    error = abs(predicted - reference)
    relative = error / max(abs(reference), 1e-30)
    return BenchmarkResult(
        name,
        Status.PASS if error <= tolerance else Status.FAIL,
        error,
        relative,
        tolerance,
    )
