# QResAudit v2 platform

The v2 portable layer is deliberately solver-independent. `SimulationManifest` records
the solver and adapter, physics domains, mesh, E/H/J/B field evidence, materials,
boundaries, conventions, capabilities, per-capability evidence states, file hashes,
and provenance. The seven adapters accept portable directories or a
`simulation-manifest.json`; they do not parse proprietary solver databases and never
synthesize missing results. Discovered portable files are `WARNING` until their
semantics are validated, while absent evidence is `NOT_EVALUATED`.

`diagnose()` is deterministic and local. Its query helper labels reports as rule-based,
and every finding is `PASS`, `WARNING`, `FAIL`, or `NOT_EVALUATED`. Measurement sweeps,
quantum estimates, fabrication yield, surrogates, job artifacts, benchmarks, and paper
packages are likewise usable without a solver or network connection. Quantum
estimates state their approximation regime; digital-twin comparisons require aligned
axes and propagate supplied measurement uncertainty; generated HPC/cloud artifacts
never submit automatically.

## Research engines

- `qresaudit.quantum`: Josephson, transmon, SQUID, dispersive, TLS, and
  cooperativity estimates.
- `qresaudit.measurement`: VNA or parameter-sweep comparison, calibration offsets,
  and simulation-to-measurement resonance shifts.
- `qresaudit.fabrication`: seeded Monte Carlo yield with binomial sampling error.
- `qresaudit.dataset`: local linear surrogates and candidate-set inverse design.
- `qresaudit.jobs`: local dry-run, Slurm, AWS Batch, and generic cluster artifacts.
- `qresaudit.reproducibility`: integrity-addressed methods and supplementary package.
- `qresaudit.benchmark`: explicit-tolerance analytic, cross-solver, or experiment
  comparisons.

These modules complement the existing convergence, resonator fitting, mode tracking,
field normalization, participation, spin-resonator, Pareto, and Palace functionality.

The existing `qresaudit_hfss` package remains the licensed boundary. A capability in
the portable API is not solver-validated scientific evidence.
