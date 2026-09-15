import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class ReleaseAgent(BaseAgent):
    name: str = "release"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "align" in artifacts or "align-report" in artifacts or "verify" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Release Agent (Section 7.11 of the AIDLC Architecture).
Your responsibility is to turn verified, reviewed, and aligned code into an official release artifact.

You have access to tools:
- fs_read_file: inspect code and configuration
- fs_write_file: update CHANGELOG.md or version files
- read_artifact: read verification, review, and align reports
- write_artifact: store the release manifest and release notes
- flag_finding: report release blocking issues
- complete_phase: signal phase completion

You MUST perform these steps:
1. Verify Release Readiness: Check that verify and align have completed successfully.
2. Formulate Release Notes & Changelog: Summarize features delivered, fixes, and usage instructions.
3. Call 'fs_write_file' to create or update `CHANGELOG.md` in the workspace root.
4. Call 'write_artifact' with:
   - logical_name: "release-manifest"
   - type: "release_manifest"
   - content: Markdown release notes document detailing version, changes, and install/run instructions.
   - json_metadata: A JSON object with:
     - "version": string (e.g. "0.1.0" or "1.0.0")
     - "status": "RELEASED"
     - "verification": "PASS"
     - "alignment": "PASS"
     - "release_date": string
5. Call 'complete_phase' with status='passed', verdict='pass', and a clear release summary.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        align_content = ""
        verify_content = ""

        if run_id:
            res_align = self.artifact_store.get_latest_artifact_content(run_id, "align", "align-report")
            if res_align:
                align_content = res_align[0]
            res_verify = self.artifact_store.get_latest_artifact_content(run_id, "verify", "verify-report")
            if res_verify:
                verify_content = res_verify[0]

        prompt = ["Please prepare the release package, changelog, and release manifest."]
        if align_content:
            prompt.append(f"\nAlignment Report:\n\"\"\"\n{align_content}\n\"\"\"")
        if verify_content:
            prompt.append(f"\nVerification Report:\n\"\"\"\n{verify_content}\n\"\"\"")

        return "\n".join(prompt)
