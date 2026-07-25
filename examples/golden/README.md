# Real HFSS golden evidence gate

This directory intentionally contains no synthetic substitute for real HFSS evidence.

Research-grade validation remains blocked until licensed CI publishes and independently checks
the families defined in `CONTRACT.md`:

- `cpw_resonator/`;
- `idc_resonator/`;
- `spiral_resonator/`;
- `eigenmode_cavity/`.

Each directory must contain the validated bundle, resolved export configuration,
expected numerical ranges, AEDT/PyAEDT versions, a result screenshot, and an
independent manual-check record. A skipped licensed test does not satisfy this gate.
