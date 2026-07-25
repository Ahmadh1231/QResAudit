"""Budgeted resumable simulation state machine with approval and validation gates."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATES = (
    "GENERATE",
    "WAITING_FOR_APPROVAL",
    "SUBMIT",
    "VALIDATE",
    "ANALYZE",
    "OPTIMIZE",
    "COMPLETE",
    "FAILED",
)


@dataclass
class LoopState:
    state: str = "GENERATE"
    iteration: int = 0
    budget: int = 1
    failures: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.state not in STATES or self.budget < 0 or self.iteration < 0:
            raise ValueError("invalid loop state")


class SimulationLoop:
    def __init__(self, checkpoint: Path, *, budget: int = 1, allow_external: bool = False) -> None:
        self.checkpoint = checkpoint
        self.allow_external = allow_external
        self.state = self.load() if checkpoint.exists() else LoopState(budget=budget)

    def load(self) -> LoopState:
        raw = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        return LoopState(**raw)

    def save(self) -> None:
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint.write_text(
            json.dumps(asdict(self.state), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def dry_run_step(
        self, *, approved: bool | None = None, evidence_validated: bool | None = None
    ) -> LoopState:
        if self.state.state == "GENERATE":
            self.state.state = "WAITING_FOR_APPROVAL"
        elif self.state.state == "WAITING_FOR_APPROVAL":
            if approved is False:
                self.state.state = "FAILED"
                self.state.failures.append("solver execution was denied")
            elif approved and self.allow_external:
                self.state.state = "SUBMIT"
            else:
                self.state.state = "WAITING_FOR_APPROVAL"
        elif self.state.state == "SUBMIT":
            self.state.state = "VALIDATE"
        elif self.state.state == "VALIDATE":
            if evidence_validated:
                self.state.state = "ANALYZE"
            elif evidence_validated is False:
                self.state.state = "FAILED"
                self.state.failures.append("solver evidence failed validation")
        elif self.state.state == "ANALYZE":
            self.state.state = "OPTIMIZE"
        elif self.state.state == "OPTIMIZE":
            self.state.iteration += 1
            self.state.budget -= 1
            self.state.state = "COMPLETE" if self.state.budget <= 0 else "GENERATE"
        self.save()
        return self.state
