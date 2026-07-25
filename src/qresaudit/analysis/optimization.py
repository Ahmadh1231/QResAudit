"""Design optimization framework — sweep ingestion, Pareto analysis, surrogate models.

Commands:
    qresaudit optimize sweep BUNDLE_DIRECTORY --objectives objectives.yaml
    qresaudit optimize bayesian CONFIG --iterations 100
"""

import ast
from dataclasses import dataclass

import numpy as np

from qresaudit.models.v0_2 import (
    OptimizationCandidate,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationResult,
)


def _finite_array(value: object, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.size == 0 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite values")
    return result


def _evaluate_expression(expression: str, variables: dict[str, float]) -> float:
    """Evaluate a numeric expression without Python ``eval`` or attribute access."""

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            return float(variables[node.id])
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return float(left**right)
            if isinstance(node.op, ast.Mod):
                return left % right
        if isinstance(node, ast.UnaryOp):
            value = evaluate(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"abs", "max", "min"}
            and not node.keywords
        ):
            arguments = [evaluate(arg) for arg in node.args]
            if node.func.id == "abs" and len(arguments) == 1:
                return abs(arguments[0])
            if node.func.id == "max" and arguments:
                return max(arguments)
            if node.func.id == "min" and arguments:
                return min(arguments)
        raise ValueError("expression contains an unsupported operation")

    result = evaluate(ast.parse(expression, mode="eval"))
    if not np.isfinite(result):
        raise ValueError("expression result must be finite")
    return result


def _validate_bounds(
    bounds: dict[str, tuple[float, float]],
) -> tuple[list[str], np.ndarray, np.ndarray]:
    if not bounds:
        raise ValueError("at least one bound is required")
    names = list(bounds)
    low = np.asarray([bounds[n][0] for n in names], dtype=float)
    high = np.asarray([bounds[n][1] for n in names], dtype=float)
    if not np.all(np.isfinite(low)) or not np.all(np.isfinite(high)) or np.any(high <= low):
        raise ValueError("bounds must be finite and have upper > lower")
    return names, low, high


@dataclass(frozen=True)
class GaussianProcessPrediction:
    mean: float
    standard_deviation: float


class GaussianProcessSurrogate:
    """Small deterministic GP using a squared-exponential kernel.

    Inputs are dimensionless normalized coordinates; outputs retain their units.
    The nugget is a non-negative observation-noise variance in output units squared.
    """

    def __init__(self, length_scale: float = 0.2, nugget: float = 1e-10) -> None:
        if (
            not np.isfinite(length_scale)
            or length_scale <= 0
            or not np.isfinite(nugget)
            or nugget < 0
        ):
            raise ValueError("length_scale must be positive and nugget non-negative")
        self.length_scale = float(length_scale)
        self.nugget = float(nugget)
        self._x: np.ndarray | None = None
        self._alpha: np.ndarray | None = None
        self._chol: np.ndarray | None = None
        self._y_scale = 1.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> "GaussianProcessSurrogate":
        x = _finite_array(x, "x")
        y = _finite_array(y, "y").reshape(-1)
        if x.ndim != 2 or len(x) != len(y) or len(x) == 0:
            raise ValueError("x must be 2-D and have non-empty matching y")
        self._x = x
        self._y_scale = max(float(np.std(y)), 1.0)
        ys = y / self._y_scale
        kernel = self._kernel(x, x) + np.eye(len(x)) * self.nugget
        jitter = 1e-12
        for _ in range(6):
            try:
                self._chol = np.linalg.cholesky(kernel + np.eye(len(x)) * jitter)
                break
            except np.linalg.LinAlgError:
                jitter *= 100
        else:
            raise ValueError("unable to factorize GP covariance")
        self._alpha = np.linalg.solve(self._chol.T, np.linalg.solve(self._chol, ys))
        return self

    def _kernel(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        distance = a[:, None, :] - b[None, :, :]
        value: np.ndarray = np.asarray(
            np.exp(-0.5 * np.sum(distance * distance, axis=2) / self.length_scale**2),
            dtype=float,
        )
        return value

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self._x is None or self._alpha is None or self._chol is None:
            raise ValueError("fit the surrogate before prediction")
        points = _finite_array(x, "x")
        if points.ndim == 1:
            points = points.reshape(1, -1)
        if points.ndim != 2 or points.shape[1] != self._x.shape[1]:
            raise ValueError("prediction dimensions do not match training data")
        k = self._kernel(points, self._x)
        mean = k @ self._alpha * self._y_scale
        v = np.linalg.solve(self._chol, k.T)
        variance = np.maximum(0.0, 1.0 - np.sum(v * v, axis=0)) * self._y_scale**2
        return mean, np.sqrt(variance)


def active_learning_candidates(
    surrogate: GaussianProcessSurrogate,
    bounds: dict[str, tuple[float, float]],
    *,
    n_candidates: int = 1,
    direction: str = "minimize",
    seed: int = 0,
    exploration: float = 1.0,
) -> list[dict[str, float]]:
    """Select candidates by lower/upper confidence bound in validated bounds."""
    names, low, high = _validate_bounds(bounds)
    if (
        n_candidates < 1
        or direction not in {"minimize", "maximize"}
        or not np.isfinite(exploration)
        or exploration < 0
    ):
        raise ValueError("invalid candidate selection arguments")
    rng = np.random.default_rng(seed)
    pool = low + rng.random((max(128, n_candidates * 32), len(names))) * (high - low)
    mean, std = surrogate.predict((pool - low) / (high - low))
    score = mean - exploration * std if direction == "minimize" else mean + exploration * std
    order = np.argsort(score, kind="stable")[:n_candidates]
    return [{name: float(pool[i, j]) for j, name in enumerate(names)} for i in order]


def is_dominated(a: OptimizationCandidate, b: OptimizationCandidate, objectives: list[str]) -> bool:
    """Check if candidate 'a' is Pareto-dominated by candidate 'b'.

    Returns True if b dominates a (b is better in at least one objective
    and not worse in any).
    """
    a_better = 0
    b_better = 0
    for obj in objectives:
        av = a.objectives.get(obj, 0.0)
        bv = b.objectives.get(obj, 0.0)
        if av < bv:
            b_better += 1
        elif bv < av:
            a_better += 1
    return b_better > 0 and a_better == 0


def compute_pareto_front(
    candidates: list[OptimizationCandidate], objectives: list[str]
) -> list[OptimizationCandidate]:
    """Compute the Pareto-optimal front from a list of candidates."""
    n = len(candidates)
    for i in range(n):
        for j in range(n):
            if i != j and is_dominated(candidates[i], candidates[j], objectives):
                candidates[i].dominated = True
                break
        else:
            candidates[i].dominated = False

    return sorted(
        [c for c in candidates if not c.dominated],
        key=lambda c: sum(c.objectives.get(o, 0.0) for o in objectives),
    )


def evaluate_candidate(
    variables: dict[str, float],
    objectives: list[OptimizationObjective],
    constraints: list[OptimizationConstraint],
) -> OptimizationCandidate:
    """Evaluate objectives and constraints for a given variable set.

    This is a placeholder — in a real run, this would invoke an external
    solver or surrogate model evaluation.
    """
    obj_vals: dict[str, float] = {}
    for obj in objectives:
        try:
            val = _evaluate_expression(obj.expression, variables)
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError):
            val = float("inf")
        obj_vals[obj.name] = val

    con_vals: dict[str, float] = {}
    is_feasible = True
    for con in constraints:
        try:
            val = _evaluate_expression(con.expression, variables)
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError):
            val = float("inf")
        con_vals[con.name] = val
        inequality_violation = con.kind == "inequality" and val > con.bound + con.tolerance
        equality_violation = con.kind == "equality" and abs(val - con.bound) > con.tolerance
        if inequality_violation or equality_violation:
            is_feasible = False

    return OptimizationCandidate(
        id=",".join(f"{k}={v}" for k, v in sorted(variables.items())),
        variables=variables,
        objectives=obj_vals,
        constraints=con_vals,
        is_feasible=is_feasible,
    )


def random_latin_hypercube(
    n_points: int, bounds: dict[str, tuple[float, float]], seed: int = 42
) -> list[dict[str, float]]:
    """Generate a Latin Hypercube sample of design points."""
    _validate_bounds(bounds)
    if n_points < 1:
        raise ValueError("n_points must be positive")
    rng = np.random.default_rng(seed)
    names = list(bounds)
    unit_samples = np.empty((n_points, len(names)), dtype=float)
    for dimension in range(len(names)):
        strata = (np.arange(n_points, dtype=float) + rng.random(n_points)) / n_points
        unit_samples[:, dimension] = strata[rng.permutation(n_points)]

    samples: list[dict[str, float]] = []
    for i in range(n_points):
        point: dict[str, float] = {}
        for dimension, name in enumerate(names):
            lo, hi = bounds[name]
            point[name] = float(lo + unit_samples[i, dimension] * (hi - lo))
        samples.append(point)

    return samples


def bayesian_optimization(
    objective: OptimizationObjective,
    variables: dict[str, tuple[float, float]],
    constraints: list[OptimizationConstraint] | None = None,
    n_iterations: int = 100,
    n_initial: int = 20,
) -> OptimizationResult:
    """Bayesian optimization with Gaussian Process surrogate.

    Currently uses a simple RBF kernel GP approximation.
    For a full implementation, scikit-learn or GPy would be used.
    """
    names, low, high = _validate_bounds(variables)
    if n_iterations < 1 or n_initial < 1 or n_initial > n_iterations:
        raise ValueError("n_initial must be in [1, n_iterations]")
    initial = random_latin_hypercube(n_initial, variables)
    candidates = [evaluate_candidate(p, [objective], constraints or []) for p in initial]
    for iteration in range(n_iterations - n_initial):
        finite_candidates = [
            candidate
            for candidate in candidates
            if np.isfinite(candidate.objectives.get(objective.name, float("inf")))
        ]
        if not finite_candidates:
            raise ValueError("objective expression did not produce any finite values")
        training_x = np.asarray(
            [[candidate.variables[name] for name in names] for candidate in finite_candidates]
        )
        training_x = (training_x - low) / (high - low)
        training_y = np.asarray(
            [candidate.objectives[objective.name] for candidate in finite_candidates]
        )
        surrogate = GaussianProcessSurrogate().fit(training_x, training_y)
        point = active_learning_candidates(
            surrogate,
            variables,
            direction="minimize" if objective.minimize else "maximize",
            seed=43 + iteration,
            exploration=max(0.1, 1.5 / np.sqrt(iteration + 1)),
        )[0]
        candidate = evaluate_candidate(point, [objective], constraints or [])
        candidates.append(candidate)

    feasible = [candidate for candidate in candidates if candidate.is_feasible]
    finite_feasible = [
        candidate
        for candidate in feasible
        if np.isfinite(candidate.objectives.get(objective.name, float("inf")))
    ]
    if not finite_feasible:
        raise ValueError("optimization produced no feasible finite candidates")

    def objective_value(candidate: OptimizationCandidate) -> float:
        return candidate.objectives[objective.name]

    best = (min if objective.minimize else max)(finite_feasible, key=objective_value)
    pareto = [best]

    return OptimizationResult(
        method="bayesian_optimization_rbf",
        candidates=candidates,
        pareto_front=pareto,
        best_candidate=best,
        iterations=n_iterations,
        evaluations=len(candidates),
        converged=len(pareto) > 0,
        elapsed_time_s=0.0,
        surrogate_model_name="squared_exponential_gaussian_process",
        acquisition_function=(
            "lower_confidence_bound" if objective.minimize else "upper_confidence_bound"
        ),
    )


def fabrication_tolerance_analysis(
    nominal: dict[str, float],
    tolerances: dict[str, float],
    objective: OptimizationObjective,
    n_samples: int = 1000,
) -> dict[str, dict[str, float]]:
    """Monte Carlo fabrication tolerance analysis.

    Returns statistics per variable: mean, std, min, max of the objective.
    """
    rng = np.random.default_rng(42)
    results: dict[str, dict[str, float]] = {}

    for var_name, tol in tolerances.items():
        samples = rng.normal(0, tol, n_samples)
        obj_vals: list[float] = []
        for sample in samples:
            perturbed = dict(nominal)
            perturbed[var_name] = nominal[var_name] + sample
            candidate = evaluate_candidate(perturbed, [objective], [])
            obj_vals.append(candidate.objectives.get(objective.name, float("inf")))

        finite = [v for v in obj_vals if np.isfinite(v)]
        results[var_name] = {
            "mean": float(np.mean(finite)) if finite else float("inf"),
            "std": float(np.std(finite)) if len(finite) > 1 else 0.0,
            "min": float(np.min(finite)) if finite else float("inf"),
            "max": float(np.max(finite)) if finite else float("inf"),
            "p95": float(np.percentile(finite, 95))
            if len(finite) >= 20
            else (float(np.max(finite)) if finite else float("inf")),
            "p5": float(np.percentile(finite, 5))
            if len(finite) >= 20
            else (float(np.min(finite)) if finite else float("inf")),
        }

    return results
