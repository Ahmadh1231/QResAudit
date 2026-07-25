"""Portable, solver-independent simulation evidence and analysis."""

__version__ = "2.0.0"

from qresaudit.agent import DesignAgentTools, RuleBasedDesignAgent, ToolResult
from qresaudit.analysis.optimization import GaussianProcessPrediction, GaussianProcessSurrogate
from qresaudit.digital_twin import CalibrationResult, calibrate_resonator
from qresaudit.geometry import CPWDesign, FabricationConstraints, make_cpw_design
from qresaudit.knowledge import KnowledgeBase, KnowledgeRecord
from qresaudit.loop import LoopState, SimulationLoop
from qresaudit.multiphysics import Perturbation
from qresaudit.planner import DesignPlan, DesignRequirements, parse_design_requirements, plan_design
from qresaudit.report import DesignReport, build_design_report, write_design_report
from qresaudit.robust import RobustResult, correlated_robust_analysis
from qresaudit.v2 import Finding, SimulationManifest, diagnose

__all__ = [
    "CPWDesign",
    "CalibrationResult",
    "DesignAgentTools",
    "DesignPlan",
    "DesignReport",
    "DesignRequirements",
    "FabricationConstraints",
    "Finding",
    "GaussianProcessPrediction",
    "GaussianProcessSurrogate",
    "KnowledgeBase",
    "KnowledgeRecord",
    "LoopState",
    "Perturbation",
    "RobustResult",
    "RuleBasedDesignAgent",
    "SimulationLoop",
    "SimulationManifest",
    "ToolResult",
    "__version__",
    "build_design_report",
    "calibrate_resonator",
    "correlated_robust_analysis",
    "diagnose",
    "make_cpw_design",
    "parse_design_requirements",
    "plan_design",
    "write_design_report",
]
