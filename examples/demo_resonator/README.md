# Synthetic quarter-wave CPW resonator demo

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
