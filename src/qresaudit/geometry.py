"""Portable parameterized CPW/resonator design specifications."""

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FabricationConstraints:
    min_linewidth_m: float = 1e-7
    min_gap_m: float = 1e-7
    max_aspect_ratio: float = 10.0

    def validate(self) -> None:
        if self.min_linewidth_m <= 0 or self.min_gap_m <= 0 or self.max_aspect_ratio <= 0:
            raise ValueError("fabrication limits must be positive")


@dataclass(frozen=True)
class CPWDesign:
    name: str
    frequency_hz: float
    center_width_m: float
    gap_m: float
    resonator_length_m: float
    substrate_thickness_m: float
    coupling_gap_m: float
    constraints: FabricationConstraints = FabricationConstraints()

    def validate(self) -> None:
        self.constraints.validate()
        vals = (
            self.frequency_hz,
            self.center_width_m,
            self.gap_m,
            self.resonator_length_m,
            self.substrate_thickness_m,
            self.coupling_gap_m,
        )
        if not all(math.isfinite(v) and v > 0 for v in vals):
            raise ValueError("physical design parameters must be finite and positive")
        if (
            self.center_width_m < self.constraints.min_linewidth_m
            or self.gap_m < self.constraints.min_gap_m
            or self.coupling_gap_m < self.constraints.min_gap_m
        ):
            raise ValueError("design violates fabrication minimums")

    def portable_spec(self) -> dict[str, object]:
        self.validate()
        return {"format": "qresaudit.portable-design.v1", "units": "SI", **asdict(self)}


def make_cpw_design(
    name: str,
    frequency_hz: float,
    *,
    center_width_m: float = 10e-6,
    gap_m: float = 6e-6,
    effective_permittivity: float = 6.0,
    **kwargs: object,
) -> CPWDesign:
    if frequency_hz <= 0 or effective_permittivity <= 0:
        raise ValueError("frequency and permittivity must be positive")
    length = 299792458.0 / (4 * frequency_hz * math.sqrt(effective_permittivity))
    substrate_thickness = kwargs.pop("substrate_thickness_m", 500e-6)
    coupling_gap = kwargs.pop("coupling_gap_m", gap_m)
    constraints = kwargs.pop("constraints", FabricationConstraints())
    if not isinstance(substrate_thickness, int | float):
        raise TypeError("substrate_thickness_m must be numeric")
    if not isinstance(coupling_gap, int | float):
        raise TypeError("coupling_gap_m must be numeric")
    if not isinstance(constraints, FabricationConstraints):
        raise TypeError("constraints must be FabricationConstraints")
    design = CPWDesign(
        name,
        frequency_hz,
        center_width_m,
        gap_m,
        length,
        float(substrate_thickness),
        float(coupling_gap),
        constraints,
    )
    if kwargs:
        raise ValueError(f"unknown design parameters: {sorted(kwargs)}")
    design.validate()
    return design


def write_portable_spec(design: CPWDesign, path: str) -> None:
    Path(path).write_text(
        json.dumps(design.portable_spec(), indent=2, sort_keys=True, default=lambda x: asdict(x))
        + "\n",
        encoding="utf-8",
    )
