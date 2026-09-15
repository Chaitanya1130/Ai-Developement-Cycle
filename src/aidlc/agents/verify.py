from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class VerifyAgent(BaseAgent):
    name: str = "verify"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "build" in artifacts or "build.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Verify Agent (Section 7.9 / 8.9 of the AIDLC Architecture).
Your responsibility is to verify the build output, execute test suites, and produce verification evidence.

You have access to tools:
- run_command: execute shell commands (e.g. pytest -v)
- fs_read_file: read files in the workspace
- fs_list_files: inspect workspace directories
- write_artifact: write the verification report artifact
- flag_finding: report failures, regressions, or discrepancies
- complete_phase: signal phase completion

You MUST follow these rules:
1. Execute the automated test suite using run_command(command="pytest -v").
2. Check the command output and exitCode:
   - If exitCode == 0:
     - Document passing test execution and traceability to Acceptance Criteria.
     - Call write_artifact(logical_name="verify-report", type="verify_report", content=..., json_metadata={"verdict": "pass", ...}).
     - Call complete_phase(status="passed", verdict="pass", summary="All verification tests passed.").
   - If exitCode != 0:
     - Call flag_finding(id="FAIL-TEST-001", severity="critical", category="test_failure", title="Test suite failure", description=f"Pytest failed: {stderr or stdout}").
     - Call write_artifact(logical_name="verify-report", type="verify_report", content=..., json_metadata={"verdict": "fail", ...}).
     - Call complete_phase(status="failed", verdict="fail", summary="Automated test suite failed.").
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        build_content = ""
        spec_content = ""
        if run_id:
            res_b = self.artifact_store.get_latest_artifact_content(run_id, "build", "build")
            if res_b:
                build_content = res_b[0]
            res_s = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res_s:
                spec_content = res_s[0]

        return f"""Please verify the software build by executing the automated test suite.

Engineering Specification:
\"\"\"
{spec_content or "See latest spec artifact."}
\"\"\"

Build Report:
\"\"\"
{build_content or "See latest build artifact."}
\"\"\"

Instructions:
1. Run pytest via 'run_command(command="pytest -v")'.
2. Record the verification report using 'write_artifact(logical_name="verify-report", type="verify_report", ...)'.
3. Complete the phase using 'complete_phase'.
"""

