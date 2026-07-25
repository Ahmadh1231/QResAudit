"""Rule-based natural-language design requirements and explicit planning."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DesignRequirements:
    prompt: str
    target_frequency_hz: float | None
    spin_species: str | None
    objectives: tuple[str, ...]
    unknown_requirements: tuple[str, ...]


@dataclass(frozen=True)
class DesignPlan:
    requirements: DesignRequirements
    geometry: dict[str, object]
    simulation_steps: tuple[str, ...]
    optimization_steps: tuple[str, ...]
    evidence_status: str = "NOT_EVALUATED"


def parse_design_requirements(prompt: str) -> DesignRequirements:
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*GHz", prompt, re.I)
    species = re.search(r"\b(Er|Yb|Eu|Ce|rare[- ]earth)\b", prompt, re.I)
    objectives = ("spin coupling",) if "spin" in prompt.casefold() else ("resonance frequency",)
    unknown = (
        "substrate and permittivity",
        "fabrication limits",
        "loss/Q target",
        "geometry footprint",
        "solver evidence",
    )
    return DesignRequirements(
        prompt,
        float(match.group(1)) * 1e9 if match else None,
        species.group(1) if species else None,
        objectives,
        unknown,
    )


def plan_design(prompt: str) -> DesignPlan:
    req = parse_design_requirements(prompt)
    geometry: dict[str, object] = {
        "family": "quarter-wave CPW",
        "frequency_hz": req.target_frequency_hz,
        "portable": True,
    }
    return DesignPlan(
        req,
        geometry,
        (
            "define SI-unit geometry",
            "validate fabrication constraints",
            "request solver only after approval",
            "validate evidence",
            "analyze resonance and Q",
        ),
        (
            "seed candidate design",
            "fit surrogate after validated results",
            "select uncertainty-aware candidates",
        ),
    )
