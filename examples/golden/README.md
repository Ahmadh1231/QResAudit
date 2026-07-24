# Real HFSS golden evidence gate

This directory intentionally contains no synthetic substitute for real HFSS evidence.

Release `v0.1.1` remains blocked until licensed CI publishes and independently checks:

- `driven_modal/` from a solved Driven Modal project;
- `eigenmode/` from a solved Eigenmode project.

Each directory must contain the validated bundle, resolved export configuration,
expected numerical ranges, AEDT/PyAEDT versions, a result screenshot, and an
independent manual-check record. A skipped licensed test does not satisfy this gate.
