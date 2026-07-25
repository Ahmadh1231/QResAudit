# HFSS workflow

1. Solve the project in a licensed AEDT environment.
2. Export with `qresaudit-hfss` using a reviewed YAML configuration.
3. Preserve the project hash, AEDT/PyAEDT versions, setup, sweep, convergence,
   mesh, network, and field provenance.
4. Copy the portable bundle to an independent machine.
5. Run `qresaudit validate`, `qresaudit analyze`, and `qresaudit report`.
6. Compare the reported numerical values against a separately recorded HFSS
   result and sign the manual review record.

A skipped licensed test is not evidence. Synthetic fixtures prove software
behavior only. The exact acceptance contract for publishable reference data is
in `examples/golden/CONTRACT.md`.

The exporter must not be run against an unsaved or still-solving project.
Student-license restrictions and AEDT lifecycle requirements are documented in
the HFSS integration tests and exporter help.
