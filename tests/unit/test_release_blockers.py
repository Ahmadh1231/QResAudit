import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import skrf as rf
from pydantic import ValidationError

from qresaudit.hashing import read_checksums
from qresaudit.io.bundle import atomic_staging
from qresaudit.io.touchstone import network_metadata
from qresaudit.models.config import ExportConfig
from qresaudit.validation import validate_bundle
from qresaudit_hfss.exports.reports import export_existing_reports
from qresaudit_hfss.provenance import evaluated_variables


def test_evidence_profiles_reject_contradictory_config() -> None:
    base = {
        "project": {"path": "project.aedt", "design": "D"},
        "solution": {"setup": "S"},
    }
    minimal = ExportConfig.model_validate(
        {
            **base,
            "evidence_profile": "minimal",
            "export_convergence": False,
            "export_mesh_stats": False,
        }
    )
    assert minimal.evidence_profile.value == "minimal"
    with pytest.raises(ValidationError, match="convergence"):
        ExportConfig.model_validate(
            {
                **base,
                "evidence_profile": "standard",
                "export_convergence": False,
            }
        )
    with pytest.raises(ValidationError, match="field exports"):
        ExportConfig.model_validate({**base, "evidence_profile": "strict"})


def test_duplicate_checksum_entry_is_rejected(tmp_path: Path) -> None:
    checksums = tmp_path / "checksums.sha256"
    digest = "0" * 64
    checksums.write_text(f"{digest}  data.csv\n{digest}  data.csv\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_checksums(checksums)


def test_unexpected_file_is_rejected(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "testdata" / "synthetic" / "valid_driven_minimal"
    bundle = tmp_path / "bundle"
    shutil.copytree(source, bundle)
    (bundle / "undeclared.bin").write_bytes(b"undeclared")
    result = validate_bundle(bundle)
    assert not result.valid
    assert "VALIDATION_UNEXPECTED_FILE" in {item.code for item in result.diagnostics}


def test_force_replacement_restores_previous_bundle_on_failed_final_validation(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")

    def reject(_: Path) -> None:
        raise RuntimeError("final validation failed")

    with (
        pytest.raises(RuntimeError, match="final validation"),
        atomic_staging(output, force=True, validate_final=reject) as staging,
    ):
        (staging / "new.txt").write_text("new", encoding="utf-8")

    assert (output / "old.txt").read_text(encoding="utf-8") == "old"
    assert not output.with_name("bundle.backup").exists()


def test_touchstone_preserves_complex_impedance_matrix() -> None:
    frequency = rf.Frequency.from_f([1.0, 2.0], unit="ghz")
    network = rf.Network(
        frequency=frequency,
        s=np.zeros((2, 2, 2), dtype=complex),
        z0=np.asarray([[50 + 1j, 75 + 2j], [51 + 3j, 76 + 4j]]),
    )
    metadata = network_metadata(network, "network.s2p", ["P1", "P2"])
    assert metadata["reference_impedance_real_ohm"] == [[50.0, 75.0], [51.0, 76.0]]
    assert metadata["reference_impedance_imag_ohm"] == [[1.0, 2.0], [3.0, 4.0]]


def test_evaluated_variables_label_declared_and_si_units() -> None:
    value = evaluated_variables({"gap": "1mm"})["gap"]
    assert value.evaluated_value == 0.001
    assert value.declared_unit == "mm"
    assert value.evaluated_unit == "m"
    assert value.evaluated_value_basis == "SI"


def test_report_names_cannot_collide(tmp_path: Path) -> None:
    class Post:
        def export_report_to_csv(self, directory: str, name: str) -> str:
            path = Path(directory) / f"{name}.csv"
            path.write_text("x\n1\n", encoding="utf-8")
            return str(path)

    config = SimpleNamespace(
        export_existing_reports=True,
        report_names=["A-B", "A B"],
    )
    _, index, diagnostics = export_existing_reports(
        SimpleNamespace(post=Post()),
        config,
        ["A-B", "A B"],
        tmp_path,
    )
    assert not diagnostics
    assert len({item["path"] for item in index}) == 2
    assert {item["id"] for item in index} == {"report_0001", "report_0002"}
