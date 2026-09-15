from typing import Any, Dict, Optional

from aidlc.agents.base import BaseAgent


class IntakeAgent(BaseAgent):
    name: str = "intake"
    tier: str = "tier2"

    def can_run(self, state: Dict[str, Any]) -> bool:
        return True

    def get_system_prompt(self) -> str:
        return """You are the AIDLC Intake Agent (Section 7.1 / 8.1 of the AIDLC Architecture).
Your responsibility is to analyze the user's raw problem statement, extract requirements, formulate an architectural discovery interview, and establish the foundational intake artifacts.

You have access to tools:
- write_artifact: write versioned artifacts (intake and interview)
- complete_phase: signal phase completion

You MUST generate TWO essential artifacts for every intake run:

1. Requirements Specification Artifact:
   Call 'write_artifact' with:
   - logical_name: "intake"
   - type: "intake"
   - content: Complete Markdown document with sections:
     # Requirements Specification: <Title>
     ## 1. Problem Statement
     ## 2. User / Actor
     ## 3. Desired Outcome
     ## 4. Functional Requirements (FR-01, FR-02, etc.)
     ## 5. Non-Functional Requirements (NFR-01, etc.)
     ## 6. Constraints
     ## 7. Story Sourcing Mode (agent_generated or human_supplied)
     ## 8. Acceptance Signals
   - json_metadata: JSON object summarizing problem, actor, functional_requirements, constraints, and story_source.

2. Discovery & Architectural Alignment Interview Artifact:
   Call 'write_artifact' with:
   - logical_name: "interview"
   - type: "interview"
   - content: Complete Markdown document with sections:
     # Discovery & Architectural Alignment Interview: <Title>
     ## 1. Project Vision & Core Description
        - High-level mission and primary user value proposition.
     ## 2. Methodology & Driven-Development Selection
        - Evaluate development paradigms:
          * TDD (Test-Driven Development): Red-Green-Refactor, automated test-first.
          * BDD (Behavior-Driven Development): Scenario & Given/When/Then acceptance criteria first.
          * CDD (Contract-Driven Development): API/schema interface contracts first.
          * EDD (Event-Driven Development): Asynchronous event/message pub-sub decoupled architecture.
          * DDD (Domain-Driven Design): Ubiquitous language, entities, value objects, and domain aggregates.
        - Declare the recommended methodology for this project with concrete rationale.
     ## 3. Architectural Style & Interface Boundaries
        - Recommended form factor (CLI utility, HTTP REST microservice, SDK library, worker daemon).
        - Statefulness, persistence strategy, and storage boundaries.
        - Dependency philosophy (zero external dependencies vs standard library vs curated framework).
     ## 4. Testing & Quality Strategy
        - Test pyramid distribution (unit, component, integration).
        - Test framework selection (e.g., pytest) and coverage expectations.
     ## 5. Non-Functional Priorities & Trade-Offs
        - Latency, startup performance, and resource bounds.
        - Portability across operating systems (POSIX, Linux, macOS, Windows).
        - Error handling posture (fail-fast with clear stderr diagnostics vs fallback).
     ## 6. Pre-filled Recommended Defaults & Sign-off Status
        - Key decision summary ready for human terminal review.
   - json_metadata: JSON object containing:
     {
       "chosen_methodology": "TDD", // or BDD, CDD, EDD, DDD
       "architecture_style": "CLI utility",
       "test_framework": "pytest",
       "dependency_strategy": "zero external dependencies",
       "status": "ready_for_review"
     }

3. Developer Interview Parsing Rules:
   - When the user input contains `interview.md` or questionnaire sections:
     * Checkboxes: Inspect all checkboxes marked with `[x]` or `[X]` (e.g., `- [x] **TDD**` or `- [x] **REST**`). You MUST strictly adopt the marked options as the developer's authoritative architectural choices.
     * Project Vision & Features: Extract project title, problem statement, users, and numbered features from Sections 1 and 4.
     * Blank Sections: If a field or checkbox was left unselected, formulate best-practice engineering recommendations tailored to the project domain and record them in the interview artifact.

4. After writing BOTH artifacts ('intake' and 'interview'), call 'complete_phase' with:
   - status: "passed"
   - verdict: "pass"
   - summary: concise summary confirming intake specification and architectural interview are generated with the developer's selected methodology.

NEVER output raw prompt templates or empty placeholders. Generate concrete, project-tailored content.
"""

    def get_initial_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        ask = ctx.get("ask", "").strip()
        interview_file = ctx.get("interview_file", "").strip()

        if not ask and not interview_file:
            workspace = getattr(self.tool_gateway, "workspace_dir", os.getcwd())
            interview_path = os.path.join(workspace, "interview.md")
            if os.path.exists(interview_path):
                try:
                    with open(interview_path, "r", encoding="utf-8") as f:
                        interview_file = f.read().strip()
                except Exception:
                    pass

        if interview_file and (not ask or ask == interview_file):
            return f"""The developer has configured the following Project Discovery & Architectural Alignment Interview (interview.md):

\"\"\"
{interview_file}
\"\"\"

Please analyze this developer interview:
1. Extract the project vision, problem statement, target users, desired outcome, functional requirements, and constraints.
2. Respect and formalize the developer's selected methodology (e.g. TDD, BDD, CDD, EDD, DDD) and architectural boundaries.
3. Save the requirements specification artifact:
   write_artifact(logical_name="intake", type="intake", content=..., json_metadata=...).
4. Formalize and save the Discovery Interview artifact:
   write_artifact(logical_name="interview", type="interview", content=..., json_metadata=...).
5. Signal completion: complete_phase(status="passed").
"""

        fallback_ask = ask or "Build a CLI calculator function with addition and subtraction"
        return f"""Please analyze the following raw user request and produce the authoritative Intake Specification and Discovery Interview artifacts:

Raw Request:
\"\"\"
{fallback_ask}
\"\"\"

Requirements:
1. Extract problem statement, user personas, desired outcomes, constraints, and functional requirements.
2. Save the requirements artifact: write_artifact(logical_name="intake", type="intake", content=..., json_metadata=...).
3. Conduct the Discovery & Architectural Alignment Interview:
   - Formulate key architectural questions.
   - Evaluate and recommend the driven-development methodology (TDD, BDD, CDD, EDD, or DDD).
   - Define architectural style, quality boundaries, and trade-offs.
   - Save the interview artifact: write_artifact(logical_name="interview", type="interview", content=..., json_metadata=...).
4. Signal completion: complete_phase(status="passed").
"""
