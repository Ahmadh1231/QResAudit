import xml.etree.ElementTree as ET
from pathlib import Path


def junit_failure_summary(path: Path) -> str:
    root = ET.parse(path).getroot()
    failures: list[str] = []
    for case in root.iter("testcase"):
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            continue
        node = case.get("classname", "")
        name = case.get("name", "unknown")
        detail = (problem.get("message") or problem.text or "no failure detail").strip()
        failures.append(f"- `{node}::{name}`: {detail}")
    if not failures:
        return "## Pytest failure summary\n\nNo failed test cases were recorded in JUnit XML.\n"
    return "## Pytest failure summary\n\n" + "\n".join(failures) + "\n"
