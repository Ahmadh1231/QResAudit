"""The packaged deterministic benchmark suite must remain green."""

from qresaudit.benchmarks import run_benchmarks


def test_local_benchmark_suite_passes() -> None:
    result = run_benchmarks()

    assert result["passed"], result
    assert "no solver validation" in result["scope"]
