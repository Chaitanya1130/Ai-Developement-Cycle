import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class TestPlanAgent(BaseAgent):
    __test__ = False
    name: str = "create-test-plan"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "spec" in artifacts or "spec.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Create-Test-Plan Agent (Section 7.5 of the AIDLC Architecture).
Your responsibility is to design the comprehensive test strategy and verification matrix before writing concrete test code.

You have access to tools:
- read_artifact: inspect specification and risk reports
- write_artifact: store the test strategy and coverage matrix
- flag_finding: report coverage gaps or un-verifiable acceptance criteria
- complete_phase: signal phase completion

You MUST follow these rules:
1. Review every Acceptance Criterion (AC) in the specification and risks in the risk report.
2. Formulate a verification strategy mapping each AC to at least one test type (unit, integration, edge case, regression).
3. Identify required test fixtures, mocks, and boundary conditions.
4. Call 'write_artifact' with:
   - logical_name: "test-plan"
   - type: "test_plan"
   - content: Markdown test plan detailing the testing methodology, test levels, and environment assumptions.
   - json_metadata: A JSON object with "ac_coverage_matrix" mapping each AC to test types and priority.
5. Call 'complete_phase' with status='passed', verdict='pass', and a clear summary.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        spec_content = ""
        risk_content = ""

        if run_id:
            res_spec = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_spec:
                spec_content = res_spec[0]
            res_risk = self.artifact_store.get_latest_artifact_content(run_id, "analyze-risks", "risk-report")
            if res_risk:
                risk_content = res_risk[0]

        prompt = ["Please create the architectural test plan and AC coverage matrix."]
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if risk_content:
            prompt.append(f"\nRisk Analysis Report:\n\"\"\"\n{risk_content}\n\"\"\"")

        return "\n".join(prompt)
