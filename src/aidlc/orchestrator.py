import os
import re
from typing import Any, Dict, List, Optional

from aidlc.agents.base import BaseAgent, PhaseResult
from aidlc.agents.intake import IntakeAgent
from aidlc.agents.scaffold import ScaffoldAgent
from aidlc.agents.spec import SpecAgent
from aidlc.agents.analyze_risks import AnalyzeRisksAgent
from aidlc.agents.test_plan import TestPlanAgent
from aidlc.agents.test_design import TestDesignAgent
from aidlc.agents.build import BuildAgent
from aidlc.agents.adversarial_review import AdversarialReviewAgent
from aidlc.agents.verify import VerifyAgent
from aidlc.agents.align import AlignAgent
from aidlc.agents.release import ReleaseAgent
from aidlc.agents.retro import RetroAgent
from aidlc.agents.stubs import StubPhaseAgent
from aidlc.artifact_store import ArtifactStore
from aidlc.model_router import ModelRouter
from aidlc.state import StateManager
from aidlc.tools.gateway import ToolGateway

PHASE_ALIASES = {
    "red_team_review": "adversarial-review",
    "red-team-review": "adversarial-review",
    "adversarial_review": "adversarial-review",
    "create-tests": "test-design",
    "create_tests": "test-design",
    "analyze_risks": "analyze-risks",
    "create_test_plan": "create-test-plan",
    "test_design": "test-design",
}

PIPELINE_ORDER = [
    "intake",
    "scaffold",
    "spec",
    "analyze-risks",
    "create-test-plan",
    "test-design",
    "build",
    "adversarial-review",
    "verify",
    "align",
    "release",
    "retro",
]


def normalize_phase(phase: str) -> str:
    p = phase.lower().strip()
    return PHASE_ALIASES.get(p, p)


class Orchestrator:
    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        provider_override: Optional[str] = None,
    ):
        self.workspace_dir = workspace_dir or os.getcwd()
        self.state_manager = StateManager(self.workspace_dir)
        self.artifact_store = ArtifactStore(self.workspace_dir)
        self.model_router = ModelRouter(provider_override=provider_override)
        self.tool_gateway = ToolGateway(
            workspace_dir=self.workspace_dir,
            state_manager=self.state_manager,
            artifact_store=self.artifact_store,
        )

        self.phase_agents: Dict[str, BaseAgent] = {
            "intake": IntakeAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "scaffold": ScaffoldAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "spec": SpecAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "analyze-risks": AnalyzeRisksAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "create-test-plan": TestPlanAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "test-design": TestDesignAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "build": BuildAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "adversarial-review": AdversarialReviewAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "verify": VerifyAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "align": AlignAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "release": ReleaseAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
            "retro": RetroAgent(
                self.state_manager,
                self.artifact_store,
                self.model_router,
                self.tool_gateway,
            ),
        }

        self.retry_limits = {
            "intake": 2,
            "scaffold": 2,
            "spec": 3,
            "analyze-risks": 2,
            "create-test-plan": 2,
            "test-design": 3,
            "build": 4,
            "adversarial-review": 3,
            "verify": 3,
            "align": 2,
            "release": 2,
            "retro": 2,
        }

        self.graph_transitions = {
            "intake": "scaffold",
            "scaffold": "spec",
            "spec": "analyze-risks",
            "analyze-risks": "create-test-plan",
            "create-test-plan": "test-design",
            "test-design": "build",
            "build": "adversarial-review",
            "adversarial-review": "verify",
            "verify": "align",
            "align": "release",
            "release": "retro",
            "retro": "completed",
        }

    def get_agent(self, phase_name: str) -> BaseAgent:
        canonical = normalize_phase(phase_name)
        if canonical in self.phase_agents:
            return self.phase_agents[canonical]
        return StubPhaseAgent(canonical)

    def execute_phase(
        self,
        run_id: str,
        phase_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PhaseResult:
        canonical = normalize_phase(phase_name)
        state = self.state_manager.get_run(run_id)
        if not state:
            raise ValueError(f"Run '{run_id}' not found")

        # 1. Check if run is currently blocked by another phase
        blocked_phase = self.state_manager.get_blocked_phase(run_id)
        has_blockers = self.state_manager.has_unresolved_blockers(run_id)

        if has_blockers and blocked_phase and canonical != blocked_phase:
            art = state.get("artifacts", {}).get(blocked_phase)
            art_uri = art.get("content_uri") if art else f".aidlc/artifacts/{run_id}/{blocked_phase}/"
            raise RuntimeError(
                f"Cannot execute phase '{canonical}'. The run is BLOCKED at phase '{blocked_phase}'.\n"
                f"You cannot bypass a blocked phase.\n"
                f"Check out the artifact at: {art_uri}\n"
                f"Resolve the blocker in the artifact and re-run 'aidlc run {blocked_phase}' first."
            )

        # 2. Check if the current phase was blocked, and whether developer unblocked it by editing the artifact
        if has_blockers and canonical == blocked_phase:
            art_entry = state.get("artifacts", {}).get(canonical)
            latest_content = None
            latest_path = None
            if art_entry and art_entry.get("content_uri"):
                full_path = os.path.join(self.workspace_dir, art_entry["content_uri"])
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        latest_content = f.read()
                    latest_path = full_path

            if not latest_content:
                alias_names = [canonical, canonical.replace("-", "_"), "risk-report", "spec", "specification"]
                for an in alias_names:
                    res = self.artifact_store.get_latest_artifact_content(run_id, canonical, an)
                    if res:
                        latest_content, latest_path = res
                        break

            if latest_content:
                unblock_match = re.search(
                    r"(?:status|verdict|state)\s*:\s*(clear|resolved|approved|pass|passed|unblocked|accept|accepted)",
                    latest_content,
                    re.IGNORECASE,
                )
                if unblock_match:
                    # Developer unblocked via artifact edit!
                    self.state_manager.resolve_blocker_findings(run_id, phase=canonical)
                    updated_state = self.state_manager.get_run(run_id)
                    if updated_state:
                        updated_state["phase"]["current"] = canonical
                        updated_state["phase"]["status"] = "passed"
                        for h in updated_state.get("phase_history", []):
                            if h["phase"] == canonical:
                                h["status"] = "passed"
                        if art_entry:
                            art_entry["verdict"] = "pass"
                            updated_state.setdefault("artifacts", {})[canonical] = art_entry
                        self.state_manager.save_run_state(updated_state)

                    with self.state_manager.conn:
                        self.state_manager.conn.execute(
                            "UPDATE phase_history SET status = 'passed' WHERE run_id = ? AND phase = ?",
                            (run_id, canonical),
                        )
                        if art_entry and art_entry.get("id"):
                            self.state_manager.conn.execute(
                                "UPDATE artifacts SET verdict = 'pass' WHERE run_id = ? AND id = ?",
                                (run_id, art_entry["id"]),
                            )

                    self.state_manager.sync_progress_file(run_id)

                    rel_path = os.path.relpath(latest_path, self.workspace_dir) if latest_path else (art_entry.get("content_uri") if art_entry else "")
                    return PhaseResult(
                        phase=canonical,
                        status="passed",
                        artifact_ids=[art_entry["id"]] if (art_entry and art_entry.get("id")) else [],
                        findings=[],
                        summary=f"Unblocked by developer via artifact edit ({rel_path}).",
                    )
                else:
                    # Artifact has not been changed to CLEAR
                    rel_path = os.path.relpath(latest_path, self.workspace_dir) if latest_path else (art_entry.get("content_uri") if art_entry else "")
                    return PhaseResult(
                        phase=canonical,
                        status="blocked",
                        artifact_ids=[art_entry["id"]] if (art_entry and art_entry.get("id")) else [],
                        summary=f"Phase remains blocked. Artifact has not been changed to CLEAR ({rel_path}).",
                    )

        # 3. Check phase prerequisites (cannot jump ahead without predecessor passing)
        PHASE_PREREQUISITES = {
            "scaffold": ["intake"],
            "spec": ["intake"],
            "analyze-risks": ["spec"],
            "create-test-plan": ["spec"],
            "test-design": ["spec"],
            "build": ["spec"],
            "adversarial-review": ["build"],
            "verify": ["build"],
            "align": ["build", "spec"],
            "release": ["verify"],
            "retro": ["verify"],
        }
        required_preds = PHASE_PREREQUISITES.get(canonical, [])
        history_phases = {h["phase"]: h.get("status") for h in state.get("phase_history", [])}
        artifacts = state.get("artifacts", {})

        for pred in required_preds:
            pred_status = history_phases.get(pred)
            pred_art = artifacts.get(pred) or artifacts.get(pred.replace("-", "_"))
            if pred_status != "passed" and not (pred_art and pred_art.get("verdict") in ("pass", "info")):
                raise RuntimeError(
                    f"Cannot execute phase '{canonical}'. Predecessor phase '{pred}' must be completed with status 'passed' first (currently: '{pred_status or 'not run'}')."
                )

        agent = self.get_agent(canonical)
        ctx = dict(context or {})
        ctx["run_id"] = run_id

        # Update run state to running
        state["phase"]["current"] = canonical
        state["phase"]["status"] = "running"
        self.state_manager.save_run_state(state)
        self.state_manager.sync_progress_file(run_id)

        result = agent.run(run_id, ctx)

        # Update run state based on execution
        state = self.state_manager.get_run(run_id)
        if state:
            state["phase"]["current"] = canonical
            state["phase"]["status"] = result.status
            self.state_manager.save_run_state(state)
            self.state_manager.sync_progress_file(run_id)

        return result

    def run_pipeline(
        self,
        run_id: Optional[str] = None,
        start_phase: str = "intake",
        initial_context: Optional[Dict[str, Any]] = None,
        on_phase_completed: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if not run_id:
            active = self.state_manager.get_active_run()
            if active:
                run_id = active["run_id"]
            else:
                new_run = self.state_manager.create_run()
                run_id = new_run["run_id"]

        current_phase = normalize_phase(start_phase)
        context = dict(initial_context or {})

        while current_phase and current_phase != "completed":
            state = self.state_manager.get_run(run_id)
            if not state:
                raise ValueError(f"Run {run_id} not found")

            # Check retry budget for current phase
            attempts = sum(1 for h in state.get("phase_history", []) if h["phase"] == current_phase)
            limit = self.retry_limits.get(current_phase, 3)
            if attempts >= limit:
                state["phase"]["status"] = "failed"
                self.state_manager.save_run_state(state)
                self.state_manager.sync_progress_file(run_id)
                raise RuntimeError(
                    f"Retry budget exceeded for phase '{current_phase}' ({attempts}/{limit} attempts)."
                )

            result = self.execute_phase(run_id, current_phase, context)

            if result.status == "blocked":
                # Blocker encountered: check if backward edge possible
                if current_phase == "analyze-risks":
                    spec_attempts = sum(1 for h in state.get("phase_history", []) if h["phase"] == "spec")
                    if spec_attempts < self.retry_limits.get("spec", 3):
                        current_phase = "spec"
                        context = {"findings": result.findings, "retry": True}
                        continue
                # Otherwise halt pipeline
                # Blocker encountered: Halt pipeline immediately and sync progress
                self.state_manager.sync_progress_file(run_id)
                break

            elif result.status == "passed":
                if on_phase_completed:
                    latest_state = self.state_manager.get_run(run_id) or state
                    should_continue = on_phase_completed(current_phase, result, latest_state)
                    if not should_continue:
                        latest_state["phase"]["status"] = "paused"
                        self.state_manager.save_run_state(latest_state)
                        break

                next_phase = self.graph_transitions.get(current_phase)
                if next_phase == "completed":
                    updated = self.state_manager.get_run(run_id)
                    if updated:
                        updated["phase"]["current"] = "completed"
                        updated["phase"]["status"] = "passed"
                        self.state_manager.save_run_state(updated)
                    break
                current_phase = next_phase
                context = {}

            elif result.status == "failed":
                # Bounded backward edge retry logic
                if current_phase in ("adversarial-review", "verify"):
                    build_attempts = sum(1 for h in state.get("phase_history", []) if h["phase"] == "build")
                    if build_attempts < self.retry_limits.get("build", 4):
                        current_phase = "build"
                        context = {"findings": result.findings, "retry": True}
                        continue

                elif current_phase == "align":
                    spec_attempts = sum(1 for h in state.get("phase_history", []) if h["phase"] == "spec")
                    if spec_attempts < self.retry_limits.get("spec", 3):
                        current_phase = "spec"
                        context = {"findings": result.findings, "retry": True}
                        continue

                # If cannot retry or failed in non-recoverable phase, halt
                break

            else:
                break

        final_state = self.state_manager.get_run(run_id)
        return final_state or {}
