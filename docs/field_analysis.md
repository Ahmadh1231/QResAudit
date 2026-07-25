# Field analysis

For peak-valued harmonic phasors, QResAudit computes time-average energies as

```text
U_E = 1/4 integral(epsilon |E|^2 dV)
U_H = 1/4 integral(mu |H|^2 dV)
```

For RMS phasors the factor is `1/2`. HFSS exports use the peak convention unless
the evidence explicitly records another convention.

Participation is `p_i = U_i / U_total`. The TLS-limited estimate is
`1/Q = sum(p_i * tan_delta_i)`. Missing interfaces or loss tangents must be
reported as missing evidence; they are never silently assigned a favorable value.

Field integration accuracy depends on the exported topology, units, material
assignment, and volume weights. Uniform-grid analytical tests exercise the
formula, while real golden bundles are required to validate the exporter and
solver-to-analysis chain.

Bundle-level volume integration accepts only a complete paired E/H context on a
three-dimensional structured Cartesian grid. QResAudit uses tensor-product
trapezoidal weights, including nonuniform axis spacing. It rejects unstructured
point clouds, planar grids with no declared thickness, unknown phasor conventions,
grid mismatches, and missing E/H partners instead of assuming a unit volume.
