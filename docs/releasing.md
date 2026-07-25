# Publishing QResAudit to PyPI

QResAudit publishes from GitHub Releases through PyPI Trusted Publishing. The
workflow does not use a long-lived PyPI API token.

## One-time repository setup

1. Create a GitHub environment named `pypi`.
2. Require a reviewer for that environment so every production upload needs approval.
3. In the PyPI project settings, add a GitHub Trusted Publisher with:
   - owner: `Ahmadh1231`
   - repository: `QResAudit`
   - workflow: `publish-pypi.yml`
   - environment: `pypi`

For a first publication where the `qresaudit` project does not yet exist on PyPI,
configure a pending publisher from the PyPI account publishing page using the same
values.

## Release procedure

1. Update `project.version` in `pyproject.toml`, `qresaudit.__version__`,
   `CITATION.cff`, and the changelog.
2. Run the complete release gates documented in `README.md`.
3. Confirm the **Release validation** workflow passes.
4. Create and push a tag matching the version, for example `v2.0.1`.
5. Publish a GitHub Release for that tag.
6. Approve the protected `pypi` environment deployment.

The workflow checks that the release tag exactly matches `project.version`, builds a
wheel and source distribution, validates their metadata, installs the wheel in a
clean environment, and only then grants the separate publish job an OIDC token.
The final upload workflow name is **Publish to PyPI**.

`python tools/check_golden.py` reports the independent scientific evidence status.
Use `--require-complete` only for a release that claims real-solver validation;
ordinary package publication must still describe an incomplete golden gate honestly.
