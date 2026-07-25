# Real-solver golden evidence contract

The four named reference families are `cpw_resonator`, `idc_resonator`,
`spiral_resonator`, and `eigenmode_cavity`. A family is publishable only when it
contains all of the following:

```text
bundle/manifest.json
bundle/network/*.s2p          # driven simulations, when applicable
bundle/fields/E.h5
bundle/fields/H.h5
bundle/mesh/mesh.csv
bundle/convergence/passes.csv
expected_results.json
README.md
manual_review.json
```

`expected_results.json` must record measured values, units, tolerances, solver
version, project SHA-256, bundle inventory SHA-256, and the reviewer. Acceptance
ranges must come from the solved project or an analytical reference; they cannot
be copied from QResAudit's own output.

The gate passes only if strict bundle validation succeeds, all declared numerical
ranges pass, the manual comparison is signed and dated, and an independent
machine reproduces the report. Synthetic data never satisfies this contract.

The inventory hash is the SHA-256 of `bundle/checksums.sha256`. The manual review
record must contain `status: "PASS"`, `reviewer`, `reviewed_at_utc`,
`independent_machine`, and `metrics_verified: true`. Run
`python tools/check_golden.py --require-complete` for a release that claims
real-solver validation.
