import os
import sys
from pathlib import Path

from qresaudit.junit import junit_failure_summary


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: summarize_junit.py PATH", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"JUnit file is unavailable: {path}", file=sys.stderr)
        return 0
    summary = junit_failure_summary(path)
    print(summary)
    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with Path(github_summary).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
