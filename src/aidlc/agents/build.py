from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class BuildAgent(BaseAgent):
    name: str = "build"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "spec" in artifacts or "spec.md" in artifacts or "test-design" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Build Agent (Section 7.7 / 8.7 of the AIDLC Architecture).
Your responsibility is to turn the engineering specification and test designs into clean, tested, working code.

You have access to tools:
- fs_write_file: create or overwrite source code and test files
- fs_read_file: read existing workspace files
- fs_list_files: inspect directory contents
- write_artifact: store the build report artifact
- flag_finding: report defects or architectural issues
- complete_phase: signal phase completion

You MUST follow these rules:
1. Review the engineering specification, acceptance criteria, and any test suites created by test-design.
2. Implement the core functionality in Python (e.g., in `generated/` or appropriate module).
3. If test files were not already created or need additions, write or update automated unit tests using pytest (in `tests/test_*.py`).
4. Call 'write_artifact' with:
   - logical_name: "build"
   - type: "build"
   - content: Markdown build report describing files created, architecture decisions, and AC coverage.
   - json_metadata: JSON object listing "files_created".
5. Call 'complete_phase' with status='passed', verdict='pass', and a concise summary.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        spec_content = ""
        test_design_content = ""
        if run_id:
            res = self.artifact_store.get_latest_artifact_content(run_id, "spec", "spec")
            if res:
                spec_content = res[0]
            res_td = self.artifact_store.get_latest_artifact_content(run_id, "test-design", "test-design")
            if res_td:
                test_design_content = res_td[0]

        if not spec_content and run_id:
            state = self.state_manager.get_run(run_id)
            if state:
                art = state.get("artifacts", {}).get("spec")
                if art and art.get("content_uri"):
                    try:
                        spec_content = self.artifact_store.read_artifact(art["content_uri"])
                    except Exception:
                        pass

        prompt = ["Please implement the software components and automated tests as specified."]
        if spec_content:
            prompt.append(f"\nEngineering Specification:\n\"\"\"\n{spec_content}\n\"\"\"")
        if test_design_content:
            prompt.append(f"\nTest Design & Scenarios:\n\"\"\"\n{test_design_content}\n\"\"\"")

        prompt.append("""
Instructions:
1. Write the implementation code using 'fs_write_file' (e.g. `generated/calc.py`).
2. Write or ensure pytest test files exist using 'fs_write_file' (e.g. `tests/test_calc.py`). Ensure tests import and exercise the implementation.
3. Save the build summary using 'write_artifact(logical_name="build", type="build", ...)'.
4. Conclude using 'complete_phase(status="passed")'.
""")
        return "\n".join(prompt)

