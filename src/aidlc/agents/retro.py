import json
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class RetroAgent(BaseAgent):
    name: str = "retro"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "release" in artifacts or "release-manifest" in artifacts or "verify" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Retro Agent (Section 7.12 of the AIDLC Architecture).
Your responsibility is to close the lifecycle by analyzing the execution history, metrics, and quality signals across all phases to extract continuous improvement insights.

You have access to tools:
- read_artifact: read artifacts across all previous phases
- write_artifact: store the retrospective report and learning signals
- complete_phase: signal phase completion

You MUST analyze:
1. Phase Execution History: Attempts per phase, retry loops, and pipeline bottlenecks.
2. Defect & Finding Recurrence: Correlate risks identified in analyze-risks, review findings, and verification failures.
3. System Improvement Recommendations: Constructive suggestions for refining agent system prompts, test strategies, or intake templates.
4. Token & Cost Efficiency: General appraisal of pipeline execution efficiency.

Rules:
- Call 'write_artifact' with:
  - logical_name: "retro"
  - type: "retro"
  - content: Comprehensive Markdown retrospective document with executive summary, timeline of key decisions, failure analysis, and system lessons learned.
  - json_metadata: A JSON object with "total_phases_executed", "backward_loops_count", "recommendations" list, and "overall_quality_grade" ('A', 'B', etc.).
- Call 'complete_phase' with status='passed', verdict='pass', and an executive retrospective conclusion.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")

        state = self.state_manager.get_run(run_id) if run_id else None
        phase_history_json = json.dumps(state.get("history", []), indent=2) if state else "[]"

        release_content = ""
        if run_id:
            res_rel = self.artifact_store.get_latest_artifact_content(run_id, "release", "release-manifest")
            if res_rel:
                release_content = res_rel[0]

        prompt = [
            "Please perform a retrospective analysis on the completed AIDLC run and extract learning signals.",
            f"\nPhase History:\n```json\n{phase_history_json}\n```"
        ]
        if release_content:
            prompt.append(f"\nRelease Manifest:\n\"\"\"\n{release_content}\n\"\"\"")

        return "\n".join(prompt)
