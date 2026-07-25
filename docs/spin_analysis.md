# Spin-resonator analysis

Spin coupling is experimental and requires an explicit evidence contract. The
sample YAML must provide:

```yaml
sample_region_name: SpinSample
total_field_region_name: FullDomain
cavity_q_loaded: 100000
spin_density_per_m3: 1.0e23
spin_number: 0.5
temperature_k: 0.05
static_b_field_t: [0.0, 0.0, 0.2]
```

Both regions need structured field exports from the same solution, variation,
normalization, and phasor convention. The total region needs paired E and H data;
the sample region needs H data. QResAudit normalizes the total mode to zero-point
energy, applies the same scale to the sample field, integrates the actual sample
volume, and uses the supplied loaded Q.

The implemented thermal-polarization equation is the two-level spin-1/2 model.
Other spins are rejected until an explicit Brillouin or level-Hamiltonian model is
selected. Missing fields, Q, sample region, grid volume, or linewidth evidence
produce errors rather than zero-valued results.
