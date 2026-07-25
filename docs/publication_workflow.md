# Publication workflow

A publishable QResAudit artifact should contain:

- the immutable evidence bundle and its SHA-256 inventory;
- export configuration and software/solver versions;
- convergence and mesh evidence;
- numerical acceptance ranges chosen before analysis;
- generated HTML, JSON, Markdown, and CSV reports;
- a manual comparison against the solver UI or independent calculation;
- limitations, missing evidence, and uncertainty;
- repository commit, release tag, citation metadata, and archival DOI.

Run:

```bash
qresaudit benchmark --output analytical-benchmarks.json
qresaudit validate bundle --strict
qresaudit report bundle --output publication-report
```

Then reproduce the same outputs on an independent machine without AEDT. A DOI is
added to `CITATION.cff` only after an archive such as Zenodo has actually minted
it. Collaborator and institutional examples are named only with their approval.
