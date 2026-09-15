import os
from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class SpecAgent(BaseAgent):
    name: str = "spec"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        artifacts = state.get("artifacts", {})
        return "intake" in artifacts or "intake.md" in artifacts

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Spec Agent (Section 7.3 / 8.3 of the AIDLC Architecture).
Your responsibility is to generate an authoritative engineering specification based on the intake requirements.

You have access to tools:
- read_artifact: read previous artifacts
- write_artifact: write the versioned spec artifact
- flag_finding: report risks, contradictions, or blockers
- complete_phase: signal phase completion

You support two story-sourcing modes:
1. Mode A: agent_generated (default)
   - Derive user stories directly from intake requirements.
   - Decompose into user stories (STORY-001, etc.).
   - Define formal Acceptance Criteria in Given/When/Then format (AC-01, etc.).
   - Establish explicit Scope Boundaries (In Scope vs. Out of Scope).
   - Define Definition of Done.
   - Call write_artifact(logical_name="spec", type="spec", content=..., json_metadata=...).
   - Call complete_phase(status="passed", verdict="pass", summary=...).

2. Mode B: human_supplied
   - Analyze human-supplied stories alongside the intake specification.
   - CRITICAL CHECK: Check for contradiction between the human stories and the intake specification/constraints (for example, if human stories request a web API / HTTP microservice when intake specifies a CLI tool, or incompatible technology stacks).
   - If a contradiction is detected:
     1. Call flag_finding with id="BLOCKER-001", severity="blocker", category="scope", title="Contradiction between human story and intake constraints", description="Detailed explanation of the contradiction".
     2. Call complete_phase with status="blocked", verdict="fail", summary="Human story contradicts intake constraints. Execution blocked for human gate."
     3. Do NOT write spec.md or proceed to build.
   - If NO contradiction:
     - Ingest and normalize human stories.
     - Generate acceptance criteria and scope boundaries.
     - Call write_artifact(logical_name="spec", type="spec", content=..., json_metadata=...).
     - Call complete_phase(status="passed", verdict="pass", summary=...).

Always produce concrete, domain-specific engineering specifications. Never output unformatted prompt instructions.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        run_id = ctx.get("run_id", "")
        mode = ctx.get("mode") or "agent_generated"
        story_input = ctx.get("story_input") or ctx.get("stories") or ""

        intake_content = ""
        if run_id:
            res = self.artifact_store.get_latest_artifact_content(run_id, "intake", "intake")
            if res:
                intake_content = res[0]

        if not intake_content and run_id:
            # Try reading from state
            state = self.state_manager.get_run(run_id)
            if state:
                art = state.get("artifacts", {}).get("intake")
                if art and art.get("content_uri"):
                    try:
                        intake_content = self.artifact_store.read_artifact(art["content_uri"])
                    except Exception:
                        pass

        prompt = f"""Please generate the Engineering Specification for the current run.

Story-Sourcing Mode: {mode}

Intake Specification:
\"\"\"
{intake_content or "See latest intake artifact."}
\"\"\"
"""

        if mode == "human_supplied":
            prompt += f"""
Human-Supplied Stories:
\"\"\"
{story_input or "No stories supplied in input."}
\"\"\"

CRITICAL INSTRUCTION:
Examine the Human-Supplied Stories against the Intake Specification.
If there is a contradiction (e.g., requested architecture, scope, or platform directly conflicts with intake constraints), you MUST call 'flag_finding' with severity='blocker' and then call 'complete_phase' with status='blocked'. Do not write spec artifact.
If there is no contradiction, normalize the stories, generate acceptance criteria and scope boundaries, call 'write_artifact(logical_name="spec", ...)', and call 'complete_phase(status="passed")'.
"""
        else:
            prompt += """
Please decompose the intake requirements into user stories, generate acceptance criteria (Given/When/Then), define scope boundaries, store the spec via write_artifact(logical_name="spec", type="spec", content=..., json_metadata=...), and call complete_phase(status="passed").
"""

        return prompt

