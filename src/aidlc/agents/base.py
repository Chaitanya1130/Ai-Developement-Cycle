from dataclasses import dataclass, field
import json
import os
import time
from typing import Any, Dict, List, Optional

from aidlc.artifact_store import ArtifactStore
from aidlc.model_router import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelRouter,
    ToolCall,
)
from aidlc.state import StateManager
from aidlc.tools.gateway import ToolGateway


@dataclass
class PhaseResult:
    phase: str
    status: str  # "passed", "failed", "blocked"
    artifact_ids: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    cost: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None


class BaseAgent:
    name: str = "base"
    tier: str = "tier2"
    max_iterations: int = 10

    def __init__(
        self,
        state_manager: StateManager,
        artifact_store: ArtifactStore,
        model_router: ModelRouter,
        tool_gateway: ToolGateway,
    ):
        self.state_manager = state_manager
        self.artifact_store = artifact_store
        self.model_router = model_router
        self.tool_gateway = tool_gateway

    def can_run(self, state: Dict[str, Any]) -> bool:
        return True

    def get_system_prompt(self) -> str:
        raise NotImplementedError

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError

    def run(self, run_id: str, context: Optional[Dict[str, Any]] = None) -> PhaseResult:
        state = self.state_manager.get_run(run_id)
        if not state:
            raise ValueError(f"Run '{run_id}' not found")

        if not self.can_run(state):
            raise RuntimeError(f"Prerequisites not met for phase '{self.name}' in run '{run_id}'")

        state, attempt = self.state_manager.start_phase(run_id, self.name)

        ctx = dict(context or {})
        ctx.setdefault("run_id", run_id)

        system_prompt = self.get_system_prompt()
        initial_prompt = self.get_initial_prompt(ctx)

        messages: List[ModelMessage] = [
            ModelMessage(role="user", content=initial_prompt)
        ]

        tools = self.tool_gateway.get_tool_definitions(self.name)

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        artifact_ids: List[str] = []
        phase_findings: List[Dict[str, Any]] = []
        phase_status: str = "passed"
        phase_summary: str = ""
        is_completed: bool = False

        for iteration in range(self.max_iterations):
            req = ModelRequest(
                messages=messages,
                tier=self.tier,
                system=system_prompt,
                tools=tools,
            )

            resp: ModelResponse = self.model_router.complete(req)
            total_input_tokens += resp.usage.input_tokens
            total_output_tokens += resp.usage.output_tokens
            total_cost += resp.usage.cost_estimate

            # Build assistant message structure
            assistant_content: List[Dict[str, Any]] = []
            if resp.text:
                assistant_content.append({"type": "text", "text": resp.text})
            for tc in resp.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })

            messages.append(ModelMessage(role="assistant", content=assistant_content or resp.text))

            if not resp.tool_calls:
                # No tool calls: if the model produced text without completing, check if it's done
                if resp.stop_reason == "end_turn":
                    break
                continue

            tool_results: List[Dict[str, Any]] = []
            for tc in resp.tool_calls:
                tool_res = self.tool_gateway.execute_tool(tc, run_id, self.name)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": tool_res.content,
                    "is_error": tool_res.is_error,
                })

                if not tool_res.is_error:
                    if tc.name == "write_artifact":
                        try:
                            parsed = json.loads(tool_res.content)
                            if parsed.get("artifact_id"):
                                artifact_ids.append(parsed["artifact_id"])
                        except Exception:
                            pass

                    elif tc.name == "flag_finding":
                        try:
                            f_dict = dict(tc.input)
                            f_dict["phase"] = self.name
                            phase_findings.append(f_dict)
                            if f_dict.get("severity") == "blocker":
                                phase_status = "blocked"
                        except Exception:
                            pass

                    elif tc.name == "complete_phase":
                        is_completed = True
                        phase_status = tc.input.get("status", phase_status)
                        phase_summary = tc.input.get("summary", phase_summary)

            messages.append(ModelMessage(role="user", content=tool_results))

            if is_completed:
                break

        # Check for open blocker findings in state or local findings
        updated_state = self.state_manager.get_run(run_id)
        if updated_state:
            for f in updated_state.get("findings", {}).get("open", []):
                if f.get("phase") == self.name and f.get("severity") == "blocker":
                    phase_status = "blocked"
                    if not phase_summary:
                        phase_summary = f"Blocked by finding: {f.get('title')}"

        for f in phase_findings:
            if f.get("severity") == "blocker":
                phase_status = "blocked"

        if phase_status == "blocked":
            # Collect all blocker findings
            all_blockers = [f for f in phase_findings if f.get("severity") == "blocker"]
            if updated_state:
                for f in updated_state.get("findings", {}).get("open", []):
                    if f.get("phase") == self.name and f.get("severity") == "blocker":
                        if not any(bf.get("id") == f.get("id") for bf in all_blockers):
                            all_blockers.append(f)

            # If no artifact was written, or none named logical_name == self.name, write one
            has_matching_artifact = False
            for art_id in artifact_ids:
                art_entry = self.state_manager.get_run(run_id).get("artifacts", {}).get(self.name)
                if art_entry and art_entry.get("id") == art_id:
                    has_matching_artifact = True
                    break

            if not has_matching_artifact:
                finding_bullets = "\n".join(
                    f"- **[{f.get('id', 'BLOCKER')}] {f.get('title', 'Finding')}**: {f.get('description', '')}"
                    for f in all_blockers
                ) or "- Critical contradiction or domain risk detected."

                blocker_doc = f"""# {self.name.title()} Phase: BLOCKED

## Phase Status: BLOCKED

> **Action Required**: This phase is currently BLOCKED and requires developer review.
> To unblock, review the details below and change `## Phase Status: BLOCKED` to `## Phase Status: CLEAR` (or `RESOLVED`), then re-run `aidlc run {self.name}`.

## Blocker Findings
{finding_bullets}

---
## Developer Resolution
To accept the risk or confirm resolution, change `## Phase Status: BLOCKED` above to `## Phase Status: CLEAR`, then re-run:
```bash
aidlc run {self.name}
```
"""
                blocker_art = self.artifact_store.store_artifact(
                    run_id=run_id,
                    phase=self.name,
                    logical_name=self.name,
                    type_=f"{self.name}_blocker",
                    content=blocker_doc,
                    agent_name=f"{self.name}-agent",
                    verdict="fail",
                    json_metadata={"status": "blocked", "blockers": all_blockers},
                )
                self.state_manager.add_artifact(run_id, blocker_art)
                if blocker_art["id"] not in artifact_ids:
                    artifact_ids.append(blocker_art["id"])

        cost_dict = {
            "inputTokens": total_input_tokens,
            "outputTokens": total_output_tokens,
            "cost": total_cost,
        }

        self.state_manager.record_phase_completion(
            run_id=run_id,
            phase=self.name,
            attempt=attempt,
            status=phase_status,
            artifact_ids=artifact_ids,
            findings=phase_findings,
            cost=cost_dict,
        )

        return PhaseResult(
            phase=self.name,
            status=phase_status,
            artifact_ids=artifact_ids,
            findings=phase_findings,
            cost=cost_dict,
            summary=phase_summary,
        )
