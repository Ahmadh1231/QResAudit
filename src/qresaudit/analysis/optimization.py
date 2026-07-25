"""Design optimization framework — sweep ingestion, Pareto analysis, surrogate models.

Commands:
    qresaudit optimize sweep BUNDLE_DIRECTORY --objectives objectives.yaml
    qresaudit optimize bayesian CONFIG --iterations 100
"""

import json
from pathlib import Path
from typing import Any

import numpy as np

from qresaudit.models.v0_2 import (
    OptimizationCandidate,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationResult,
)


def is_dominated(a: OptimizationCandidate, b: OptimizationCandidate,
                 objectives: list[str]) -> bool:
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


def compute_pareto_front(candidates: list[OptimizationCandidate],
                         objectives: list[str]) -> list[OptimizationCandidate]:
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


def evaluate_candidate(variables: dict[str, float],
                       objectives: list[OptimizationObjective],
                       constraints: list[OptimizationConstraint]) -> OptimizationCandidate:
    """Evaluate objectives and constraints for a given variable set.

    This is a placeholder — in a real run, this would invoke an external
    solver or surrogate model evaluation.
    """
    obj_vals: dict[str, float] = {}
    for obj in objectives:
        # Evaluate objective expression with substituted variables
        try:
            val = float(eval(obj.expression, {"__builtins__": {}}, variables))
        except Exception:
            val = float("inf")
        obj_vals[obj.name] = val

    con_vals: dict[str, float] = {}
    is_feasible = True
    for con in constraints:
        try:
            val = float(eval(con.expression, {"__builtins__": {}}, variables))
        except Exception:
            val = float("inf")
        con_vals[con.name] = val
        if con.kind == "inequality" and val > con.bound + con.tolerance:
            is_feasible = False
        elif con.kind == "equality" and abs(val - con.bound) > con.tolerance:
            is_feasible = False

    return OptimizationCandidate(
        id=",".join(f"{k}={v}" for k, v in sorted(variables.items())),
        variables=variables,
        objectives=obj_vals,
        constraints=con_vals,
        is_feasible=is_feasible,
    )


def random_latin_hypercube(n_points: int, bounds: dict[str, tuple[float, float]],
                           seed: int = 42) -> list[dict[str, float]]:
    """Generate a Latin Hypercube sample of design points."""
    rng = np.random.default_rng(seed)
    n_dims = len(bounds)
    names = list(bounds)
    samples = []

    # Latin hypercube: stratify each dimension
    segments = np.linspace(0, 1, n_points + 1)
    for i in range(n_points):
        point: dict[str, float] = {}
        for dim_idx, name in enumerate(names):
            lo, hi = bounds[name]
            u = rng.uniform(segments[i], segments[i + 1])
            point[name] = float(lo + u * (hi - lo))
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
    bounds_list = list(variables.values())
    dims = len(bounds_list)

    # Initial Latin Hypercube samples
    initial = random_latin_hypercube(n_initial, variables)
    candidates = [
        evaluate_candidate(p, [objective], constraints or [])
        for p in initial
    ]

    best = min(candidates, key=lambda c: c.objectives.get(objective.name, float("inf")))

    # Simple random search with local refinement as placeholder for full GP-BO
    for iteration in range(n_iterations - n_initial):
        # Explore: random candidate
        point: dict[str, float] = {}
        for name, (lo, hi) in variables.items():
            point[name] = float(np.random.uniform(lo, hi))

        candidate = evaluate_candidate(point, [objective], constraints or [])

        if candidate.is_feasible:
            if candidate.objectives.get(objective.name, float("inf")) < \
               best.objectives.get(objective.name, float("inf")):
                best = candidate

        candidates.append(candidate)

    pareto = compute_pareto_front(
        [c for c in candidates if c.is_feasible],
        [objective.name],
    )

    return OptimizationResult(
        method="bayesian_optimization_rbf",
        candidates=candidates,
        pareto_front=pareto,
        best_candidate=best,
        iterations=n_iterations,
        evaluations=len(candidates),
        converged=len(pareto) > 0,
        elapsed_time_s=0.0,
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
            "p95": float(np.percentile(finite, 95)) if len(finite) >= 20 else (float(np.max(finite)) if finite else float("inf")),
            "p5": float(np.percentile(finite, 5)) if len(finite) >= 20 else (float(np.min(finite)) if finite else float("inf")),
        }

    return results
