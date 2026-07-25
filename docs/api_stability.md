# API stability

QResAudit 2.x has a deliberately small stable Python API:

```python
from qresaudit.api import (
    analyze_resonator,
    generate_report,
    load_bundle,
    validate_bundle,
)
```

These functions follow semantic versioning. Backward-incompatible signature or
behavior changes require a new major version. Compatible keyword additions and
new result fields may appear in minor releases.

## Stability levels

- **Stable:** names exported by `qresaudit.api` and the four convenience exports
  at the package root.
- **Supported module API:** schema, validation, reader, and analysis modules.
  These receive deprecation warnings for at least one minor release before removal.
- **Experimental:** names exposed through `qresaudit.experimental`. These may
  change in a minor release and must not be treated as frozen.
- **Internal:** `_internal` modules, when present. They have no compatibility promise.

Deprecations are recorded in `CHANGELOG.md`. Importing `qresaudit` never contacts
a solver, cloud service, or language model.
