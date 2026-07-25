from __future__ import annotations

import json
import shutil
from pathlib import Path

from qresaudit.analysis.compare import compare_bundles

ROOT = Path(__file__).resolve().parents[2]


def _copy_bundle(tmp_path: Path, name: str) -> Path:
    source = ROOT / "testdata" / "synthetic" / "valid_eigenmode_minimal"
    destination = tmp_path / name
    shutil.copytree(source, destination)
    return destination


def _set_variation(bundle: Path, values: dict[str, str]) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variation"] = {
        key: {"expression": value}
        for key, value in values.items()
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_compare_includes_portable_variation_changes(tmp_path: Path) -> None:
    bundle_a = _copy_bundle(tmp_path, "a")
    bundle_b = _copy_bundle(tmp_path, "b")
    _set_variation(bundle_a, {"substrate_um": "300", "air_um": "600"})
    _set_variation(bundle_b, {"substrate_um": "700", "air_um": "600"})

    result = compare_bundles(bundle_a, bundle_b)
    assert result.variable_differences == ["substrate_um: 300 vs 700"]
    assert result.classification == "CONFIGURATION_DIFFERENCE"


def test_compare_reports_one_sided_variation(tmp_path: Path) -> None:
    bundle_a = _copy_bundle(tmp_path, "a")
    bundle_b = _copy_bundle(tmp_path, "b")
    _set_variation(bundle_a, {"airbridge_count": "0"})
    _set_variation(bundle_b, {"airbridge_count": "0", "sheet_inductance": "1pH"})

    result = compare_bundles(bundle_a, bundle_b)
    assert result.variable_differences == ["sheet_inductance: <missing> vs 1pH"]
