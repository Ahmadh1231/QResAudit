"""Generate the public, solver-free quarter-wave CPW resonator demo.

The fixture is intentionally analytic and synthetic. It demonstrates the QResAudit
bundle workflow without claiming HFSS validation or publishing a research design.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qresaudit.hashing import run_id_for, sha256_file, write_checksums  # noqa: E402
from qresaudit.io.field_tab import ParsedField  # noqa: E402
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5  # noqa: E402
from qresaudit.models.common import (  # noqa: E402
    EvidenceProfile,
    ExportStatus,
    FieldRepresentation,
    NormalizationKind,
    PhasorConvention,
    SolutionKind,
)
from qresaudit.models.manifest import (  # noqa: E402
    FieldRecord,
    FileRecord,
    HFSSRunManifest,
    TouchstoneRecord,
)

DEMO = ROOT / "examples" / "demo_resonator"
BUNDLE = DEMO / "bundle"
F0_HZ = 6.0e9
Q_LOADED = 5_000.0
Q_COUPLING = 8_000.0
Q_INTERNAL = 1.0 / (1.0 / Q_LOADED - 1.0 / Q_COUPLING)
EPSILON_EFFECTIVE = 6.0
SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
RESONATOR_LENGTH_M = SPEED_OF_LIGHT_M_PER_S / (4.0 * F0_HZ * np.sqrt(EPSILON_EFFECTIVE))
GENERATED_BY = "tools/generate_demo_resonator.py"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_record(relative: str, role: str) -> FileRecord:
    path = BUNDLE / relative
    return FileRecord(
        path=relative,
        role=role,
        media_type=(
            "application/json"
            if path.suffix == ".json"
            else "text/csv"
            if path.suffix == ".csv"
            else "application/octet-stream"
        ),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        required=True,
        generated_by=GENERATED_BY,
    )


def _write_network() -> tuple[TouchstoneRecord, list[FileRecord]]:
    frequency_hz = np.linspace(F0_HZ - 30e6, F0_HZ + 30e6, 1201)
    detuning = 2.0 * Q_LOADED * (frequency_hz - F0_HZ) / F0_HZ
    s21 = 1.0 - (Q_LOADED / Q_COUPLING) / (1.0 + 1j * detuning)
    zeros = np.zeros_like(s21)

    touchstone = BUNDLE / "network" / "network.s2p"
    touchstone.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "! QResAudit analytic synthetic quarter-wave CPW demo",
        "! Port[1] = input",
        "! Port[2] = output",
        "# HZ S RI R 50",
    ]
    for frequency, s11, transmission, s12, s22 in zip(
        frequency_hz, zeros, s21, s21, zeros, strict=True
    ):
        lines.append(
            " ".join(
                f"{value:.17g}"
                for value in (
                    frequency,
                    s11.real,
                    s11.imag,
                    transmission.real,
                    transmission.imag,
                    s12.real,
                    s12.imag,
                    s22.real,
                    s22.imag,
                )
            )
        )
    touchstone.write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = BUNDLE / "reports" / "s_parameters.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.column_stack(
        (
            frequency_hz,
            zeros.real,
            zeros.imag,
            s21.real,
            s21.imag,
            s21.real,
            s21.imag,
            zeros.real,
            zeros.imag,
        )
    )
    np.savetxt(
        csv_path,
        matrix,
        delimiter=",",
        header=("frequency_hz,re_S1_1,im_S1_1,re_S1_2,im_S1_2,re_S2_1,im_S2_1,re_S2_2,im_S2_2"),
        comments="",
        fmt="%.17g",
    )

    metadata = TouchstoneRecord(
        path="network/network.s2p",
        number_of_ports=2,
        frequency_unit="Hz",
        parameter_type="S",
        data_format="RI",
        renormalized=False,
        reference_impedance_ohm=50.0,
        header_reference_impedance_ohm=50.0,
        touchstone_version="1.0",
        wave_definition="power",
        matrix_format="full",
        port_names=["input", "output"],
        source_excitation_names=["input", "output"],
        port_order_verified=True,
        frequency_min_hz=float(frequency_hz[0]),
        frequency_max_hz=float(frequency_hz[-1]),
        point_count=len(frequency_hz),
    )
    return metadata, [
        _file_record("network/network.s2p", "touchstone"),
        _file_record("reports/s_parameters.csv", "s_parameters"),
    ]


def _write_field(quantity: str) -> tuple[FieldRecord, list[FileRecord]]:
    x = np.linspace(-30e-6, 30e-6, 5)
    y = np.linspace(0.0, RESONATOR_LENGTH_M, 9)
    z = np.linspace(0.0, 0.5e-3, 3)
    mesh = np.meshgrid(x, y, z, indexing="ij")
    coordinates = np.column_stack([axis.ravel(order="C") for axis in mesh])

    transverse_profile = np.exp(-np.abs(coordinates[:, 0]) / 20e-6)
    vertical_profile = np.exp(-coordinates[:, 2] / 0.5e-3)
    phase = np.pi * coordinates[:, 1] / (2.0 * RESONATOR_LENGTH_M)
    values = np.zeros((len(coordinates), 3), dtype=np.complex128)
    if quantity == "E":
        values[:, 0] = 1_000.0 * np.sin(phase) * transverse_profile * vertical_profile
        units = "V/m"
    else:
        free_space_impedance_ohm = np.sqrt(4.0e-7 * np.pi / 8.8541878128e-12)
        values[:, 2] = (
            1_000.0
            / free_space_impedance_ohm
            * np.cos(phase)
            * transverse_profile
            * vertical_profile
        )
        units = "A/m"

    raw_relative = f"fields/raw/resonator_{quantity}.fld"
    raw_path = BUNDLE / raw_relative
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = [
        f"# analytic synthetic {quantity}-field",
        f"# units: {units}",
        "# x_m y_m z_m real_x imag_x real_y imag_y real_z imag_z",
    ]
    for coordinate, value in zip(coordinates, values, strict=True):
        raw_lines.append(
            " ".join(
                f"{item:.17g}"
                for item in (
                    *coordinate,
                    value[0].real,
                    value[0].imag,
                    value[1].real,
                    value[1].imag,
                    value[2].real,
                    value[2].imag,
                )
            )
        )
    raw_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    h5_relative = f"fields/hdf5/resonator_{quantity}.h5"
    h5_path = BUNDLE / h5_relative
    parsed = ParsedField(
        coordinates_m=coordinates,
        values=values,
        is_complex=True,
        is_vector=True,
        quantity=quantity,
        value_units=units,
        coordinate_units="m",
        source_header=tuple(raw_lines[:3]),
    )
    logical_shape = [len(x), len(y), len(z)]
    metadata = {
        "schema_version": "0.1.1",
        "grid_type": "Cartesian",
        "topology": "structured",
        "shape": logical_shape,
        "axes": {"x": x.tolist(), "y": y.tolist(), "z": z.tolist()},
        "axis_order": ["x", "y", "z"],
        "flattening_order": "C",
        "coordinate_system": "Global",
        "solution_reference": "AnalyticNotch : Sweep",
        "setup_name": "AnalyticNotch",
        "sweep_name": "Sweep",
        "frequency_hz": F0_HZ,
        "phase_deg": 0.0,
        "normalization": NormalizationKind.USER_SCALED.value,
        "region_name": "cpw_resonator_domain",
        "assignments_json": ["analytic_domain"],
        "representation": FieldRepresentation.COMPLEX_PHASOR.value,
        "phasor_convention": PhasorConvention.EXP_POSITIVE_IWT_PEAK.value,
        "excitation_context": {"name": "analytic_port_1", "amplitude": "1 arbitrary unit"},
        **source_metadata(raw_path),
    }
    write_field_hdf5(h5_path, parsed, metadata)

    record = FieldRecord(
        path=h5_relative,
        raw_path=raw_relative,
        quantity=quantity,
        complex_data=True,
        vector=True,
        units=units,
        coordinate_units="m",
        coordinate_system="Global",
        grid_type="Cartesian",
        region_name="cpw_resonator_domain",
        assignment=["analytic_domain"],
        object_type="Vol",
        solution="AnalyticNotch : Sweep",
        frequency_hz=F0_HZ,
        phase_deg=0.0,
        normalization=NormalizationKind.USER_SCALED,
        shape=[*logical_shape, 3],
        point_count=len(coordinates),
        excitation="analytic_port_1",
        representation=FieldRepresentation.COMPLEX_PHASOR,
        phasor_convention=PhasorConvention.EXP_POSITIVE_IWT_PEAK,
        component_labels=["x", "y", "z"],
        axis_order=["x", "y", "z"],
        flattening_order="C",
        topology="structured",
    )
    return record, [
        _file_record(raw_relative, "field_raw"),
        _file_record(h5_relative, "field_hdf5"),
    ]


def _write_supporting_evidence() -> list[FileRecord]:
    design = {
        "classification": "analytic synthetic demonstration; not solver validation",
        "device": "quarter-wave coplanar-waveguide resonator",
        "frequency_target_hz": F0_HZ,
        "effective_permittivity": EPSILON_EFFECTIVE,
        "center_conductor_width_m": 10e-6,
        "gap_m": 6e-6,
        "resonator_length_m": RESONATOR_LENGTH_M,
        "feedline_impedance_ohm": 50.0,
        "model": "lossy analytic notch response",
        "q_loaded": Q_LOADED,
        "q_coupling": Q_COUPLING,
        "q_internal": Q_INTERNAL,
    }
    _write_json(BUNDLE / "analytic_design.json", design)
    _write_json(
        BUNDLE / "design_variables.json",
        {
            "center_width": {"expression": "10 um", "evaluated_value": 10.0, "unit": "um"},
            "gap": {"expression": "6 um", "evaluated_value": 6.0, "unit": "um"},
            "length": {
                "expression": "c/(4*f0*sqrt(epsilon_eff))",
                "evaluated_value": RESONATOR_LENGTH_M,
                "unit": "m",
            },
        },
    )
    _write_json(BUNDLE / "project_variables.json", {})
    (BUNDLE / "export_config.resolved.yaml").write_text(
        "schema_version: 0.1.1\nevidence_profile: strict\nsource: analytic_synthetic_demo\n",
        encoding="utf-8",
    )

    convergence = BUNDLE / "convergence" / "adaptive_passes.csv"
    convergence.parent.mkdir(parents=True, exist_ok=True)
    convergence.write_text(
        "pass_number,frequency_hz,max_delta_s_percent,converged\n"
        "1,6008000000,0.5,false\n"
        "2,6003000000,0.2,false\n"
        "3,6001000000,0.08,false\n"
        "4,6000200000,0.0495,false\n"
        "5,6000000000,0.049,true\n",
        encoding="utf-8",
    )
    (BUNDLE / "convergence" / "convergence_raw.prof").write_text(
        "Analytic refinement demonstration\n"
        "Passes: 5\n"
        "Final delta metric: 0.049 percent\n"
        "Converged: true\n",
        encoding="utf-8",
    )
    (BUNDLE / "mesh" / "mesh.csv").parent.mkdir(parents=True, exist_ok=True)
    (BUNDLE / "mesh" / "mesh.csv").write_text(
        "pass_number,elements,minimum_quality\n"
        "1,8000,0.72\n"
        "2,11200,0.75\n"
        "3,15680,0.78\n"
        "4,21952,0.80\n"
        "5,30733,0.82\n",
        encoding="utf-8",
    )
    (BUNDLE / "convergence" / "mesh_stats_raw.txt").write_text(
        "Synthetic structured refinement record\nElements: 30733\nMinimum quality: 0.82\n",
        encoding="utf-8",
    )
    return [
        _file_record("analytic_design.json", "configuration"),
        _file_record("design_variables.json", "design_variables"),
        _file_record("project_variables.json", "project_variables"),
        _file_record("export_config.resolved.yaml", "configuration"),
        _file_record("convergence/adaptive_passes.csv", "convergence"),
        _file_record("convergence/convergence_raw.prof", "convergence"),
        _file_record("mesh/mesh.csv", "mesh"),
        _file_record("convergence/mesh_stats_raw.txt", "mesh_stats"),
    ]


def generate() -> None:
    resolved_demo = DEMO.resolve()
    resolved_examples = (ROOT / "examples").resolve()
    if resolved_demo.parent != resolved_examples:
        raise RuntimeError("refusing to replace a demo outside the repository examples directory")
    if DEMO.exists():
        shutil.rmtree(DEMO)
    BUNDLE.mkdir(parents=True)

    files = _write_supporting_evidence()
    touchstone, network_files = _write_network()
    files.extend(network_files)
    fields: list[FieldRecord] = []
    for quantity in ("E", "H"):
        field, field_files = _write_field(quantity)
        fields.append(field)
        files.extend(field_files)

    design_hash = sha256_file(BUNDLE / "analytic_design.json")
    manifest = HFSSRunManifest(
        schema_version="0.1.1",
        exporter_version="2.0.0",
        bundle_status=ExportStatus.COMPLETE,
        run_id=run_id_for(
            {
                "demo": "quarter_wave_cpw",
                "frequency_hz": F0_HZ,
                "q_loaded": Q_LOADED,
                "q_coupling": Q_COUPLING,
            }
        ),
        export_timestamp_utc=datetime(2026, 7, 27, tzinfo=UTC),
        project_name="qresaudit_public_demo",
        project_file_name="analytic_design.json",
        project_file_sha256=design_hash,
        design_name="SyntheticQuarterWaveCPW",
        design_type="analytic synthetic fixture",
        solution_kind=SolutionKind.DRIVEN_MODAL,
        setup_name="AnalyticNotch",
        sweep_name="Sweep",
        solution_reference="AnalyticNotch : Sweep",
        variation_id="nominal",
        variation={},
        evidence_profile=EvidenceProfile.STRICT,
        aedt_version="not used",
        pyaedt_version="not used",
        python_version="3.11+",
        operating_system="platform independent",
        model_units="m",
        reference_coordinate_system="Global",
        ports=["input", "output"],
        touchstone=touchstone,
        eigenmode=None,
        fields=fields,
        files=files,
        diagnostics=[],
    )
    _write_json(BUNDLE / "manifest.json", manifest.model_dump(mode="json"))
    write_checksums(BUNDLE)

    _write_json(
        DEMO / "expected_output.json",
        {
            "classification": "analytic synthetic demo; not HFSS or real-solver validation",
            "validation": {"strict": True, "expected_valid": True},
            "fit": {
                "model": "notch",
                "response": "S21",
                "frequency_hz": F0_HZ,
                "frequency_tolerance_fraction": 1e-5,
                "q_loaded": Q_LOADED,
                "q_loaded_tolerance_fraction": 0.01,
                "q_coupling": Q_COUPLING,
                "q_coupling_tolerance_fraction": 0.01,
                "q_internal": Q_INTERNAL,
                "q_internal_tolerance_fraction": 0.02,
            },
        },
    )
    (DEMO / "README.md").write_text(
        """# Synthetic quarter-wave CPW resonator demo

This is an original, solver-free demonstration created for QResAudit. It is not
an HFSS export, a measured device, a golden scientific benchmark, or evidence of
real-solver validation. No institutional or proprietary design data is included.

The model is a simple capacitively coupled quarter-wave coplanar-waveguide
resonator. Its length is calculated from
`c / (4 f0 sqrt(epsilon_effective))`. The Touchstone trace is generated from an
analytic notch response with declared `f0`, loaded Q, and coupling Q. The small
paired E/H grids are analytic standing-wave illustrations intended to exercise
field ingestion and report generation.

From the repository root:

```powershell
qresaudit validate examples/demo_resonator/bundle
qresaudit analyze examples/demo_resonator/bundle
qresaudit report examples/demo_resonator/bundle --output demo-report
```

Expected results and tolerances are recorded in `expected_output.json`. Rebuild
the entire deterministic fixture with:

```powershell
python tools/generate_demo_resonator.py
```

For real-solver validation requirements, see `examples/golden/CONTRACT.md`.
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
