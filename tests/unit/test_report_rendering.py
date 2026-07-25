"""Report rendering must not execute evidence text as markup."""

from datetime import UTC, datetime

from qresaudit.analysis.audit import render_audit_html, render_audit_markdown
from qresaudit.models.v0_2 import AuditReport, AuditVerdict


def test_html_report_escapes_bundle_and_verdict_content() -> None:
    report = AuditReport(
        bundle_path="<script>alert(1)</script>",
        audit_timestamp_utc=datetime.now(UTC),
        verdicts=[
            AuditVerdict(
                section="<img src=x onerror=alert(1)>",
                check="safe",
                result="FAIL",
                detail="<script>alert(2)</script>",
            )
        ],
    )

    rendered = render_audit_html(report)

    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert" in rendered
    assert "<img src=x" not in rendered


def test_markdown_report_escapes_table_delimiters_and_newlines() -> None:
    report = AuditReport(
        bundle_path="bundle",
        audit_timestamp_utc=datetime.now(UTC),
        verdicts=[
            AuditVerdict(
                section="physics|fields",
                check="energy",
                result="WARNING",
                detail="line one\nline two",
            )
        ],
    )

    rendered = render_audit_markdown(report)

    assert "physics\\|fields" in rendered
    assert "line one line two" in rendered
