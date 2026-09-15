from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent, PhaseResult

PHASE_B_C_D_PHASES = {
    "scaffold": "Phase A / Phase B component",
    "analyze-risks": "Phase B — Quality system",
    "create-test-plan": "Phase B — Quality system",
    "test-design": "Phase B — Quality system",
    "adversarial-review": "Phase B — Quality system",
    "align": "Phase B — Quality system",
    "release": "Phase C — Delivery system",
    "retro": "Phase D — Learning system",
}


class StubPhaseAgent(BaseAgent):
    def __init__(self, phase_name: str, *args, **kwargs):
        self.name = phase_name
        self.phase_scope = PHASE_B_C_D_PHASES.get(phase_name, "Future AIDLC Phase")

    def can_run(self, state: Dict[str, Any]) -> bool:
        return False

    def get_system_prompt(self) -> str:
        raise NotImplementedError(
            f"Phase '{self.name}' is part of {self.phase_scope} and is not implemented in AIDLC Phase A ('Core execution engine')."
        )

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError(
            f"Phase '{self.name}' is part of {self.phase_scope} and is not implemented in AIDLC Phase A ('Core execution engine')."
        )

    def run(self, run_id: str, context: Optional[Dict[str, Any]] = None) -> PhaseResult:
        raise NotImplementedError(
            f"Phase '{self.name}' is part of {self.phase_scope} and is not implemented in AIDLC Phase A ('Core execution engine')."
        )

