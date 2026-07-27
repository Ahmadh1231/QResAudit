# Getting started

Install the package and run its deterministic checks:

```bash
python -m pip install qresaudit
qresaudit benchmark
qresaudit validate path/to/bundle
qresaudit analyze path/to/bundle
qresaudit report path/to/bundle --output report
```

The core package runs locally. It does not require or invoke an LLM. Validation
checks provenance and evidence completeness; it does not imply that the underlying
electromagnetic model is physically correct.

Python users should import the frozen surface from `qresaudit.api`:

```python
from qresaudit.api import generate_report, validate_bundle

result = validate_bundle("bundle")
if result.valid:
    report = generate_report("bundle", "report")
```

For HFSS export, install `qresaudit[hfss]` on the machine that has AEDT. Analysis
of the resulting bundle remains portable and offline.

## Run the public demo

The repository contains an original analytic quarter-wave CPW resonator fixture.
It is synthetic and solver-free, so it demonstrates the complete local workflow
without distributing a private design or making a real-HFSS validation claim.

```powershell
qresaudit validate examples/demo_resonator/bundle
qresaudit analyze examples/demo_resonator/bundle
qresaudit report examples/demo_resonator/bundle --output demo-report
```

The generated HTML report is `demo-report/report.html`. The declared analytic
targets and tolerances are in `examples/demo_resonator/expected_output.json`.
