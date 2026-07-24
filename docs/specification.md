# QResAudit 0.1 implementation contract

This implementation is derived from `QResAudit_HFSS_Implementation_Specification.pdf`
(version 1.0, 23 July 2026). The PDF remains the normative product specification.

## Definition of done

A driven and an eigenmode HFSS fixture can be inspected and exported with one command.
The resulting canonical bundles validate on a machine without AEDT. Every published
file is covered by SHA-256 integrity data, raw vendor exports are preserved, units and
field normalization are explicit, and failures cannot publish a complete-looking
directory.

## Trust boundary

`qresaudit_hfss` may import PyAEDT and call documented export APIs. `qresaudit` must
remain importable and usable without PyAEDT. The exporter treats HFSS as the numerical
source but cross-checks file labels, ports, solution context, variation, field shape,
units, and normalization.

## Supported result contracts

- Driven Modal/Terminal: Touchstone, complex canonical S CSV, convergence, mesh
  statistics, profile, variables, and at least one complex H field.
- Eigenmode: mode frequency and HFSS unloaded-Q table, convergence, mesh statistics,
  profile, variables, and complex E/H fields for each selected mode.
- Fields: coordinates in metres; E in V/m; H in A/m; complex128 components and derived
  magnitude in HDF5.

HFSS eigenmode fields are labeled `hfss_eigenmode_peak_1`. They are relative fields
and must not be interpreted as per-photon V/m or A/m.

## Validation order

1. Filesystem and path safety.
2. Manifest schema.
3. File sizes and SHA-256 integrity.
4. JSON/YAML/CSV/Touchstone/HDF5 formats.
5. Solution-specific required evidence.
6. Ports, modes, shapes, units, solution context, normalization, and raw-source hashes.
7. Touchstone/canonical CSV agreement and policy checks.

Checksum mismatches, malformed files, unknown normalization, and contradictory
solution metadata are always errors, including permissive mode.
