# AIDLC — AI-Driven Development Lifecycle (Phase A)

AIDLC is an installable CLI (`aidlc`) implementing **Phase A ("Core execution engine")** of the AIDLC end-to-end architecture specification (`aidlc.md`).

## Phase A Scope

Phase A implements:
- **Orchestrator**: Directed state graph executor (`intake` → `spec` → `build` → `verify` → `completed`), retry budgets (build: 4, verify: 3), and human gate halts.
- **Shared Lifecycle State**: SQLite-backed state store (`.aidlc/state.db`) tracking runs, phase history, artifacts, open findings, and token/cost budgets.
- **Artifact Store**: Append-only filesystem storage (`.aidlc/artifacts/`) with monotonic versioning (`.v001.md`, `.v001.json`), SHA-256 checksums, and unversioned aliases.
- **Tool Gateway**: Least-privilege phase-scoped tool dispatch for filesystem I/O, shell execution, artifacts, and engineering findings.
- **Phase Agents**:
  - `intake`: Extracts requirements, problem statement, user actors, constraints, and acceptance signals.
  - `spec`: Two-mode engineering spec derivation:
    - **Mode A (agent_generated)**: Decomposes intake requirements into user stories, acceptance criteria (Given/When/Then), scope boundaries, and DoD.
    - **Mode B (human_supplied)**: Normalizes human-provided stories and checks for contradictions against intake constraints. If a contradiction is detected, records a `blocker` finding and halts with `blocked` status.
  - `build`: Generates Python source code and automated tests.
  - `verify`: Executes `pytest -v` via `run_command`, records results, and creates verification report.
  - `stubs`: Explicit `NotImplementedError` for Phase B/C/D phases (`scaffold`, `analyze-risks`, `create-test-plan`, etc.).

---

## Installation

Requirements: Python >= 3.10.

```bash
# Clone or navigate to the repository directory
cd /path/to/project

# Install in editable mode
pip install -e .
```

---

## Provider Resolution Priority

AIDLC resolves LLM providers strictly without silent fallback:
1. `--provider <anthropic|agy|mock>` CLI flag.
1. `--provider <anthropic|openai|codex|agy|mock>` CLI flag.
2. `ANTHROPIC_API_KEY` environment variable (uses Claude 3.5 Sonnet).
3. Authenticated local `agy` CLI session (`~/.local/bin/agy` or `PATH`).
4. **Loud explicit error**: if neither Anthropic key nor agy is available, AIDLC halts with an error. The mock adapter is only used when `--provider mock` is explicitly provided.
3. `OPENAI_API_KEY` environment variable (uses OpenAI GPT-4o / Codex).
4. Authenticated local `agy` CLI session (`~/.local/bin/agy` or `PATH`).
5. **Loud explicit error**: if no configured provider is found, AIDLC halts with an explicit error. The mock adapter is only used when `--provider mock` is explicitly provided.

---

## Usage & Commands

### 1. Initialize Workspace
```bash
aidlc init
```
Creates `.aidlc/state.db` and the initial active run.

### 2. Run Intake
```bash
aidlc run intake --ask "Build a CLI calculator function with addition and subtraction"
```
Produces `artifacts/<run_id>/intake/intake.v001.md` and `intake.v001.json`.

### 3. Run Spec (Mode A — Agent Generated)
```bash
aidlc run spec --mode agent_generated
```
Produces `artifacts/<run_id>/spec/spec.v001.md`.

### 4. Run Spec (Mode B — Human Supplied)
```bash
# Compatible stories
aidlc run spec --mode human_supplied --stories "As a user I want add and subtract CLI operations"

# Contradicting stories (escalates blocker and halts)
aidlc run spec --mode human_supplied --stories "Build a Python Flask web API microservice"
```

### 5. Run Build
```bash
aidlc run build
```
Generates implementation files and `pytest` test suites.

### 6. Run Verify
```bash
aidlc run verify
```
Executes `pytest -v` and records verification report artifact.

### 7. Run Full Pipeline
```bash
aidlc run intake --ask "Build a CLI calculator function" --pipeline
```

### 8. Inspect Run Status & History
```bash
# View active run details, history, artifacts, and findings
aidlc status

# List all runs in state.db
aidlc runs
```

