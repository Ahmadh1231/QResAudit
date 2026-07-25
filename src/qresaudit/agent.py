"""Tool contract for honest local design agents."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    tool: str
    status: str
    data: dict[str, Any]
    claim: str


class DesignAgentTools(Protocol):
    def plan(self, prompt: str) -> ToolResult: ...
    def generate_candidates(self, plan: dict[str, Any]) -> ToolResult: ...
    def request_solver_job(self, design: dict[str, Any], approved: bool = False) -> ToolResult: ...
    def analyze_validated_evidence(self, evidence: dict[str, Any]) -> ToolResult: ...
    def optimize(self, evidence: dict[str, Any]) -> ToolResult: ...
    def report(self, records: list[dict[str, Any]]) -> ToolResult: ...


class RuleBasedDesignAgent:
    """Local deterministic implementation; it never claims an LLM ran."""

    def plan(self, prompt: str) -> ToolResult:
        from qresaudit.planner import plan_design

        return ToolResult(
            "plan",
            "ok",
            {"plan": plan_design(prompt).__dict__},
            "rule-based local planning; no LLM ran",
        )

    def generate_candidates(self, plan: dict[str, Any]) -> ToolResult:
        return ToolResult(
            "generate_candidates",
            "ok",
            {"candidates": [plan.get("geometry", {})]},
            "deterministic local candidate generation",
        )

    def request_solver_job(self, design: dict[str, Any], approved: bool = False) -> ToolResult:
        return ToolResult(
            "request_solver_job",
            "approved" if approved else "approval_required",
            {"design": design},
            "external execution disabled without explicit human approval",
        )

    def analyze_validated_evidence(self, evidence: dict[str, Any]) -> ToolResult:
        if evidence.get("status") != "PASS":
            return ToolResult(
                "analyze_validated_evidence", "blocked", {}, "analysis requires validated evidence"
            )
        return ToolResult(
            "analyze_validated_evidence",
            "ok",
            evidence,
            "analysis of caller-supplied validated evidence",
        )

    def optimize(self, evidence: dict[str, Any]) -> ToolResult:
        if evidence.get("status") != "PASS":
            return ToolResult(
                "optimize",
                "blocked",
                {},
                "optimization requires validated evidence",
            )
        return ToolResult(
            "optimize",
            "ready",
            {"evidence": evidence, "next": "fit surrogate and select candidate"},
            "validated evidence accepted; no solver or optimization was run",
        )

    def report(self, records: list[dict[str, Any]]) -> ToolResult:
        return ToolResult(
            "report", "ok", {"records": records}, "reproducible local report; no AI or solver claim"
        )
