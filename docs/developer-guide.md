# Developer guide

Keep vendor compatibility logic inside `qresaudit_hfss`. Detect PyAEDT capabilities
once and route through an adapter. Preserve exact raw exports before conversion.

Do not create reports in the user's project. Prefer direct solution data or existing
reports. Never remove locks unless the configuration explicitly says so. Student AEDT
does not support non-graphical batch mode.

When adding fields or schemas, update models, generated JSON schemas, bundle
documentation, valid fixtures, and corresponding corrupt fixtures together.
