from pathlib import Path

from qresaudit.junit import junit_failure_summary


def test_junit_failure_summary_reports_failed_test(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuite><testcase classname="tests.test_example" name="test_failure">'
        '<failure message="expected 1">traceback</failure>'
        "</testcase></testsuite>",
        encoding="utf-8",
    )

    summary = junit_failure_summary(junit)

    assert "tests.test_example::test_failure" in summary
    assert "expected 1" in summary
