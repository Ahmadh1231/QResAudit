# QResAudit v2

[![CI](https://github.com/Ahmadh1231/QResAudit/actions/workflows/core-ci.yml/badge.svg)](https://github.com/Ahmadh1231/QResAudit/actions/workflows/core-ci.yml)
[![Documentation](https://github.com/Ahmadh1231/QResAudit/actions/workflows/docs.yml/badge.svg)](https://github.com/Ahmadh1231/QResAudit/actions/workflows/docs.yml)

QResAudit turns electromagnetic simulation and measurement evidence into portable,
auditable research records. The HFSS evidence/export boundary remains the v1
foundation; real-solver validation claims remain separately gated. V2 adds
solver-neutral manifests and offline research engines for
diagnosis, design, digital twins, quantum-device estimates, fabrication variation,
surrogates, reproducibility packages, and execution artifacts.

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
qresaudit benchmark
qresaudit analyze path/to/real/bundle
qresaudit report path/to/real/bundle --output report
qresaudit show testdata/synthetic/valid_driven_minimal
qresaudit schema manifest
```

The supported Python surface is intentionally small:

```python
from qresaudit.api import analyze_resonator, generate_report, load_bundle, validate_bundle
```

QResAudit runs locally and does not call an LLM or hosted inference service.
See [`docs/api_stability.md`](docs/api_stability.md) for compatibility guarantees.
The source distribution contains no proprietary project, geometry, solved result, or
institutional design. Researchers provide their own evidence bundles locally.

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

## v2 capabilities and evidence boundary

The portable v2 core supports manifest-based imports for HFSS, Palace, COMSOL, CST,
Sonnet, openEMS, and Elmer; deterministic diagnosis; measurement comparison;
quantum-device estimates; fabrication yield; local surrogate and inverse-design
models; reproducibility packages; offline Slurm/AWS/cluster job artifacts; and
benchmarks. Adapters describe capabilities and missing evidence rather than
fabricating solver results. Tests do not contact solvers, cloud, or HPC systems.
Reports state when only local rules were used.

The master-roadmap research layer adds a Gaussian-process active-learning engine,
correlated fabrication uncertainty and yield analysis, portable parametric CPW
designs, experiment-backed digital-twin calibration, first-order multiphysics
perturbations, citation-preserving knowledge records, deterministic natural-language
planning, guarded agent tool contracts, resumable budgeted loops, and reproducible
design reports. These are portable research APIs; proprietary solver execution still
requires an explicit adapter, user approval, a license, and validated output evidence.
See [`docs/v4-platform.md`](docs/v4-platform.md).

## Limitations

QResAudit audits evidence; it does not prove a model is physically correct. Portable
adapters ingest exported files and manifests, not proprietary solver databases.
Quantum-circuit functions are documented analytic approximations, and surrogate
predictions are only as credible as their training evidence. Public CI proves offline
behavior and mocked lifecycle safety, not licensed HFSS or cross-solver validation.

## Testing

```powershell
ruff format --check .
ruff check .
mypy src
pytest tests/unit tests/offline_integration tests/physics --cov=qresaudit
qresaudit benchmark
```

## Publishing

Production packages are built and uploaded through secretless PyPI Trusted
Publishing when a GitHub Release is published. See
[`docs/releasing.md`](docs/releasing.md) for the protected-environment setup and
release checklist.

Licensed tests are marked `hfss` and run only on a private Windows runner with approved
fixture projects. The runner must configure `QRESAUDIT_HFSS_DRIVEN_CONFIG`,
`QRESAUDIT_HFSS_EIGENMODE_CONFIG`, and, for attachment safety,
`QRESAUDIT_HFSS_EXISTING_PROCESS_ID`. Missing configuration produces visible skips,
not passing evidence. No real golden bundle has been published yet, so a
research-grade solver-validation claim remains gated by
[`examples/golden/CONTRACT.md`](examples/golden/CONTRACT.md).
Package publication is not a claim that this independent evidence gate has passed.
