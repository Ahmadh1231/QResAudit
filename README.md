# QResAudit

[![CI](https://github.com/Ahmadh1231/QResAudit/actions/workflows/core-ci.yml/badge.svg)](https://github.com/Ahmadh1231/QResAudit/actions/workflows/core-ci.yml)

QResAudit exports solved Ansys HFSS evidence into a portable bundle and validates that
bundle without AEDT, PyAEDT, or an Ansys license. Version 0.1 targets HFSS 3D Driven
Modal and Eigenmode results. Driven Terminal export is intentionally disabled
until terminal/reference-conductor provenance is modeled. Version 0.1.1 is an
unreleased offline/schema stabilization candidate.

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

The package dependency currently permits PyAEDT 1.3.x, but no AEDT/PyAEDT pair is
claimed compatible until its licensed matrix passes. AEDT Student must run
graphically; set `student_version: true` and `non_graphical: false`.

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
replace an existing bundle; replacement keeps a recoverable backup until final
validation succeeds. Use `keep_failed: true` to retain failed staging data.

The default session starts and owns a new AEDT desktop. Attaching is opt-in through
`project.attach_process_id`. QResAudit never closes an attached AEDT desktop and closes
only projects that it opened during the current export session. Projects that were
already loaded remain open. Lock removal is forbidden.

Evidence requirements are explicit:

- `minimal`: primary network or eigenmode evidence;
- `standard`: primary evidence plus convergence and mesh statistics;
- `strict`: standard evidence plus fields required by the solution contract.

## Limitations

QResAudit audits evidence; it does not prove the model is physically correct. Version
0.1.1 intentionally excludes Q fitting, participation ratios, photon normalization,
spin coupling, dashboards, and non-HFSS solvers. Real-gauge eigenmode fields are
accepted; driven fields require explicit frequency and excitation context. Public CI
proves offline behavior and mocked lifecycle safety, not real HFSS validation.

## Testing

```powershell
ruff check .
mypy src
pytest tests/unit tests/offline_integration --cov=qresaudit
```

Licensed tests are marked `hfss` and run only on a private Windows runner with approved
fixture projects. The runner must configure `QRESAUDIT_HFSS_DRIVEN_CONFIG`,
`QRESAUDIT_HFSS_EIGENMODE_CONFIG`, and, for attachment safety,
`QRESAUDIT_HFSS_EXISTING_PROCESS_ID`. Missing configuration produces visible skips,
not passing evidence. No real golden bundle has been published yet, so `v0.1.1`
remains gated and Phase 2 remains deferred.
