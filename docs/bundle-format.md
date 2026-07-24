# Bundle format 0.1

`manifest.json` is the authoritative index. All paths are POSIX-style and relative to
the bundle root. `checksums.sha256` covers every file except itself.

Typical paths:

```text
manifest.json
export_config.resolved.yaml
design_variables.json
project_variables.json
network/network.s2p
modes/eigenmodes.csv
convergence/convergence_raw.prof
convergence/mesh_stats_raw.txt
reports/s_parameters.csv
fields/raw/*.fld
fields/hdf5/*.h5
logs/export.jsonl
checksums.sha256
```

Each HDF5 field contains `coordinates/points`, `field/real`, `field/imag`,
`field/magnitude`, and attributes under `metadata`. The magnitude is derived and
revalidated from the complex values.
