import json
import os
import sys
from typing import Optional

import click

from aidlc.orchestrator import Orchestrator, normalize_phase
from aidlc.state import StateManager


@click.group()
def cli():
    """AIDLC — AI-Driven Development Lifecycle CLI (Phase A Core Engine)"""
    pass


DEFAULT_INTERVIEW_TEMPLATE = """# Project Discovery & Architectural Alignment Interview

> Instructions:
> 1. Fill in your project overview, description, and desired features in Sections 1 & 4.
> 2. Mark your architectural choices with an `[x]` in Sections 2, 3, and 5.
> 3. Run `aidlc run intake` (or `aidlc run intake --pipeline`). The Intake Agent will automatically parse this file and build your specification!

---

## 1. Project Overview & Vision
- **Project Name / Title**: 
- **Problem Statement**: 
- **Target Users & Personas**: 
- **Desired Outcome & Value**: 

---

## 2. Development Methodology Selection
*Mark your chosen development paradigm with an `[x]`*:
- [ ] **TDD (Test-Driven Development)**: Red-Green-Refactor cycle; automated unit and edge-case tests written before code implementation.
- [ ] **BDD (Behavior-Driven Development)**: User-story and scenario-first; acceptance criteria specified in Given/When/Then format.
- [ ] **CDD (Contract-Driven Development)**: Interface schemas, API specifications, and formal contracts defined before coding.
- [ ] **EDD (Event-Driven Development)**: Decoupled asynchronous architecture with event pub/sub and messaging streams.
- [ ] **DDD (Domain-Driven Design)**: Complex domain logic, ubiquitous language, entity modeling, and aggregates.

- **Methodology Notes / Rationale (Optional)**: 

---

## 3. Architecture & Form Factor
*Mark your primary form factor with an `[x]`*:
- [ ] **CLI Application / Utility**: Terminal command with subcommands, arguments, flags, and POSIX exit codes.
- [ ] **REST / HTTP API Microservice**: Web service exposing endpoints (JSON, OpenAPI, HTTP status codes).
- [ ] **Reusable Library / SDK**: Importable package/module with public interfaces, types, and client methods.
- [ ] **Background Worker / Daemon**: Long-running background service, cron processor, or queue consumer.
- [ ] **Full-stack Web Application**: Backend service combined with frontend user interface.

*State & Persistence Strategy (Mark one with `[x]`)*:
- [ ] **Stateless**: Pure memory execution; no local or database persistence required.
- [ ] **File-Based / SQLite**: Lightweight local storage (JSON/YAML/SQLite).
- [ ] **External Database**: Relational (PostgreSQL/MySQL) or Document (MongoDB/DynamoDB).

*Dependency Philosophy (Mark one with `[x]`)*:
- [ ] **Zero External Dependencies**: Standard library built-ins only.
- [ ] **Curated Minimal Dependencies**: Lightweight, trusted community packages.
- [ ] **Full Framework**: Comprehensive framework ecosystem (e.g., FastAPI, Django, Express, NestJS).

---

## 4. Key Functional Requirements & Features
*List the essential capabilities, commands, or behaviors you want implemented:*
1. 
2. 
3. 
4. 

---

## 5. Non-Functional Requirements & Constraints
- **Performance / Latency Targets**: 
- **Target Runtimes & Languages**: (e.g. Python 3.10+, Node.js, Go)
- **Security & Permissions**: 
- **Operating Systems / Environments**: 
- **Error Handling Posture**: 
"""


@cli.command()
@click.option("--project-id", default="default-project", help="Project identifier")
@click.option("--story-id", default="default-story", help="Story identifier")
def init(project_id: str, story_id: str):
    """Initialize an AIDLC workspace, creating state.db and an active run."""
    workspace = os.getcwd()
    sm = StateManager(workspace)
    run = sm.create_run(project_id=project_id, story_id=story_id)
    click.echo(f"Initialized AIDLC workspace in {os.path.join(workspace, '.aidlc')}")
    click.echo(f"Created active run: {run['run_id']}")
    click.echo(f"Phase: {run['phase']['current']} | Status: {run['phase']['status']}")

    interview_path = os.path.join(workspace, "interview.md")
    if not os.path.exists(interview_path):
        with open(interview_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_INTERVIEW_TEMPLATE)
        click.echo(f"\nGenerated discovery interview template: ./interview.md")
    else:
        click.echo(f"\nDiscovered existing interview file: ./interview.md")

    click.echo("\n👉 Next Step:")
    click.echo("   1. Open ./interview.md to review or customize your project requirements.")
    click.echo("   2. Run 'aidlc run intake' (or 'aidlc run intake --pipeline') to begin.")


def render_intake_interview_summary(sm: StateManager, run_id: str) -> None:
    run_data = sm.get_run(run_id)
    if not run_data:
        return

    artifacts = run_data.get("artifacts", {})
    intake_art = artifacts.get("intake")
    interview_art = artifacts.get("interview")

    methodology = "Not specified"
    arch_style = "Not specified"
    test_strat = "Not specified"

    if interview_art:
        uri = interview_art.get("content_uri")
        if uri:
            json_uri = uri.rsplit(".", 1)[0] + ".json"
            full_json_path = os.path.join(sm.workspace_dir, json_uri)
            if os.path.exists(full_json_path):
                try:
                    with open(full_json_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        methodology = meta.get("chosen_methodology") or methodology
                        arch_style = meta.get("architecture_style") or arch_style
                        test_strat = meta.get("test_framework") or test_strat
                except Exception:
                    pass

            if methodology == "Not specified":
                full_md_path = os.path.join(sm.workspace_dir, uri)
                if os.path.exists(full_md_path):
                    try:
                        with open(full_md_path, "r", encoding="utf-8") as f:
                            text = f.read()
                            import re
                            m_meth = re.search(r"(?:-\s*\[[xX]\]\s*\*\*([^*]+)\*\*|\*\*(?:Chosen|Recommended) (?:Methodology|Paradigm)\*\*:\s*([^\n]+))", text)
                            if m_meth:
                                methodology = (m_meth.group(1) or m_meth.group(2)).strip()
                            m_arch = re.search(r"(?:-\s*\[[xX]\]\s*\*\*([^*]+)\*\*|\*\*(?:Form Factor|Architecture Style)\*\*:\s*([^\n]+))", text)
                            if m_arch:
                                arch_style = (m_arch.group(1) or m_arch.group(2)).strip()
                    except Exception:
                        pass

    click.echo("\n" + "=" * 64)
    click.echo("  AIDLC Discovery & Architectural Alignment Summary")
    click.echo("=" * 64)
    if intake_art:
        click.echo(f"  • Requirements: {intake_art.get('content_uri')}")
    if interview_art:
        click.echo(f"  • Interview:    {interview_art.get('content_uri')}")
    click.echo(f"  • Methodology:  {methodology}")
    click.echo(f"  • Architecture: {arch_style}")
    click.echo(f"  • Test Harness: {test_strat}")
    click.echo("=" * 64)


@cli.command()
@click.argument("phase", required=True)
@click.option("--ask", help="Raw problem statement or feature request (for intake)")
@click.option(
    "--mode",
    type=click.Choice(["agent_generated", "human_supplied"], case_sensitive=False),
    default="agent_generated",
    help="Story sourcing mode for spec phase (agent_generated or human_supplied)",
)
@click.option("--stories", help="Human-supplied stories text or path to stories file")
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "agy", "mock"], case_sensitive=False),
    help="LLM provider override (anthropic, agy, mock)",
)
@click.option("--pipeline", is_flag=True, default=False, help="Run full pipeline from this phase")
@click.option("-y", "--yes", is_flag=True, default=False, help="Automatically approve intake/interview without prompt")
@click.option("--run-id", help="Explicit Run ID (defaults to active run)")
def run(
    phase: str,
    ask: Optional[str],
    mode: str,
    stories: Optional[str],
    provider: Optional[str],
    pipeline: bool,
    yes: bool,
    run_id: Optional[str],
):
    """Execute a lifecycle phase (intake, spec, build, verify) or pipeline."""
    workspace = os.getcwd()
    sm = StateManager(workspace)

    active_run_id = run_id or sm.get_active_run_id()
    if not active_run_id:
        new_run = sm.create_run()
        active_run_id = new_run["run_id"]
        click.echo(f"No active run found. Created new run: {active_run_id}")

    phase = normalize_phase(phase)

    # Read stories content if a file path was passed
    story_input = stories
    if stories and os.path.exists(stories) and os.path.isfile(stories):
        with open(stories, "r", encoding="utf-8") as f:
            story_input = f.read()

    # Read interview.md if available in workspace
    interview_file_path = os.path.join(workspace, "interview.md")
    interview_content = ""
    if os.path.exists(interview_file_path):
        try:
            with open(interview_file_path, "r", encoding="utf-8") as f:
                interview_content = f.read().strip()
        except Exception:
            pass

    resolved_ask = ask
    if not resolved_ask and interview_content and phase == "intake":
        resolved_ask = interview_content
        click.echo("[AIDLC] Auto-detected ./interview.md as primary project input.")
    elif not resolved_ask and not interview_content and phase == "intake":
        click.echo(
            "[AIDLC Notice] Neither --ask was provided nor was ./interview.md found. Using standard default prompt."
        )

    context = {
        "ask": resolved_ask,
        "mode": mode,
        "story_input": story_input,
        "interview_file": interview_content,
    }

    try:
        orch = Orchestrator(workspace_dir=workspace, provider_override=provider)
        active_provider, _ = orch.model_router.resolve_provider()
        click.echo(f"[AIDLC] Provider resolved: {active_provider.upper()}")
    except Exception as e:
        click.echo(f"[AIDLC Error] Provider resolution failed: {e}", err=True)
        sys.exit(1)

    if pipeline:
        click.echo(f"[AIDLC] Running pipeline starting from phase '{phase}' on run {active_run_id}...")

        def pipeline_gate_check(current_phase: str, result, current_state) -> bool:
            if current_phase == "intake" and result.status == "passed":
                render_intake_interview_summary(sm, active_run_id)
                if not yes:
                    confirmed = click.confirm(
                        "\nIs everything good with the intake specification and architectural interview to proceed?",
                        default=True,
                    )
                    if not confirmed:
                        click.echo("\n[AIDLC] Pipeline halted by user after intake phase. Review/edit artifacts before resuming.")
                        return False

                current_state.setdefault("gates", {}).setdefault("approved", []).append("intake-interview")
                sm.save_run_state(current_state)
                click.echo("[AIDLC] Intake & architectural interview confirmed. Proceeding to scaffold phase...\n")
            return True

        try:
            final_state = orch.run_pipeline(
                run_id=active_run_id,
                start_phase=phase,
                initial_context=context,
                on_phase_completed=pipeline_gate_check,
            )
            click.echo(f"[AIDLC] Pipeline completed. Final phase: {final_state['phase']['current']} | Status: {final_state['phase']['status']}")
            if final_state["phase"]["status"] == "blocked":
                click.echo("[AIDLC] Pipeline blocked! Human gate intervention required.")
                sys.exit(2)
            elif final_state["phase"]["status"] == "failed":
                click.echo("[AIDLC] Pipeline failed.")
                sys.exit(1)
            elif final_state["phase"]["status"] == "paused":
                click.echo("[AIDLC] Pipeline paused at user gate.")
                sys.exit(0)
        except Exception as e:
            click.echo(f"[AIDLC Error] Pipeline execution error: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(f"[AIDLC] Executing phase '{phase}' for run {active_run_id}...")
        try:
            result = orch.execute_phase(run_id=active_run_id, phase_name=phase, context=context)
            click.echo(f"\n--- Phase '{phase}' Result ---")
            click.echo(f"Status: {result.status.upper()}")
            if result.summary:
                click.echo(f"Summary: {result.summary}")
            if result.artifact_ids:
                click.echo(f"Artifacts: {', '.join(result.artifact_ids)}")
            if result.findings:
                click.echo(f"Findings ({len(result.findings)}):")
                for f in result.findings:
                    click.echo(f"  [{f.get('severity', 'info').upper()}] {f.get('title')}: {f.get('description', '')}")

            cost = result.cost
            click.echo(
                f"Usage: {cost.get('inputTokens', 0)} in / {cost.get('outputTokens', 0)} out | Est Cost: ${cost.get('cost', 0.0):.4f}"
            )

            if phase == "intake" and result.status == "passed":
                render_intake_interview_summary(sm, active_run_id)
                if not yes:
                    confirmed = click.confirm(
                        "\nIs everything good with the intake specification and architectural interview to proceed?",
                        default=True,
                    )
                    if confirmed:
                        click.echo("[AIDLC] Intake and architectural interview confirmed.")
                        updated = sm.get_run(active_run_id)
                        if updated:
                            updated.setdefault("gates", {}).setdefault("approved", []).append("intake-interview")
                            sm.save_run_state(updated)
                    else:
                        click.echo("\n[AIDLC] Intake completed. Review or edit artifacts before proceeding with 'aidlc run spec'.")

            if result.status == "blocked":
                click.echo("\n[AIDLC] Execution BLOCKED. Human intervention or clarification required.")
                sys.exit(2)
            elif result.status == "failed":
                click.echo("\n[AIDLC] Phase execution FAILED.")
                sys.exit(1)
        except NotImplementedError as nie:
            click.echo(f"[AIDLC NotImplemented] {nie}", err=True)
            sys.exit(3)
        except Exception as e:
            click.echo(f"[AIDLC Error] Execution error: {e}", err=True)
            sys.exit(1)


@cli.command()
@click.option("--run-id", help="Explicit Run ID to inspect")
def status(run_id: Optional[str]):
    """Display active run status, phase history, artifacts, and findings."""
    workspace = os.getcwd()
    sm = StateManager(workspace)
    target_id = run_id or sm.get_active_run_id()

    if not target_id:
        click.echo("No active run found. Run 'aidlc init' or specify --run-id.")
        return

    run_data = sm.get_run(target_id)
    if not run_data:
        click.echo(f"Run '{target_id}' not found.")
        return

    click.echo("=" * 60)
    click.echo(f"AIDLC Run Status: {run_data['run_id']}")
    click.echo(f"Project: {run_data.get('project_id')} | Story: {run_data.get('story_id')}")
    click.echo(f"Current Phase: {run_data['phase']['current']} | Status: {run_data['phase']['status'].upper()}")
    click.echo(f"Created: {run_data['metadata'].get('created_at')} | Updated: {run_data['metadata'].get('updated_at')}")
    click.echo("=" * 60)

    # Phase History
    click.echo("\nPhase History:")
    history = run_data.get("phase_history", [])
    if not history:
        click.echo("  (no phases executed yet)")
    else:
        for h in history:
            cost = h.get("cost", {})
            tokens = f"{cost.get('inputTokens', 0)}in/{cost.get('outputTokens', 0)}out"
            arts = h.get("artifact_ids", [])
            click.echo(
                f"  - {h['phase']:<12} attempt {h['attempt']} [{h['status'].upper():<7}] arts: {len(arts)} | tokens: {tokens} | at: {h.get('completed_at', h.get('started_at', ''))}"
            )

    # Artifacts
    click.echo("\nArtifacts:")
    artifacts = run_data.get("artifacts", {})
    if not artifacts:
        click.echo("  (none)")
    else:
        for key, art in artifacts.items():
            click.echo(
                f"  - {key:<16} v{art.get('version', 1):03d} [{art.get('verdict', 'info')}] -> {art.get('content_uri')}"
            )

    # Findings
    click.echo("\nOpen Findings:")
    open_findings = run_data.get("findings", {}).get("open", [])
    if not open_findings:
        click.echo("  (none)")
    else:
        for f in open_findings:
            click.echo(
                f"  - [{f.get('severity', 'info').upper()}] ({f.get('phase')}) {f.get('title')}: {f.get('description', '')}"
            )

    # Budget
    budget = run_data.get("budget", {})
    click.echo(f"\nBudget & Tokens:")
    click.echo(
        f"  Total In: {budget.get('tokens_in', 0)} | Total Out: {budget.get('tokens_out', 0)} | Actual Cost: ${budget.get('actual', 0.0):.4f} / Cap: ${budget.get('cap', 100.0):.2f}"
    )


@cli.command()
def runs():
    """List all runs stored in SQLite state."""
    workspace = os.getcwd()
    sm = StateManager(workspace)
    all_runs = sm.list_runs()
    active_id = sm.get_active_run_id()

    if not all_runs:
        click.echo("No runs found in workspace.")
        return

    click.echo(f"{'ACTIVE':<8} {'RUN ID':<30} {'PHASE':<12} {'STATUS':<10} {'CREATED AT':<25}")
    click.echo("-" * 88)
    for r in all_runs:
        is_active = "*" if r["run_id"] == active_id else " "
        click.echo(
            f"{is_active:<8} {r['run_id']:<30} {r['current_phase']:<12} {r['current_status']:<10} {r['created_at']:<25}"
        )


def main():
    cli()


if __name__ == "__main__":
    main()

