import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class AdversarialReviewAgent(BaseAgent):
    name: str = "adversarial-review"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "build" in artifacts or "build.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Adversarial-Review Agent (Section 7.8 of the AIDLC Architecture).
You act as an independent Red Team and code reviewer trying to uncover bugs, vulnerabilities, and spec non-compliance in the implemented code.

You have access to tools:
- fs_read_file: read implemented source and test files
- fs_list_files: inspect repository layout
- read_artifact: read build report, spec, test plan, and intake
- write_artifact: store the adversarial review report and findings
- flag_finding: report defects, security issues, or compliance failures
- complete_phase: signal phase completion

You MUST evaluate the code across these critical lenses:
1. Correctness: Does the code accurately satisfy the acceptance criteria? Are edge cases handled?
2. Security: Check for injection vulnerabilities, unsafe file access, secret exposure, or unvalidated inputs.
3. Reliability: Resource cleanup, exception handling, boundary overflows.
4. Spec Compliance: Ensure no scope creep or omitted requirements.

Rules:
- If critical defects or security vulnerabilities are discovered:
  - Call 'flag_finding' with severity='blocker' or severity='critical'.
  - Call 'write_artifact' with verdict='fail'.
  - Call 'complete_phase' with status='failed', verdict='fail', and detailed defect explanation (this triggers a backward loop to Build).
- If code is sound or only minor non-blocking warnings exist:
  - Call 'write_artifact' with verdict='pass'.
  - Call 'complete_phase' with status='passed', verdict='pass', and an approval summary.
- Always call 'write_artifact' with:
  - logical_name: "review-report"
  - type: "review_report"
  - content: Markdown review report categorized by lens.
  - json_metadata: A JSON object with "verdict" ('PASS', 'PASS_WITH_WARNINGS', 'FAIL') and "findings" list.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        spec_content = ""
        build_content = ""

        if run_id:
            res_spec = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_spec:
                spec_content = res_spec[0]
            res_build = self.artifact_store.get_latest_artifact_content(run_id, "build", "build")
            if res_build:
                build_content = res_build[0]

        prompt = ["Please conduct an adversarial red-team review of the implementation."]
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if build_content:
            prompt.append(f"\nBuild Report:\n\"\"\"\n{build_content}\n\"\"\"")

        return "\n".join(prompt)
