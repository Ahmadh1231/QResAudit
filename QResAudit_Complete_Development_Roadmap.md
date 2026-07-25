# QResAudit Development Roadmap

## Executive summary

QResAudit is an open-source scientific-software project for converting Ansys HFSS simulation outputs into portable, machine-readable, cryptographically verifiable evidence bundles, then auditing and analyzing those bundles without requiring Ansys AEDT.

Its strongest purpose is:

> **Make electromagnetic simulation outputs portable, reproducible, auditable, and suitable for downstream scientific analysis.**

The initial implementation was produced in approximately one day using Codex CLI and Claude Code. That demonstrates unusually high implementation velocity for repository scaffolding, schemas, CLI development, tests, CI, HDF5 handling, and documentation. Later phases will still slow down because the bottleneck shifts from writing code to proving scientific correctness.

The main constraints will be:

- verifying actual HFSS and PyAEDT behavior;
- running licensed integration tests;
- constructing real golden datasets;
- checking numerical conventions and formulas;
- validating field normalization, participation, and mode tracking;
- reviewing generated code for silent scientific errors;
- maintaining compatibility across solver versions.

## Revised schedule

Assuming daily focused work, reliable HFSS access, Codex as primary implementer, and Claude Code as independent reviewer:

| Milestone | Aggressive estimate | Conservative estimate |
|---|---:|---:|
| Stabilized Phase 1 release | 2–5 days | 1–2 weeks |
| Phase 2 core analysis | 1–3 weeks | 1–2 months |
| Public research-software release | 2–4 weeks | 2–3 months |
| Palace adapter | 1–3 weeks | 1–2 months |
| Spin-resonator module | 2–4 weeks | 1–3 months |
| Optimization framework | 2–5 weeks | 2–4 months |
| Credible `v1.0` | 2–4 months | 6–12 months |

The first day was fast because AI coding agents are highly effective at repository construction, typed models, tests, packaging, and documentation. They provide less acceleration for scientific validation, licensed solver behavior, and numerical correctness.

---

# 1. Project definition

## 1.1 Core problem

HFSS results are often difficult to reproduce because:

- the original `.aedt` project is unavailable;
- the recipient lacks an Ansys license;
- solver settings are distributed across screenshots, notebooks, reports, and files;
- field plots use arbitrary normalization;
- convergence evidence is incomplete;
- Touchstone files omit context;
- port definitions and renormalization choices are unclear;
- field data lose coordinate topology;
- solver versions change output behavior;
- final numerical values are preserved without the evidence supporting them.

QResAudit should convert a solved HFSS design into a portable bundle containing enough evidence to audit what was exported and how it should be interpreted.

## 1.2 Architecture

### Licensed boundary: `qresaudit_hfss`

Responsibilities:

- open an existing HFSS project safely;
- inspect existing solved data;
- export networks, fields, convergence, mesh, and provenance;
- avoid solving or modifying the model;
- close only resources owned by QResAudit;
- convert vendor-specific outputs into canonical files.

### Portable core: `qresaudit`

Responsibilities:

- validate bundles;
- parse canonical files;
- verify checksums;
- check schema consistency;
- analyze convergence;
- fit resonators;
- normalize fields;
- calculate participation;
- track modes;
- compare runs;
- generate reports.

The portable core must work without AEDT or PyAEDT.

## 1.3 Value proposition

> QResAudit converts proprietary HFSS outputs into portable scientific evidence and applies reproducible validation and analysis without requiring access to Ansys.

This is stronger than describing it as an HFSS automation package or Q-factor fitter.

---

# 2. Current status and release blockers

## 2.1 Existing capabilities

The repository already contains:

- separate portable and HFSS namespaces;
- typed Python packaging;
- Pydantic schemas;
- command-line tooling;
- Touchstone support;
- HDF5 field support;
- manifest generation;
- cryptographic checksums;
- validation logic;
- synthetic fixtures;
- unit and offline-integration tests;
- GitHub Actions;
- licensed HFSS test structure;
- contribution and security documentation;
- evidence-profile concepts;
- safe staging and publication logic.

## 2.2 Current blockers

Before Phase 2:

1. Public CI must pass on Ubuntu and Windows.
2. Version metadata must be consistent.
3. Licensed HFSS workflow must pass.
4. A real Driven Modal bundle must be published.
5. A real Eigenmode bundle must be published.
6. Structured-grid coordinate ordering must be verified.
7. Structured HDF5 axis metadata must be correct.
8. Touchstone version and metadata must be parsed rather than assumed.
9. Tested AEDT/PyAEDT compatibility must be documented.
10. A tagged release must be published.

> Do not build advanced analysis on top of an unproven export contract.

---

# 3. Phase 0 — Repository foundation

## Purpose

Create a maintainable Python scientific-software repository.

## Scope

- `src/` package layout;
- portable and HFSS packages;
- tests, examples, schemas, and documentation;
- `pyproject.toml`;
- linting, formatting, and type checking;
- unit and offline integration tests;
- package-build tests;
- GitHub Actions;
- contributor and security policies;
- repository-specific agent instructions.

## Status

Mostly complete.

## Remaining work

- make CI green;
- add version-consistency tests;
- correct inaccurate documentation claims;
- update GitHub Actions dependencies;
- add minimum workflow permissions;
- publish test results;
- make Markdown the normative specification;
- generate the PDF from Markdown.

## Release gate

```bash
ruff check .
ruff format --check .
mypy src
python tools/check_schemas.py
pytest tests/unit tests/offline_integration
python -m build
```

All checks must pass on Ubuntu and Windows.

## Revised estimate

1–3 days.

---

# 4. Phase 1 — HFSS evidence export

## Target

`v0.1.1`

## Purpose

Export a solved HFSS design into a portable bundle that validates without AEDT.

## Solution types

### Driven Modal

Export:

- Touchstone network;
- S-parameter reports;
- port metadata;
- reference impedances;
- renormalization metadata;
- explicit field frequency;
- excitation amplitude and phase;
- field data;
- convergence evidence;
- mesh statistics;
- design and variation provenance.

### Driven Terminal

Initially experimental. Additional provenance must include:

- terminal names;
- reference conductors;
- differential definitions;
- terminal ordering;
- terminal impedance;
- terminal-to-network mapping.

### Eigenmode

Export:

- mode number;
- real and imaginary frequency where available;
- solver-reported unloaded Q where available;
- selected variation;
- adaptive-pass convergence;
- electric and magnetic fields;
- field representation;
- arbitrary-amplitude normalization status;
- mesh evidence;
- project provenance.

## Canonical bundle

```text
hfss_run/
├── manifest.json
├── checksums.sha256
├── export_config.yaml
├── variables/
│   ├── project_variables.json
│   ├── design_variables.json
│   └── solved_variation.json
├── network/
│   ├── network.s2p
│   └── network.csv
├── modes/
│   └── eigenmodes.csv
├── convergence/
│   ├── adaptive_passes.csv
│   └── raw/
├── mesh/
│   ├── mesh_summary.csv
│   └── raw/
├── fields/
│   ├── field_index.json
│   ├── mode_01_E.h5
│   └── mode_01_H.h5
├── reports/
├── logs/
└── validation.json
```

## Driven-field metadata

Every driven field must state:

- frequency;
- phase;
- setup and sweep;
- variation;
- excitation amplitudes and phases;
- coordinate system;
- field representation;
- units;
- phasor convention;
- peak or RMS convention;
- region assignment;
- grid topology;
- grid shape;
- axis order;
- flattening order.

## Eigenmode-field metadata

Every eigenmode field must state:

- mode number;
- frequency;
- arbitrary-amplitude status;
- real-gauge or complex-phasor representation;
- coordinate system;
- region;
- grid topology;
- shape;
- axis order;
- flattening order.

Real-valued eigenmodes must be supported when represented in a valid real gauge.

## Structured-grid contract

```json
{
  "topology": "structured",
  "coordinate_type": "Cartesian",
  "coordinate_system": "Global",
  "shape": [101, 101, 7],
  "axis_order": ["x", "y", "z"],
  "flattening_order": "C"
}
```

Recommended HDF5 layout:

```text
/coordinates/x
/coordinates/y
/coordinates/z
/coordinates/points
/field/real
/field/imag
/field/magnitude
```

The writer must prove that point ordering agrees with the declared grid order. Otherwise it must reorder the field data or preserve the export as unstructured.

## Touchstone contract

Record:

- version;
- parameter type;
- data format;
- frequency unit;
- port count and names;
- port-order verification;
- matrix format;
- source and exported reference impedance;
- renormalization;
- wave definition when known;
- mixed-mode ordering when present.

## Safety requirements

- Never create a missing project or design.
- Never solve automatically.
- Never remove a lock automatically.
- Never close an unowned AEDT desktop.
- Close only projects opened by QResAudit.
- Preserve the previous valid bundle if publication fails.
- Log cleanup failures without hiding the original exception.

## Real golden bundles

```text
testdata/golden/driven_modal_single_resonator/
testdata/golden/eigenmode_single_resonator/
```

Each must include:

- export configuration;
- manifest;
- checksums;
- canonical data;
- validation report;
- expected numerical ranges;
- screenshot;
- AEDT and PyAEDT versions;
- short model description.

## Completion criteria

1. Public CI green.
2. Licensed HFSS CI green.
3. Driven Modal export succeeds.
4. Eigenmode export succeeds.
5. Golden bundles validate offline.
6. Structured-grid round-trip is proven.
7. Touchstone provenance is preserved.
8. Version metadata agree.
9. `v0.1.1` is tagged and released.

## Revised estimate

3–10 days.

---

# 5. Phase 2 — HFSS analysis and audit

## Target

`v0.2.0`

## Purpose

Convert validated evidence bundles into quantitative scientific audits.

## 5.1 Schema 0.2 and migrations

Add:

- `GridRecord`;
- `FieldRepresentationRecord`;
- `ExcitationRecord`;
- `PortRecord`;
- `ReferenceImpedanceRecord`;
- `AdaptivePassRecord`;
- `MeshStatisticsRecord`;
- `MaterialRecord`;
- `BoundaryRecord`;
- `AnalysisRecord`;
- `DiagnosticRecord`.

Command:

```bash
qresaudit migrate BUNDLE --to-schema 0.2.0
```

Requirements:

- preserve the original;
- write a migration report;
- record source and destination schema;
- identify unmigratable fields;
- never invent missing metadata.

Estimate: 1–3 days aggressive.

## 5.2 Convergence auditing

Canonical adaptive-pass fields:

```text
pass
tetrahedra
frequency_hz
frequency_change_fraction
maximum_delta_s
converged
elapsed_time_s
peak_memory_bytes
solver_message
```

Analyze:

- final frequency change;
- final maximum delta S;
- mesh growth ratio;
- monotonicity;
- oscillation;
- stagnation;
- insufficient passes;
- requested versus achieved criterion;
- limiting-value extrapolation where justified;
- quantity-specific convergence;
- false convergence;
- mode identity across passes.

Command:

```bash
qresaudit convergence BUNDLE
```

Outputs:

```text
analysis/convergence.json
analysis/convergence.csv
analysis/convergence.png
```

Estimate: 2–5 days aggressive.

## 5.3 Resonator fitting

Support:

- notch transmission;
- peak transmission;
- reflection;
- resonance detection;
- cable-delay removal;
- complex backgrounds;
- loaded, coupling, and internal Q;
- covariance;
- bootstrap uncertainty;
- residual diagnostics;
- model comparison;
- optimizer-failure detection;
- overlapping-mode detection;
- inadequate-span and inadequate-sampling detection.

Command:

```bash
qresaudit fit BUNDLE --response S21 --model notch
```

Synthetic validation must include ideal, delayed, noisy, sloped-background, undercoupled, overcoupled, critically coupled, overlapping, under-sampled, and unstable cases.

Estimate: 3–7 days aggressive.

## 5.4 Eigenmode tracking

Use phase-invariant normalized field overlap:

\[
M_{ij}
=
rac{
\left|
\int \mathbf E_i^* \cdot oldsymbol{\epsilon}\mathbf E_j\,dV
ight|
}{
\sqrt{
\int \mathbf E_i^* \cdot oldsymbol{\epsilon}\mathbf E_i\,dV
\int \mathbf E_j^* \cdot oldsymbol{\epsilon}\mathbf E_j\,dV
}
}.
\]

Support:

- common-grid interpolation;
- global-phase removal;
- electric and magnetic overlap;
- frequency continuity;
- Hungarian assignment;
- confidence;
- mode swaps;
- crossings;
- avoided crossings;
- hybridization;
- user-defined mode-character regions.

Command:

```bash
qresaudit modes track SWEEP_DIRECTORY
```

Outputs:

```text
mode_branches.csv
overlap_matrices.h5
mode_assignments.json
avoided_crossings.json
mode_tracking.png
```

Estimate: 4–10 days aggressive.

## 5.5 Field integration and normalization

Support:

- Cartesian grids;
- cylindrical grids with Jacobian;
- spherical grids with Jacobian;
- unstructured data only with integration weights;
- region masks;
- electric and magnetic energy;
- peak and RMS fields;
- field percentiles;
- effective mode volume;
- filling factors;
- grid-resolution sensitivity.

Normalization:

\[
lpha =
\sqrt{
rac{U_{	ext{target}}}{U_{	ext{raw}}}
}.
\]

Explicit target-energy conventions:

- zero-point energy \(\hbar\omega/2\);
- one excitation above vacuum \(\hbar\omega\);
- total \(n\)-photon energy;
- user-defined classical energy.

Commands:

```bash
qresaudit fields inspect BUNDLE
qresaudit fields integrate BUNDLE --region SpinSample
qresaudit fields normalize BUNDLE --mode 1 --energy zero-point
```

Estimate: 4–10 days aggressive.

## 5.6 Participation and loss

Volume participation:

\[
p_k = rac{U_k}{U_{\mathrm{total}}}.
\]

Loss estimate:

\[
rac{1}{Q_{\mathrm{loss}}}
=
\sum_k p_k 	an\delta_k.
\]

Support:

- dielectric participation;
- magnetic filling factor;
- user-defined regions;
- domain coverage;
- missing-region warnings;
- sum checks;
- resolution sensitivity;
- uncertainty propagation.

Commands:

```bash
qresaudit participation BUNDLE --regions regions.yaml
qresaudit loss-estimate BUNDLE --materials materials.yaml
```

Surface participation must remain deferred until interface, layer-thickness, component-field, and surface-mesh contracts are rigorous.

Estimate: 3–7 days aggressive.

## 5.7 Bundle comparison

Command:

```bash
qresaudit compare RUN_A RUN_B
```

Compare:

- provenance;
- variables;
- software versions;
- mesh;
- convergence;
- resonant frequencies;
- Q values;
- S-parameters;
- mode identity;
- field overlap;
- integrated quantities;
- participation;
- diagnostics.

Classify differences as:

```text
NUMERICAL_DIFFERENCE
CONFIGURATION_DIFFERENCE
SOLVER_VERSION_DIFFERENCE
PHYSICAL_MODEL_DIFFERENCE
MISSING_EVIDENCE
```

Estimate: 1–4 days aggressive.

## 5.8 Automated audit report

Command:

```bash
qresaudit audit BUNDLE --output audit/
```

Output:

```text
audit/
├── audit.json
├── report.html
├── summary.md
├── diagnostics.csv
├── plots/
└── analysis/
```

Every result must be:

```text
PASS
WARNING
FAIL
NOT_EVALUATED
```

Missing evidence must never be treated as a pass.

Estimate: 2–5 days aggressive.

## Phase 2 completion criteria

1. Schema 0.2 documented.
2. Schema 0.1 migrates deterministically.
3. Convergence data canonicalized.
4. Real and complex eigenmodes supported.
5. Structured grids preserve topology.
6. Resonator fitting passes ground-truth tests.
7. Unreliable fits are rejected.
8. Mode tracking handles crossings.
9. Energy integration passes analytic tests.
10. Normalized fields reproduce target energy within tolerance.
11. Participation passes coverage checks.
12. Bundle comparison is reproducible.
13. HTML and JSON audit reports work.
14. Public and licensed CI are green.
15. Real golden fixtures are archived.
16. Offline core remains independent of PyAEDT.
17. `v0.2.0` is tagged and released.

Revised estimate: 2–4 weeks aggressive.

---

# 6. Phase 3 — Public research-software release

## Target

`v0.3.0`

## Scope

- stable Python API;
- stable CLI and exit codes;
- diagnostic-code catalogue;
- MkDocs or Sphinx documentation;
- API reference;
- tutorials and notebooks;
- PyPI publication;
- reproducible development environment;
- signed release artifacts;
- SBOM;
- `CITATION.cff`;
- Zenodo DOI;
- archive validation;
- semantic-versioning policy;
- migration and deprecation policy.

Estimate: 3–7 days aggressive.

---

# 7. Phase 4 — Palace support

## Target

`v0.4.0`

## Purpose

Prove that the audit framework is not permanently tied to HFSS.

## Scope

- Palace adapter;
- solver-independent manifest mapping;
- eigenmode import;
- driven-response import;
- field import;
- mesh import;
- convergence import;
- HFSS-versus-Palace comparison;
- matched reference models;
- solver-difference diagnostics.

Required deliverables:

- one matched eigenmode model;
- one matched driven model;
- documented convention differences;
- comparison report;
- expected numerical tolerances.

Estimate: 1–3 weeks aggressive.

---

# 8. Phase 5 — Spin-resonator physics

## Target

`v0.5.0`

## Scope

- magnetic filling factor;
- zero-point magnetic field;
- effective \(g\)-tensor;
- crystal orientation;
- single-spin coupling;
- ensemble coupling;
- thermal polarization;
- inhomogeneous linewidth;
- cavity and spin decay;
- cooperativity;
- strong-coupling criterion;
- placement sweeps;
- orientation sweeps;
- uncertainty propagation.

Example commands:

```bash
qresaudit spin analyze BUNDLE --ensemble erbium.yaml
qresaudit spin sweep BUNDLE --parameter orientation
```

Validation:

- analytic uniform-field case;
- published resonator case;
- orientation test;
- temperature-polarization test;
- sensitivity analysis;
- dimensional checks.

Estimate: 2–4 weeks aggressive.

---

# 9. Phase 6 — Design optimization

## Target

`v0.6.0`

## Scope

- sweep ingestion;
- objectives and constraints;
- Pareto analysis;
- surrogate models;
- Bayesian optimization;
- fabrication-tolerance analysis;
- optimization provenance;
- HFSS job orchestration;
- resume and recovery;
- cost-aware scheduling;
- candidate comparison.

Possible objectives:

- resonance-frequency error;
- magnetic field in sample;
- electric participation;
- spin coupling;
- cooperativity;
- internal and coupling Q;
- footprint;
- minimum feature size;
- fabrication sensitivity.

Optimization must remain downstream of validation.

Estimate: 2–5 weeks aggressive.

---

# 10. Phase 7 — Broader ecosystem

Potential additions:

- COMSOL;
- Elmer;
- openEMS;
- Sonnet;
- measured VNA data;
- cryogenic metadata;
- temperature and power sweeps;
- magnetic-field sweeps;
- TLS fitting;
- simulation-to-measurement comparison;
- plugin interface.

Implement adapters only when a real use case, maintainer, and validation fixture exist.

---

# 11. Stable `v1.0`

Requirements:

- stable schema, API, and CLI;
- migration support;
- at least two solver adapters;
- multiple real golden datasets;
- documented tolerances;
- tested compatibility matrix;
- external users and issue reports;
- at least one outside contribution;
- complete release policy;
- no known silent data-corruption paths;
- software paper or archived technical report.

Estimate: 2–4 months aggressive, 6–12 months conservative.

---

# 12. Codex and Claude Code workflow

## Codex CLI

Use as primary implementer for:

- issue implementation;
- tests;
- CI repair;
- refactoring;
- migrations;
- CLI commands;
- packaging;
- release automation;
- local review.

## Claude Code

Use as independent reviewer for:

- scientific assumptions;
- numerical formulas;
- edge cases;
- adversarial fixtures;
- API boundaries;
- documentation claims;
- failure modes;
- security review.

## Branch discipline

Do not let both agents edit the same branch.

```text
main
├── codex/issue-042-structured-grid-order
├── claude/review-issue-042
└── integration/issue-042
```

## Procedure

1. Create one narrowly scoped issue.
2. Define acceptance criteria.
3. Codex implements.
4. Run local checks.
5. Claude reviews the diff and tests.
6. Separate real defects from preferences.
7. Codex addresses verified findings.
8. Run Linux and Windows tests.
9. Run HFSS tests for licensed-boundary changes.
10. Merge through pull request.
11. Delete worktree.
12. Begin next issue.

## Agent instruction files

### `AGENTS.md`

Include:

- project purpose;
- architecture;
- package boundaries;
- test commands;
- scientific invariants;
- prohibited shortcuts;
- release gates;
- style and documentation rules.

### `CLAUDE.md`

Include:

- review responsibilities;
- scientific-review checklist;
- adversarial-test expectations;
- distinction between code and physical correctness;
- uncertainty reporting;
- prohibition against unsupported claims.

### Suggested Claude subagents

```text
hfss-api-reviewer.md
schema-reviewer.md
numerical-method-reviewer.md
test-adversary.md
security-reviewer.md
release-reviewer.md
```

---

# 13. Development rules

## Never weaken validation to pass CI

Do not:

- remove Ubuntu;
- lower coverage merely to pass;
- skip scientific tests;
- add unjustified platform-specific `xfail`;
- weaken assertions;
- suppress parser failures;
- replace missing values with zero;
- silently coerce invalid data.

## Every numerical feature needs ground truth

Use at least one:

- analytic solution;
- synthetic generated data;
- independent implementation;
- published reference;
- solver comparison;
- measurement;
- dimensional analysis;
- limiting-case behavior.

## Every conclusion needs a state

```text
PASS
WARNING
FAIL
NOT_EVALUATED
```

## Every convention must be explicit

Examples:

- peak versus RMS;
- \(e^{+i\omega t}\) versus \(e^{-i\omega t}\);
- zero-point versus one-excitation energy;
- source versus renormalized impedance;
- coordinate system;
- unit system;
- real gauge versus complex phasor;
- structured versus unstructured grid;
- mode normalization;
- surface versus volume quantity.

---

# 14. Testing strategy

## Unit tests

Cover:

- schemas;
- unit conversion;
- checksum parsing;
- HDF5 layout;
- Touchstone metadata;
- grid ordering;
- migrations;
- diagnostic codes;
- numerical formulas.

## Property-based tests

Cover:

- monotonic and malformed frequency axes;
- random grid dimensions;
- checksum duplicates;
- path traversal;
- finite and nonfinite values;
- unit consistency;
- shape consistency;
- serialization round trips.

## Offline integration tests

Cover:

- valid Driven and Eigenmode bundles;
- corrupted checksums;
- missing evidence;
- undeclared files;
- bad HDF5 shapes;
- invalid field metadata;
- malformed Touchstone data;
- migrations;
- report generation.

## Licensed integration tests

Cover:

- real Driven Modal export;
- real Eigenmode export;
- existing desktop survival;
- missing project and design rejection;
- project ownership;
- field, convergence, and mesh export;
- offline validation of real bundles.

## Numerical fixtures

```text
ideal_notch
delayed_notch
noisy_notch
overlapping_resonances
real_eigenmode
complex_eigenmode
mode_crossing
avoided_crossing
structured_cartesian_field
cylindrical_field
spherical_field
malformed_grid
nonconvergent_frequency
false_convergence
```

---

# 15. Release strategy

## `v0.1.1`

Evidence export:

- green public CI;
- green licensed CI;
- real Driven and Eigenmode bundles;
- consistent versions;
- wheel, source distribution, and checksums.

## `v0.2.0`

HFSS analysis:

- convergence;
- resonator fitting;
- mode tracking;
- field integration;
- normalization;
- participation;
- comparison;
- audit reports.

## `v0.3.0`

Public research package:

- documentation;
- PyPI;
- citation metadata;
- SBOM;
- DOI;
- stable policies.

## `v0.4.0`

Palace.

## `v0.5.0`

Spin-resonator physics.

## `v0.6.0`

Optimization.

## `v1.0`

Stable externally validated scientific package.

---

# 16. Impact and CV positioning

## Impact potential

### Current stage

Already a strong résumé project because it demonstrates:

- scientific Python;
- HFSS and PyAEDT;
- architecture;
- schemas;
- HDF5;
- Touchstone;
- CI;
- testing;
- provenance;
- validation;
- reproducibility.

Scientific impact remains limited until real HFSS outputs and licensed tests are public.

### After Phase 1

Potentially one of the strongest projects on the CV because it becomes demonstrably reproducible and release-ready.

### After Phase 2

Potentially useful to:

- superconducting-circuit groups;
- quantum-device groups;
- spin-resonance groups;
- detector groups;
- microwave engineers;
- cryogenic measurement teams.

### After external adoption

Publication-level indicators:

- outside users;
- external issues and pull requests;
- PyPI downloads;
- Zenodo DOI;
- citations;
- use in theses and papers;
- multiple solvers;
- external maintainers.

## CV entry — current

**QResAudit — Open-Source HFSS Validation Framework**  
*Python, PyAEDT, Pydantic, HDF5, scikit-rf, pytest, GitHub Actions*

- Developed a solver-independent evidence framework that exports HFSS network, field, convergence, mesh, and provenance data into portable, cryptographically verified bundles.
- Implemented validation for driven and eigenmode simulations, including explicit field frequency, field representation, structured-grid topology, per-port impedance records, and offline integrity checks.
- Designed separate licensed-HFSS and portable-core layers with typed schemas, CLI workflows, synthetic fixtures, cross-platform tests, and automated package builds.

## CV entry — after Phase 2

**QResAudit — Open-Source Electromagnetic Simulation Audit Platform**

- Built a portable audit framework for HFSS simulations, including resonator fitting, convergence diagnostics, eigenmode tracking, field-energy normalization, participation analysis, and reproducible reporting.
- Validated numerical outputs against synthetic ground truth, analytic field models, and real HFSS golden datasets across public and licensed CI environments.
- Published versioned schemas, reproducible evidence bundles, documentation, and release artifacts usable without an Ansys license.

## Claims to avoid until proven

Do not claim:

- used by researchers;
- production-ready;
- validated across multiple AEDT versions;
- published on PyPI;
- solver-agnostic;
- improved simulation accuracy;
- participation analysis;
- resonator fitting;
- Palace support;
- external contributors.

---

# 17. Immediate aggressive execution schedule

## Days 1–2

- diagnose Ubuntu failure;
- make CI green;
- synchronize version metadata;
- correct documentation;
- update GitHub Actions;
- add result reporting.

## Days 2–4

- repair structured-grid ordering;
- add grid-order tests;
- correct HDF5 axis metadata;
- parse Touchstone version;
- add Touchstone tests.

## Days 3–7

- run licensed HFSS tests;
- fix PyAEDT incompatibilities;
- export real Driven and Eigenmode bundles;
- publish compatibility table.

## Days 5–10

- release `v0.1.1`;
- begin schema 0.2;
- implement convergence parser;
- implement first audit report.

## Week 2

- resonator fitting;
- convergence analysis;
- bundle comparison;
- HTML report.

## Week 3

- field integration;
- normalization;
- participation;
- analytic validation.

## Week 4

- mode tracking;
- real sweep fixture;
- release `v0.2.0`;
- documentation and PyPI preparation.

This schedule is aggressive but plausible if HFSS access is reliable and every generated change is reviewed.

---

# 18. Final assessment

The one-day implementation speed proves that QResAudit can progress much faster than a conventional solo scientific-software project.

Revised expectations:

- Phase 1 stabilization: days;
- Phase 2 implementation: weeks;
- public research package: one to two months;
- broader solver and spin-resonator platform: several months;
- stable `v1.0`: potentially two to four months with sustained AI-assisted development.

The limiting factor is scientific verification, not code generation.

The project should optimize for:

1. evidence;
2. reproducibility;
3. explicit conventions;
4. real solver validation;
5. narrow releases;
6. independent review;
7. external usability.

A smaller, fully validated `v0.2.0` is more valuable than a larger nominal `v1.0` containing unverified analysis.
