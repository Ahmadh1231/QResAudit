"""Palace solver adapter — prove audit framework is solver-independent.

Palace (https://github.com/awslabs/palace) is an open-source 3D
finite-element electromagnetic solver. This adapter maps Palace
outputs into the same canonical bundle format used by the HFSS adapter,
enabling solver-independent comparison and audit.

Target: v0.4.0
"""

from qresaudit.palace.adapter import PalaceAdapter, convert_palace_run

__all__ = ["PalaceAdapter", "convert_palace_run"]
