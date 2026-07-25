"""Offline job specifications and submission artifacts."""

import json
import re
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path

SUPPORTED_BACKENDS = {"local-dry-run", "slurm", "aws-batch", "cluster"}


@dataclass(frozen=True)
class JobSpec:
    name: str
    command: list[str]
    backend: str = "local-dry-run"
    resources: dict[str, str | int | float] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"unsupported backend: {self.backend}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.name) or not self.command:
            raise ValueError("job name or command is invalid")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in self.environment):
            raise ValueError("environment variable name is invalid")


def render_job(spec: JobSpec, output: Path) -> Path:
    """Render artifacts only; this function never submits a job."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "job.json").write_text(
        json.dumps(asdict(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    quoted = shlex.join(spec.command)
    environment = "".join(
        f"export {key}={shlex.quote(value)}\n" for key, value in sorted(spec.environment.items())
    )
    if spec.backend == "slurm":
        script = (
            "#!/bin/bash\nset -eu\n"
            f"#SBATCH --job-name={spec.name}\n"
            f"#SBATCH --cpus-per-task={spec.resources.get('cpus', 1)}\n"
            f"{environment}"
            f"{quoted}\n"
        )
    else:
        script = (
            f"# dry-run artifact for {spec.backend}; no submission performed\n"
            f"{environment}{quoted}\n"
        )
    (output / "submit.sh").write_text(script, encoding="utf-8")
    return output
