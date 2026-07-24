# QResAudit

QResAudit exports solved Ansys HFSS evidence into a portable bundle and validates that
bundle without AEDT, PyAEDT, or an Ansys license. Version 0.1 supports HFSS 3D Driven
Modal, experimental Driven Terminal, and Eigenmode results.

## Architecture

- `qresaudit` is the portable core: schemas, checksums, Touchstone/CSV/HDF5 readers,
  semantic validation, and CLI.
- `qresaudit_hfss` is the licensed boundary: read-only project inspection and
  documented PyAEDT export calls.
- A completed bundle contains raw vendor exports, canonical tables/HDF5, provenance,
  a manifest, and checksums.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

For a compatible AEDT/PyAEDT environment:

```powershell
.\.venv\Scripts\python -m pip install -e ".[hfss]"
```

PyAEDT 1.3.x is the initial supported API family. AEDT Student must run graphically;
set `student_version: true` and `non_graphical: false`.

## Quick start

Validate a portable bundle:

```powershell
qresaudit validate testdata/synthetic/valid_driven_minimal
qresaudit show testdata/synthetic/valid_driven_minimal
qresaudit schema manifest
```

Inspect and export a solved project:

```powershell
qresaudit-hfss inspect resonator.aedt --design Resonator --json
qresaudit-hfss export resonator.aedt --config examples/driven_export.yaml --output exports/run
```

The exporter never solves or modifies geometry, setups, ports, boundaries, or materials.
It stages to `OUTPUT.partial`, validates, and publishes atomically. Use `--force` to
replace an existing bundle and `keep_failed: true` to retain failed staging data.

## Limitations

QResAudit audits evidence; it does not prove the model is physically correct. Version
0.1 intentionally excludes Q fitting, participation ratios, photon normalization,
spin coupling, dashboards, and non-HFSS solvers. Complex fields must be genuinely
complex; a single phase-evaluated real field is rejected.

## Testing

```powershell
ruff check .
mypy src
pytest tests/unit tests/offline_integration --cov=qresaudit
```

Licensed tests are marked `hfss` and run only on a private Windows runner with approved
fixture projects.
