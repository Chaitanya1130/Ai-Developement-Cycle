import json
import os
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class ScaffoldAgent(BaseAgent):
    name: str = "scaffold"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "intake" in artifacts or "intake.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Scaffold Agent (Section 7.2 of the AIDLC Architecture).
Your responsibility is to bootstrap the initial engineering workspace and repository skeleton based on the intake requirements.

You have access to tools:
- fs_write_file: create initial directory structure and starter configuration files
- fs_read_file: inspect existing files
- fs_list_files: inspect workspace files
- write_artifact: store the scaffold report and stack manifest
- flag_finding: report setup warnings or constraints
- complete_phase: signal phase completion

You MUST follow these rules:
1. Review the intake specification, problem statement, and architectural choices from the interview.
2. Select the appropriate technology stack, test framework, runtime version, and packaging structure.
3. Bootstrap essential project configuration if not present (e.g., directory layouts, starter configs).
4. Call 'write_artifact' with:
   - logical_name: "scaffold"
   - type: "scaffold"
   - content: Markdown document detailing the stack selection, chosen tools, directory topology, and CI strategy.
   - json_metadata: A JSON object with:
     - "language": string (e.g. "python")
     - "framework": string
     - "test_framework": string (e.g. "pytest")
     - "directories": list of created/recommended directories
     - "entry_point": string
5. Call 'complete_phase' with status='passed', verdict='pass', and a clear summary.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        intake_content = ""
        interview_content = ctx.get("interview_file", "")

        if run_id:
            res = self.artifact_store.get_latest_artifact_content(run_id, "intake", "intake")
            if res:
                intake_content = res[0]

        if not intake_content and run_id:
            state = self.state_manager.get_run(run_id)
            if state:
                art = state.get("artifacts", {}).get("intake")
                if art and art.get("content_uri"):
                    try:
                        intake_content = self.artifact_store.read_artifact(art["content_uri"])
                    except Exception:
                        pass

        prompt = ["Please scaffold the project repository and produce the stack manifest."]
        if intake_content:
            prompt.append(f"\nIntake Specification:\n\"\"\"\n{intake_content}\n\"\"\"")
        if interview_content:
            prompt.append(f"\nArchitectural Interview:\n\"\"\"\n{interview_content}\n\"\"\"")

        return "\n".join(prompt)
