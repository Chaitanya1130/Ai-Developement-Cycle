import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class TestDesignAgent(BaseAgent):
    __test__ = False
    name: str = "test-design"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "spec" in artifacts or "test-plan" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Test-Design Agent (Section 7.6 of the AIDLC Architecture).
Your responsibility is to generate executable test suites BEFORE the software implementation is written, establishing a test-first (TDD/BDD) foundation.

You have access to tools:
- fs_write_file: write executable automated test files (in `tests/test_*.py`)
- fs_read_file: inspect existing files
- fs_list_files: inspect workspace files
- read_artifact: read test-plan, risk report, and specification
- write_artifact: store test design report and test map
- flag_finding: report ambiguities in testability
- complete_phase: signal phase completion

You MUST follow these rules:
1. Review the specification, acceptance criteria, and test plan.
2. Generate deterministic test cases covering normal flows, edge cases, and error conditions.
3. Use 'fs_write_file' to create automated test suites (e.g., in `tests/test_*.py`) using pytest.
4. Call 'write_artifact' with:
   - logical_name: "test-design"
   - type: "test_design"
   - content: Markdown document detailing the test suites created, fixture designs, and AC mapping.
   - json_metadata: Object containing "test_files" created and "ac_to_test_mapping".
5. Call 'complete_phase' with status='passed', verdict='pass', and a clear summary.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        spec_content = ""
        plan_content = ""

        if run_id:
            res_spec = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_spec:
                spec_content = res_spec[0]
            res_plan = self.artifact_store.get_latest_artifact_content(run_id, "create-test-plan", "test-plan")
            if res_plan:
                plan_content = res_plan[0]

        prompt = ["Please design and write the executable test suites based on the specification and test plan."]
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if plan_content:
            prompt.append(f"\nTest Plan:\n\"\"\"\n{plan_content}\n\"\"\"")

        return "\n".join(prompt)
