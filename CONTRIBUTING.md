# Contributing

# Contributing

Install `.[dev,docs]`, then run:

```bash
ruff format --check .
ruff check .
mypy src
python -m validate_pyproject pyproject.toml
pytest
qresaudit benchmark
python -m pip_audit .
python -m bandit -r src -q -s B105,B110,B112
mkdocs build --strict
python -m build
python -m twine check dist/*
```

Core modules must never import PyAEDT, call an LLM, or require network access.
Licensed tests belong under `tests/hfss_integration`; analytical physics regressions
belong under `tests/physics`.

New public APIs need typing, documentation, tests, and an entry in `CHANGELOG.md`.
Only the names in `qresaudit.api` are frozen. Scientific changes must state units,
conventions, equations or references, acceptance thresholds, and limitations.
Real solver data must comply with `examples/golden/CONTRACT.md`.
