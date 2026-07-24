from pathlib import Path
from typing import Any

from qresaudit.exceptions import ExportError
from qresaudit.models.config import ExportConfig


def export_touchstone(
    app: Any,
    config: ExportConfig,
    output_file: Path,
    *,
    renormalization: bool | None = None,
    impedance_ohm: float | None = None,
) -> Path:
    if not config.touchstone.enabled:
        raise ExportError("EXPORT_TOUCHSTONE_DISABLED_FOR_DRIVEN_SOLUTION")
    names = list(config.solution.variation)
    values = [config.solution.variation[name] for name in names]
    should_renormalize = (
        config.touchstone.renormalize if renormalization is None else renormalization
    )
    impedance = config.touchstone.impedance_ohm if renormalization is None else impedance_ohm
    result = app.export_touchstone(
        setup=config.solution.setup,
        sweep=config.solution.sweep,
        output_file=str(output_file),
        variations=names or None,
        variations_value=values or None,
        renormalization=should_renormalize,
        impedance=impedance,
        gamma_impedance_comments=config.touchstone.include_gamma_impedance_comments,
    )
    if not result:
        raise ExportError("EXPORT_TOUCHSTONE_FAILED")
    return Path(result)
