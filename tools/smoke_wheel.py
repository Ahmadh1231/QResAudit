"""Install the built wheel into a clean virtual environment and smoke the CLIs."""

import os
import site
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from qresaudit import __version__


def main() -> None:
    wheels = sorted((Path(__file__).parents[1] / "dist").glob(f"qresaudit-{__version__}-*.whl"))
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
                "--no-deps",
                str(wheels[0]),
            ],
            check=True,
        )
        suffix = ".exe" if sys.platform == "win32" else ""
        command_environment = os.environ.copy()
        command_environment["PYTHONPATH"] = os.pathsep.join(site.getsitepackages())
        for command in ("qresaudit", "qresaudit-hfss"):
            subprocess.run(
                [str(scripts / f"{command}{suffix}"), "--version"],
                check=True,
                cwd=environment,
                env=command_environment,
            )


if __name__ == "__main__":
    main()
