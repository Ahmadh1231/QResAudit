import platform
import sys
from pathlib import Path
from typing import Any

from qresaudit.hashing import sha256_file
from qresaudit.models.manifest import VariationValue
from qresaudit.units import canonical_si_unit, parse_quantity


def evaluated_variables(values: dict[str, str]) -> dict[str, VariationValue]:
    result: dict[str, VariationValue] = {}
    for name, expression in values.items():
        try:
            evaluated, declared_unit = parse_quantity(expression)
            unit = canonical_si_unit(declared_unit)
        except ValueError:
            evaluated, unit, declared_unit = None, None, None
        result[name] = VariationValue(
            expression=expression,
            evaluated_value=evaluated,
            evaluated_unit=unit,
            declared_unit=declared_unit,
            evaluated_value_basis="SI" if evaluated is not None else None,
        )
    return result


def project_hash(path: Path) -> str:
    return sha256_file(path)


def runtime_provenance(app: Any) -> dict[str, str]:
    return {
        "aedt_version": str(getattr(app, "aedt_version_id", "unknown")),
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "python_executable": Path(sys.executable).name,
    }
