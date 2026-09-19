# AIDLC Command Execution Guide

This guide outlines the exact sequence of commands to execute the 12-phase AI-Driven Development Lifecycle (AIDLC).

---

## 🚀 Quick Start (Complete Autonomous Pipeline)

If you want the framework to run all 12 phases autonomously from start to finish:

### Step 1: Initialize Project
```bash
aidlc init
```
- Creates `.aidlc/state.db` and the active run.
- Generates the discovery questionnaire: `./interview.md`.

### Step 2: Edit `interview.md`
Open `./interview.md` in your editor:
1. Fill in your project name, problem statement, and desired features (Sections 1 & 4).
2. Mark your choices with an `[x]` (e.g. `[x] **TDD**`, `[x] **CLI Application**`) in Sections 2 & 3.
3. Save the file.

### Step 3: Run the Complete Pipeline
```bash
aidlc run intake --pipeline
```
- Auto-detects `./interview.md`.
- Displays the alignment summary and asks: `Is everything good with the intake specification and architectural interview to proceed? [Y/n]`.
- Press **Enter** (or `y`), and it will run through all 12 phases in sequence.

*(To skip the terminal confirmation prompt, pass `-y`: `aidlc run intake --pipeline -y`)*

---

## 📋 Step-by-Step Execution (Phase-by-Phase Order)

If you prefer to run and inspect each phase individually, execute them in this exact order:

```text
intake ──▶ scaffold ──▶ spec ──▶ analyze-risks ──▶ create-test-plan ──▶ test-design ──▶ build ──▶ adversarial-review ──▶ verify ──▶ align ──▶ release ──▶ retro
```

### 1. Intake Phase
Parses `./interview.md` and generates official requirements artifacts (`intake.v001.md`, `interview.v001.md`).
```bash
aidlc run intake
```

### 2. Scaffold Phase
Selects technology stack, creates project directory structure (`src/`, `tests/`), and writes `stack-manifest.json`.
```bash
aidlc run scaffold
```

### 3. Spec Phase
Decomposes requirements into user stories and formal Gherkin acceptance criteria (Given/When/Then).
```bash
aidlc run spec
```

### 4. Risk Analysis Phase
Attacks the specification across 4 red-team lenses: ambiguity, edge cases, scope drift, and security preflight.
```bash
aidlc run analyze-risks
```

### 5. Test Plan Phase
Formulates test strategy and builds the Acceptance Criteria (AC) verification matrix.
```bash
aidlc run create-test-plan
```

### 6. Test Design Phase *(Test-First / TDD / BDD)*
Writes concrete automated test suites in `tests/test_*.py` **before** the implementation code is created.
```bash
aidlc run test-design
```
*Alias:*
```bash
aidlc run create-tests
```

### 7. Build Phase
Implements source code in `src/` (or `generated/`) specifically designed to satisfy the specs and pass the designed test suites.
```bash
aidlc run build
```

### 8. Adversarial Red-Team Review Phase
Independent criticism layer evaluating the implementation diff for bugs, vulnerabilities, and spec compliance.
```bash
aidlc run adversarial-review
```
*Aliases:*
```bash
aidlc run red_team_review
# or
aidlc run red-team-review
```
*(If critical defects are found, the state machine automatically loops back to `build`).*

### 9. Verification Phase
Executes the automated test runner (`pytest -v`), verifies all test assertions pass, and compiles AC traceability evidence.
```bash
aidlc run verify
```

### 10. Semantic Alignment Phase
Validates intent alignment: *"Did we build what the stakeholder actually asked for?"* Checks for requirement and scope drift.
```bash
aidlc run align
```

### 11. Release Phase
Packages the verified software, bumps version, generates release notes, and writes `CHANGELOG.md`.
```bash
aidlc run release
```

### 12. Retrospective Phase
Closes the lifecycle: synthesizes run telemetry, evaluates retry counts, extracts failure patterns, and recommends system improvements.
```bash
aidlc run retro
```

---

## 🔍 Status & Inspection Commands

Check the active run and past runs at any point:

```bash
# View active phase, phase history, and generated artifacts
aidlc status

# List all past runs and timestamps
aidlc runs
```

---

## 📁 Artifact Locations

Every phase produces versioned, immutable artifacts in `.aidlc/artifacts/<run_id>/`:
- `.aidlc/artifacts/<run_id>/intake/intake.v001.md`
- `.aidlc/artifacts/<run_id>/scaffold/scaffold.v001.md`
- `.aidlc/artifacts/<run_id>/spec/spec.v001.md`
- `.aidlc/artifacts/<run_id>/analyze-risks/risk-report.v001.md`
- `.aidlc/artifacts/<run_id>/create-test-plan/test-plan.v001.md`
- `.aidlc/artifacts/<run_id>/test-design/test-design.v001.md`
- `.aidlc/artifacts/<run_id>/build/build.v001.md`
- `.aidlc/artifacts/<run_id>/adversarial-review/review-report.v001.md`
- `.aidlc/artifacts/<run_id>/verify/verify-report.v001.md`
- `.aidlc/artifacts/<run_id>/align/align-report.v001.md`
- `.aidlc/artifacts/<run_id>/release/release-manifest.v001.md`
- `.aidlc/artifacts/<run_id>/retro/retro.v001.md`

---

## ⚙️ Provider Options

By default, `aidlc` resolves providers in this priority:
1. Explicit `--provider` flag
2. `ANTHROPIC_API_KEY` (Anthropic API)
3. `agy` CLI (Google Antigravity model provider)
2. `ANTHROPIC_API_KEY` (Anthropic Claude API)
3. `OPENAI_API_KEY` (OpenAI GPT-4o / Codex API)
4. `agy` CLI (Google Antigravity model provider)

To override the provider for any run:
```bash
# Run with Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
aidlc run intake --provider anthropic

# Run with OpenAI / Codex
export OPENAI_API_KEY="sk-..."
aidlc run intake --provider openai
# (or: aidlc run intake --provider codex)

# Run with Antigravity
aidlc run intake --provider agy

# Run with Anthropic Claude
aidlc run intake --provider anthropic

# Run with fast mock provider (offline testing)
aidlc run intake --provider mock
```
