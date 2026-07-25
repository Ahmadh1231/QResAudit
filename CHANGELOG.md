# Changelog

## Unreleased

- Added a frozen local-only API for validation, loading, resonator analysis, and reports.
- Replaced magnitude/implicit-complex fitting with bounded complex least squares.
- Corrected field energy to distinguish peak-phasor (1/4) and RMS (1/2) conventions.
- Corrected adjacent-sweep mode matching and complex interpolation.
- Added analytical physics/property benchmarks, stable CLI commands, MkDocs documentation,
  experimental namespace boundaries, and a formal real-HFSS golden evidence contract.
- Added release-gated PyPI Trusted Publishing with OIDC, tag/version validation,
  distribution metadata checks, and a clean-wheel smoke test.
- Fixed the wheel smoke test to install declared dependencies without leaking host
  site-packages through `PYTHONPATH`.

## 2.0.0 - 2026-07-25

- Added solver-independent manifests and portable adapters for seven simulation ecosystems.
- Added deterministic diagnosis, measurement comparison, quantum estimates, fabrication yield,
  local surrogates, reproducibility packages, offline job artifacts, and benchmarks.
- Preserved explicit missing-evidence and solver-provenance boundaries.

## 0.1.1 - 2026-07-23

- Stabilized read-only AEDT lifecycle handling and offline bundle validation.
- Added explicit field context and HDF5 topology metadata contracts.
- Public CI proves formatting, typing, packaging, and offline tests on Ubuntu and Windows.
- No real HFSS/AEDT solve or physical-validity claim is included.

## 0.1.0 - 2026-07-23

- Initial schema-first HFSS bundle exporter and offline validator.
