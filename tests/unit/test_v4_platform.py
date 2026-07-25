import numpy as np
import pytest

from qresaudit.analysis.optimization import (
    GaussianProcessSurrogate,
    active_learning_candidates,
    bayesian_optimization,
    evaluate_candidate,
)
from qresaudit.digital_twin import calibrate_resonator, update_material_loss_model
from qresaudit.geometry import make_cpw_design
from qresaudit.knowledge import KnowledgeBase, KnowledgeRecord
from qresaudit.loop import SimulationLoop
from qresaudit.models.v0_2 import OptimizationObjective
from qresaudit.multiphysics import combine_perturbations, thermal_frequency_shift
from qresaudit.planner import parse_design_requirements
from qresaudit.robust import correlated_robust_analysis


def test_gp_uncertainty_and_seeded_selection():
    model = GaussianProcessSurrogate().fit(np.array([[0.0], [1.0]]), np.array([0.0, 1.0]))
    mean, std = model.predict(np.array([[0.5], [4.0]]))
    assert np.all(np.isfinite(mean)) and np.all(std >= 0)
    bounds = {"x": (0.0, 1.0)}
    assert active_learning_candidates(model, bounds, seed=4) == active_learning_candidates(
        model, bounds, seed=4
    )
    with pytest.raises(ValueError):
        active_learning_candidates(model, {"x": (1.0, 1.0)})


def test_correlated_robust_result_is_reproducible():
    def evaluate(p):
        return {"frequency_hz": p["width"] + 2 * p["gap"]}

    args = (
        {"width": 1.0, "gap": 2.0},
        {"width": 0.1, "gap": 0.2},
        np.array([[1, 0.5], [0.5, 1]]),
        evaluate,
    )
    first = correlated_robust_analysis(*args, samples=100, seed=3)
    second = correlated_robust_analysis(*args, samples=100, seed=3)
    assert first == second and 0 <= first.feasible_fraction <= 1


def test_geometry_planner_knowledge_and_units():
    assert make_cpw_design("r", 6e9).resonator_length_m > 0
    req = parse_design_requirements("Design a 6 GHz Er spin-coupling resonator")
    assert req.target_frequency_hz == 6e9 and req.unknown_requirements
    db = KnowledgeBase([KnowledgeRecord("m1", "material", "Al", None, "unknown", (), {})])
    assert db.query(kind="material")[0].source_identifier is None
    term = thermal_frequency_shift(6e9, 1, 1e-5)
    assert combine_perturbations(term).units == "Hz"


def test_bayesian_optimizer_uses_gp_and_rejects_unsafe_expression():
    objective = OptimizationObjective(name="loss", expression="(x - 0.25) ** 2")
    result = bayesian_optimization(
        objective,
        {"x": (0.0, 1.0)},
        n_initial=4,
        n_iterations=10,
    )
    assert result.surrogate_model_name == "squared_exponential_gaussian_process"
    assert result.best_candidate is not None
    assert result.best_candidate.objectives["loss"] < 0.02

    unsafe = OptimizationObjective(name="unsafe", expression="__import__('os').getcwd()")
    candidate = evaluate_candidate({"x": 1.0}, [unsafe], [])
    assert candidate.objectives["unsafe"] == float("inf")


def test_digital_twin_permittivity_update_and_loop_gates(tmp_path):
    calibration = calibrate_resonator(
        {"frequency_hz": 6.0e9, "q": 1.0e6},
        {"frequency_hz": 5.9e9, "q": 0.9e6},
    )
    updated = update_material_loss_model({"permittivity": 10.0}, calibration)
    assert updated["permittivity"] == pytest.approx(10.0 * (6.0 / 5.9) ** 2)

    loop = SimulationLoop(tmp_path / "loop.json", budget=1)
    assert loop.dry_run_step().state == "WAITING_FOR_APPROVAL"
    assert loop.dry_run_step().state == "WAITING_FOR_APPROVAL"
