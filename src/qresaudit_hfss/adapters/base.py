from pathlib import Path
from typing import Any, Protocol

from qresaudit.models.common import Diagnostic, SolutionKind
from qresaudit.models.manifest import EigenmodeRecord, FieldRecord, FileRecord, TouchstoneRecord
from qresaudit_hfss.inspect import map_solution_kind


class HFSSAdapter(Protocol):
    def preflight(self) -> list[Diagnostic]: ...

    def export_primary_results(
        self, staging: Path
    ) -> tuple[list[FileRecord], TouchstoneRecord | None, EigenmodeRecord | None]: ...

    def export_evidence(self, staging: Path) -> list[FileRecord]: ...

    def export_fields(self, staging: Path) -> tuple[list[FileRecord], list[FieldRecord]]: ...


def adapter_for(app: Any, config: Any, capabilities: Any) -> HFSSAdapter:
    kind = map_solution_kind(str(app.solution_type))
    if kind in {SolutionKind.DRIVEN_MODAL, SolutionKind.DRIVEN_TERMINAL}:
        from qresaudit_hfss.adapters.driven import DrivenAdapter

        return DrivenAdapter(app, config, capabilities)
    if kind is SolutionKind.EIGENMODE:
        from qresaudit_hfss.adapters.eigenmode import EigenmodeAdapter

        return EigenmodeAdapter(app, config, capabilities)
    raise ValueError(f"HFSS_UNSUPPORTED_SOLUTION_TYPE: {app.solution_type}")
