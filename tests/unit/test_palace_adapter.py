import json
from pathlib import Path

from qresaudit.io.bundle import load_manifest
from qresaudit.palace.adapter import convert_palace_run
from qresaudit.validation.engine import validate_bundle


def test_eigenmode_conversion_is_self_contained_and_valid(tmp_path: Path) -> None:
    source = tmp_path / "palace-output"
    source.mkdir()
    (source / "config.json").write_text(
        json.dumps({"Problem": {"Type": "Eigenmode"}}),
        encoding="utf-8",
    )
    (source / "eigenmode.csv").write_text(
        "m,Freq. (Hz),Loss (Hz),Q\n1,6.0e9,100,30000000\n",
        encoding="utf-8",
    )
    output = tmp_path / "bundle"

    convert_palace_run(source, output)

    manifest = load_manifest(output / "manifest.json")
    assert manifest.evidence_profile.value == "minimal"
    assert manifest.fields == []
    assert manifest.project_file_sha256
    assert (output / "provenance" / "palace_config.json").is_file()
    assert (output / "modes" / "raw_eigenmode.csv").is_file()
    assert validate_bundle(output, strict=True).valid


def test_raw_vtu_is_preserved_without_false_field_metadata(tmp_path: Path) -> None:
    source = tmp_path / "palace-output"
    (source / "postpro").mkdir(parents=True)
    (source / "config.json").write_text("{}", encoding="utf-8")
    (source / "eigenmode.csv").write_text(
        "m,Freq. (Hz),Loss (Hz),Q\n1,6.0e9,100,30000000\n",
        encoding="utf-8",
    )
    (source / "postpro" / "e_field.vtu").write_text("<VTKFile/>", encoding="utf-8")
    output = tmp_path / "bundle"

    convert_palace_run(source, output)

    manifest = load_manifest(output / "manifest.json")
    assert manifest.fields == []
    assert manifest.bundle_status.value == "complete_with_warnings"
    assert manifest.diagnostics[0].code == "PALACE_FIELDS_RAW_ONLY"
    assert (output / "fields" / "raw" / "e_field.vtu").is_file()
