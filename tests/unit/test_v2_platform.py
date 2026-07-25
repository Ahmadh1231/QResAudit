import hashlib
import math

import numpy as np
import pytest

from qresaudit.adapters import ADAPTERS
from qresaudit.dataset import LinearSurrogate
from qresaudit.diagnosis import diagnose
from qresaudit.fabrication import monte_carlo_yield
from qresaudit.jobs import JobSpec, render_job
from qresaudit.measurement import Sweep, compare_sweeps, resonance_frequency_shift
from qresaudit.quantum import (
    PHI0,
    cooperativity,
    josephson_energy,
    squid_effective_ej,
    tls_q,
    transmon_frequency,
)
from qresaudit.v2 import (
    FieldEvidence,
    PhysicsRecord,
    SimulationManifest,
    SolverRecord,
    Status,
)


def test_all_portable_adapters_are_explicit(tmp_path):
    assert set(ADAPTERS) == {"hfss", "palace", "comsol", "cst", "sonnet", "openems", "elmer"}
    (tmp_path / "network.s2p").write_text("# GHz S RI R 50\n", encoding="utf-8")
    manifest = ADAPTERS["cst"].import_bundle(tmp_path)
    assert manifest.evidence["s2p"] == Status.WARNING
    assert manifest.evidence["fields"] == Status.NOT_EVALUATED
    assert manifest.provenance["validated"] is False


def test_missing_evidence_is_not_evaluated():
    findings = diagnose({})
    assert findings[0].status == Status.NOT_EVALUATED
    assert all(finding.status in Status for finding in findings)
    present = diagnose({"participation": {"value": 0.5}})
    states = {finding.code: finding.status for finding in present}
    assert states["PARTICIPATION"] == Status.WARNING


def test_diagnosis_detects_convergence_mesh_and_hotspot_failures():
    findings = diagnose(
        {
            "convergence_passes": [1, 2, 3],
            "final_frequency_change_fraction": 0.03,
            "requested_frequency_change_fraction": 0.01,
            "mesh_quality": [0.05, 0.8],
            "field_hotspots": [1.5],
        }
    )
    states = {finding.code: finding.status for finding in findings}
    assert states["CONVERGENCE_CRITERION_MISSED"] == Status.FAIL
    assert states["MESH_QUALITY_LOW"] == Status.FAIL
    assert states["FIELD_HOTSPOT"] == Status.WARNING


def test_measurement_limiting_case_and_mismatch():
    x = np.arange(3.0)
    y = np.ones(3)
    result = compare_sweeps(
        Sweep("temperature", x, y),
        Sweep("temperature", x, y, np.ones(3)),
    )
    assert result.status == Status.PASS and result.rms == 0
    assert compare_sweeps(Sweep("power", x, y), Sweep("temperature", x, y)).status == Status.FAIL
    assert compare_sweeps(Sweep("power", x, y), Sweep("power", x, y)).status == (
        Status.NOT_EVALUATED
    )
    assert (
        compare_sweeps(
            Sweep("power", x, y, response_unit="dB"),
            Sweep("power", x, y, np.ones(3), response_unit="linear"),
        ).status
        == Status.FAIL
    )
    assert (
        compare_sweeps(
            Sweep("power", x, np.array([1.0, np.nan, 1.0])),
            Sweep("power", x, y, np.ones(3)),
        ).status
        == Status.FAIL
    )


def test_frequency_shift_diagnosis():
    result = resonance_frequency_shift(6e9, 5.973e9)
    assert result["shift_hz"] == -27e6
    assert "permittivity" in str(result["likely_cause"])


def test_quantum_domains_formulas_and_limits():
    critical_current = 1e-6
    assert josephson_energy(critical_current) == pytest.approx(
        critical_current * PHI0 / (2 * math.pi)
    )
    assert transmon_frequency(1.0, 100.0) > 0
    assert squid_effective_ej(10.0, 0.0, math.pi) == pytest.approx(0.0, abs=1e-14)
    assert tls_q(0.0, 1e-3) == float("inf")
    assert cooperativity(0.0, 1.0, 1.0) == 0
    with pytest.raises(ValueError):
        transmon_frequency(-1.0, 100.0)
    with pytest.raises(ValueError):
        tls_q(float("nan"), 1e-3)


def test_yield_is_deterministic_and_reports_sampling_error():
    def predicate(point):
        return point["width"] > 0.9

    first = monte_carlo_yield({"width": 1.0}, {"width": 0.01}, predicate, 100, 7)
    second = monte_carlo_yield({"width": 1.0}, {"width": 0.01}, predicate, 100, 7)
    assert first == second and first["samples"] == 100
    assert "standard_error" in first


def test_surrogate_inverse_design():
    x = np.array([[0.0], [1.0], [2.0]])
    model = LinearSurrogate.fit(x, np.array([1.0, 3.0, 5.0]))
    candidate, prediction = model.inverse_design(x, 4.9)
    assert candidate.tolist() == [2.0]
    assert float(prediction) == pytest.approx(5.0)


def test_manifest_rejects_traversal_bad_hash_and_changed_file(tmp_path):
    with pytest.raises(ValueError):
        FieldEvidence(
            quantity="E",
            path="../secret",
            units="V/m",
            normalization="relative",
        )
    artifact = tmp_path / "field.h5"
    artifact.write_bytes(b"field")
    digest = hashlib.sha256(b"field").hexdigest()
    manifest = SimulationManifest(
        run_id="run",
        solver=SolverRecord(name="palace", adapter="portable-palace"),
        physics=PhysicsRecord(),
        fields=[
            FieldEvidence(
                quantity="E",
                path="field.h5",
                units="V/m",
                normalization="relative",
            )
        ],
        files={"field.h5": digest},
    )
    (tmp_path / "simulation-manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    assert ADAPTERS["palace"].import_bundle(tmp_path).run_id == "run"
    artifact.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        ADAPTERS["palace"].import_bundle(tmp_path)
    raw = manifest.model_dump(mode="json")
    raw["files"] = {"field.h5": "bad"}
    with pytest.raises(ValueError):
        SimulationManifest.model_validate(raw)


def test_job_rendering_quotes_shell_expansion(tmp_path):
    render_job(
        JobSpec(
            name="safe",
            command=["solver", "$(touch pwned)", "a'b"],
            backend="slurm",
            environment={"CASE_NAME": "$(touch env-pwned)"},
        ),
        tmp_path,
    )
    script = (tmp_path / "submit.sh").read_text(encoding="utf-8")
    assert "'$(touch pwned)'" in script
    assert "'$(touch env-pwned)'" in script
    assert (tmp_path / "job.json").is_file()
