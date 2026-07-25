# Developer guide

Create a Python 3.11+ environment and install:

```bash
python -m pip install -e ".[dev,docs]"
ruff format --check .
ruff check .
mypy
pytest
qresaudit benchmark
python -m build
python -m twine check dist/*
```

New physics must include an equation or reference, declared units and phasor
convention, input validation, an analytical or synthetic regression test, an
acceptance threshold, and an explicit statement of what the test does not prove.

Keep stable entry points in `qresaudit.api`. Put developing research interfaces
under `qresaudit.experimental`, record user-visible changes in `CHANGELOG.md`,
and avoid network or LLM dependencies in the core package.

Real solver fixtures follow `examples/golden/CONTRACT.md`; never replace missing
licensed evidence with generated numbers.
