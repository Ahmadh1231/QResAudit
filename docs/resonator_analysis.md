# Resonator analysis

`qresaudit analyze BUNDLE` performs a complex least-squares fit of the selected
Touchstone response. The notch model is

```text
S21 = 1 - (Ql / |Qc|) / (1 + 2j Ql (f - f0) / f0)
```

with optional cable delay and complex linear background. The result reports
`f0`, loaded and coupling Q, inferred internal Q, residuals, and fit diagnostics.

The fit uses both real and imaginary data. Tests inject deterministic complex
noise into a known synthetic response and require frequency, loaded-Q, and
coupling-Q errors below 5%. This is an algorithm regression test, not an HFSS or
experimental validation.

Inspect residuals and frequency span before accepting a fit. Internal Q from a
notch assumes the implemented coupling model; impedance mismatch and asymmetric
line shapes require a more specialized model.
