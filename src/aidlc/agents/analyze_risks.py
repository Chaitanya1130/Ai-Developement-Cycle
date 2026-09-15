import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class AnalyzeRisksAgent(BaseAgent):
    name: str = "analyze-risks"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "spec" in artifacts or "spec.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Analyze-Risks Agent (Section 7.4 of the AIDLC Architecture).
Your responsibility is to attack the engineering specification before any code is written, acting as a multi-lens red team.

You have access to tools:
- read_artifact: retrieve previous artifacts (spec, intake, interview)
- write_artifact: store the risk assessment report and risk register
- flag_finding: report blockers, ambiguities, security issues, or edge cases
- complete_phase: signal phase completion

You MUST evaluate the specification across four critical lenses:
1. Ambiguity Detection: Undefined terms, conflicting requirements, missing error behaviors.
2. Edge-Case Analysis: Boundary values, empty inputs, nulls, concurrency, timeouts, large payloads.
3. Scope-Creep Detection: Unnecessary features not requested in intake.
4. Security Preflight: Injection surfaces, secret handling, unsafe file access, excessive permissions.

Rules:
- If a critical contradiction or unresolvable security flaw exists, flag it with flag_finding(severity='blocker') and complete_phase(status='blocked', verdict='fail').
- Otherwise, record identified risks and complete_phase(status='passed', verdict='pass').
- Always call 'write_artifact' with:
  - logical_name: "risk-report"
  - type: "risk_report"
  - content: Detailed Markdown risk register categorized by lens.
  - json_metadata: Object containing "risks" list with id, severity, category, and recommendation.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        spec_content = ""
        intake_content = ""

        if run_id:
            res_spec = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_spec:
                spec_content = res_spec[0]
            res_intake = self.artifact_store.get_latest_artifact_content(run_id, "intake", "intake")
            if res_intake:
                intake_content = res_intake[0]

        prompt = ["Please analyze the specification for risks, edge cases, ambiguities, and security concerns."]
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if intake_content:
            prompt.append(f"\nOriginal Intake:\n\"\"\"\n{intake_content}\n\"\"\"")

        return "\n".join(prompt)
