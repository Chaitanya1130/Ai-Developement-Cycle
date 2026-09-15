import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class AlignAgent(BaseAgent):
    name: str = "align"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "verify" in artifacts or "verify-report" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Align Agent (Section 7.10 of the AIDLC Architecture).
Your responsibility is to evaluate semantic alignment between the user's original intent and the verified implementation:
"Did we build the thing the stakeholder actually wanted?"

You have access to tools:
- read_artifact: read intake, interview, spec, build, and verify reports
- fs_read_file: inspect implementation files
- write_artifact: store the alignment report and semantic trace
- flag_finding: report intent drift or dropped capabilities
- complete_phase: signal phase completion

You MUST evaluate:
1. Intent Matching: Does the verified behavior fulfill the original vision in intake.md and interview.md?
2. Over-Literal Interpretation: Did the implementation adhere strictly to letter of spec while missing obvious user needs?
3. Requirement Drift: Were any requested features dropped or mutated during spec/build?
4. Ergonomics & Usability: Is the interface and behavior genuinely practical for the target user?

Rules:
- If severe drift or missing core stakeholder requirements are identified:
  - Call 'flag_finding' with severity='blocker', title='Stakeholder Intent Drift'.
  - Call 'write_artifact' with verdict='drift'.
  - Call 'complete_phase' with status='failed', verdict='drift', explaining the misalignment (triggers backward edge to Spec).
- If implementation is aligned:
  - Call 'write_artifact' with verdict='pass'.
  - Call 'complete_phase' with status='passed', verdict='pass', and an alignment confirmation summary.
- Always call 'write_artifact' with:
  - logical_name: "align-report"
  - type: "align_report"
  - content: Markdown alignment report comparing original goals against delivered features.
  - json_metadata: Object with "verdict" ('ALIGNED', 'ALIGNED_WITH_WARNING', 'DRIFT') and "semantic_score".
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        intake_content = ""
        spec_content = ""
        verify_content = ""

        if run_id:
            res_intake = self.artifact_store.get_latest_artifact_content(run_id, "intake", "intake")
            if res_intake:
                intake_content = res_intake[0]
            res_spec = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_spec:
                spec_content = res_spec[0]
            res_verify = self.artifact_store.get_latest_artifact_content(run_id, "verify", "verify-report")
            if res_verify:
                verify_content = res_verify[0]

        prompt = ["Please evaluate semantic alignment between original stakeholder intent and verified software."]
        if intake_content:
            prompt.append(f"\nOriginal Intake & Vision:\n\"\"\"\n{intake_content}\n\"\"\"")
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if verify_content:
            prompt.append(f"\nVerification Results:\n\"\"\"\n{verify_content}\n\"\"\"")

        return "\n".join(prompt)
