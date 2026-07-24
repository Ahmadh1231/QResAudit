import re
from pathlib import Path
from typing import Any

from qresaudit.models.common import Diagnostic, warning
from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import FileRecord
from qresaudit_hfss.adapters.common import file_record


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "report"


def export_existing_reports(
    app: Any,
    config: ExportConfig,
    available_reports: list[str],
    staging: Path,
) -> tuple[list[FileRecord], list[dict[str, str]], list[Diagnostic]]:
    """Export existing report definitions without creating or modifying reports."""
    if not config.export_existing_reports:
        return [], [], []
    selected = config.report_names or available_reports
    records: list[FileRecord] = []
    index: list[dict[str, str]] = []
    diagnostics: list[Diagnostic] = []
    output_dir = staging / "reports" / "existing"
    output_dir.mkdir(parents=True, exist_ok=True)
    for report_name in selected:
        if report_name not in available_reports:
            diagnostics.append(
                warning(
                    "EXPORT_REPORT_NOT_FOUND",
                    f"Configured report does not exist: {report_name}",
                )
            )
            continue
        before = set(output_dir.glob("*.csv"))
        try:
            result = app.post.export_report_to_csv(str(output_dir), report_name)
            after = set(output_dir.glob("*.csv"))
            created = sorted(after - before)
            if isinstance(result, str) and Path(result).is_file():
                exported = Path(result)
            elif created:
                exported = created[-1]
            else:
                expected = output_dir / f"{report_name}.csv"
                if not expected.is_file():
                    raise RuntimeError("PyAEDT did not return or create a CSV")
                exported = expected
            canonical = output_dir / f"{_safe_name(report_name)}.csv"
            if exported != canonical:
                exported.replace(canonical)
            records.append(file_record(canonical, staging, "existing_report", False))
            index.append(
                {
                    "name": report_name,
                    "path": canonical.relative_to(staging).as_posix(),
                }
            )
        except Exception as exc:
            diagnostics.append(
                warning(
                    "EXPORT_REPORT_FAILED",
                    f"Could not export existing report {report_name}: {exc}",
                )
            )
    return records, index, diagnostics
