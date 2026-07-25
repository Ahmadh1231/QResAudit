"""Install the built wheel into a clean virtual environment and smoke the CLIs."""

import os
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path


def main() -> None:
    repository = Path(__file__).parents[1]
    with (repository / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    wheels = sorted((repository / "dist").glob(f"qresaudit-{version}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel in dist, found {len(wheels)}")
    with tempfile.TemporaryDirectory(prefix="qresaudit-wheel-") as directory:
        environment = Path(directory)
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if sys.platform == "win32" else "bin")
        python = scripts / ("python.exe" if sys.platform == "win32" else "python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                str(wheels[0]),
            ],
            check=True,
        )
        suffix = ".exe" if sys.platform == "win32" else ""
        command_environment = os.environ.copy()
        command_environment.pop("PYTHONPATH", None)
        for command in ("qresaudit", "qresaudit-hfss"):
            subprocess.run(
                [str(scripts / f"{command}{suffix}"), "--version"],
                check=True,
                cwd=environment,
                env=command_environment,
            )
        subprocess.run(
            [
                str(python),
                "-c",
                (
                    "from importlib.resources import files; "
                    "from qresaudit.api import validate_bundle, load_bundle, "
                    "analyze_resonator, generate_report; "
                    "from qresaudit.benchmarks import run_benchmarks; "
                    "assert files('qresaudit').joinpath('py.typed').is_file(); "
                    "assert run_benchmarks()['passed']"
                ),
            ],
            check=True,
            cwd=environment,
            env=command_environment,
        )


if __name__ == "__main__":
    main()
