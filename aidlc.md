# AIDLC — End-to-End AI-Driven Development Lifecycle
## Production Architecture Reference

> **Purpose:** Define a complete multi-agent software-engineering framework that takes a raw request from intake to a released, verified, auditable change.
>
> **Lifecycle:**
>
> `intake → scaffold → spec → analyze-risks → create-test-plan → test-design → build → adversarial-review → verify → align → release → retro`

This design extends the initial graph-based concept into an **end-to-end engineering operating system**. Each phase is an agent-controlled subgraph; the overall lifecycle is an orchestrated state machine with durable artifacts, bounded retries, human gates, Git awareness, observability, policy enforcement, and release traceability.

---

# 1. Architecture Principles

## 1.1 The lifecycle is a graph, not a script

Do not implement the pipeline as:

```text
phase1()
phase2()
phase3()
...
```

Implement it as a **directed state graph**:

```text
                         ┌──────────────┐
                         │    intake    │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   scaffold   │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │     spec     │
                         └──────┬───────┘
                                │
                                ▼
                      ┌────────────────────┐
                      │   analyze-risks    │
                      └─────────┬──────────┘
                                │
                         blockers? ────────┐
                                │           │
                               no           │yes
                                │           │
                                ▼           │
                      ┌─────────────────┐   │
                      │ create-test-plan│   │
                      └────────┬────────┘   │
                               │             │
                               ▼             │
                        ┌─────────────┐      │
                        │ test-design │      │
                        └──────┬──────┘      │
                               │             │
                               ▼             │
                          ┌─────────┐         │
                          │  build  │◄────────┘
                          └────┬────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │ adversarial-review │
                    └─────────┬──────────┘
                              │
                         fail? ───────────► build
                              │
                             pass
                              │
                              ▼
                         ┌────────┐
                         │ verify │
                         └───┬────┘
                             │
                        fail? ─────────────► build
                             │
                            pass
                             │
                             ▼
                         ┌────────┐
                         │ align  │
                         └───┬────┘
                             │
                     intent drift? ───────► spec
                             │
                             ▼
                         ┌─────────┐
                         │ release │
                         └────┬────┘
                              │
                              ▼
                          ┌────────┐
                          │ retro  │
                          └───┬────┘
                              │
                              ▼
                             END
```

### Core rule

**The LLM chooses inside a phase; the orchestrator chooses between phases.**

This keeps execution deterministic and auditable.

---

# 2. System-Level Architecture

## 2.1 Major components

```text
┌─────────────────────────────────────────────────────────────────┐
│                         USER / DEVELOPER                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API / CLI / UI                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LIFECYCLE ORCHESTRATOR                     │
│                                                                 │
│  StateGraph • phase routing • retries • budgets • gates         │
└──────┬───────────────────┬──────────────────┬───────────────────┘
       │                   │                  │
       ▼                   ▼                  ▼
┌─────────────┐     ┌──────────────┐   ┌────────────────┐
│ Agent Layer │     │ Policy Layer │   │ Context Layer  │
│             │     │              │   │                │
│ phase agents│     │ approvals    │   │ repo/context   │
│ sub-agents  │     │ permissions  │   │ retrieval      │
│ critic loops│     │ budgets      │   │ memory         │
└──────┬──────┘     └──────┬───────┘   └───────┬────────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        TOOL GATEWAY                              │
│                                                                 │
│ Git • Files • Shell • Tests • Build • Security • Cloud • CI/CD  │
└──────────┬─────────────────────┬─────────────────┬───────────────┘
           │                     │                 │
           ▼                     ▼                 ▼
┌─────────────────┐   ┌──────────────────┐  ┌────────────────────┐
│ Artifact Store  │   │ Workspace / Repo │  │ Observability      │
│                 │   │                  │  │                    │
│ immutable docs  │   │ working tree     │  │ traces             │
│ reports         │   │ branches         │  │ logs               │
│ manifests       │   │ generated code   │  │ metrics            │
│ evidence        │   │ tests            │  │ costs              │
└─────────────────┘   └──────────────────┘  └────────────────────┘
```

---

# 3. The Core Abstraction: Agent → Skill → Tool

Use three layers.

```text
AGENT
  │
  ├── Skill A
  │     ├── Tool 1
  │     └── Tool 2
  │
  ├── Skill B
  │     ├── Tool 3
  │     └── Tool 4
  │
  └── Skill C
        └── Tool 5
```

## Agent

The agent owns:

- goal
- phase contract
- reasoning loop
- skill selection
- stopping conditions
- escalation behavior
- final phase verdict

## Skill

A reusable unit of engineering judgment.

Examples:

- requirement extraction
- architecture decomposition
- threat modeling
- test-case generation
- code implementation
- semantic diffing

A skill should describe **what good looks like**, not how a specific API works.

## Tool

A mechanical capability.

Examples:

- `read_file`
- `write_file`
- `git_diff`
- `run_tests`
- `run_linter`
- `run_security_scan`
- `create_branch`
- `open_pr`
- `deploy`

The model should not directly execute uncontrolled shell commands. Put tools behind a **Tool Gateway** with policy checks.

---

# 4. Shared Lifecycle State

Every run carries a durable state object.

```yaml
RunState:
  run_id: string
  project_id: string
  story_id: string

  phase:
    current: string
    status: pending|running|blocked|passed|failed

  phase_history:
    - phase: string
      attempt: integer
      status: string
      started_at: timestamp
      completed_at: timestamp
      artifact_ids: []
      findings: []
      cost: {}

  artifacts:
    intake: ArtifactRef
    scaffold: ArtifactRef
    spec: ArtifactRef
    risk_report: ArtifactRef
    test_plan: ArtifactRef
    test_design: ArtifactRef
    implementation: ArtifactRef
    review_report: ArtifactRef
    verify_report: ArtifactRef
    align_report: ArtifactRef
    release_manifest: ArtifactRef
    retro: ArtifactRef

  git:
    repository: string
    base_commit: string
    working_branch: string
    changed_files: []
    active_conflicts: []

  budget:
    cap: number
    estimated: number
    actual: number
    tokens_in: integer
    tokens_out: integer
    tool_cost: number

  gates:
    required: []
    approved: []

  findings:
    open: []
    resolved: []
    accepted_risk: []

  metadata:
    actor: string
    environment: string
    created_at: timestamp
```

### Important rule

`phase_history` and artifacts are **append-only**.

Never overwrite:

```text
risk-report.md
```

Instead create:

```text
risk-report.v001.md
risk-report.v002.md
```

or use immutable artifact IDs with a logical alias:

```text
artifact_id = art_8f4...
logical_name = risk-report
version = 2
```

---

# 5. Artifact-First Architecture

The artifact store is the backbone of the system.

Every phase must answer:

1. What did I consume?
2. What did I produce?
3. What evidence supports the output?
4. What decision did I make?
5. Why was that decision made?

Each artifact should carry metadata:

```yaml
artifact:
  id: art_123
  type: risk_report
  project_id: proj_123
  story_id: story_456
  phase: analyze-risks
  version: 3

  created_at: timestamp
  created_by_agent: risk-agent
  parent_artifacts:
    - art_spec_v2
    - art_intake_v1

  content_uri: artifact://...
  checksum: sha256:...

  verdict: pass|fail|warning|info

  evidence:
    - source: spec.md
      locator: "AC-04"
```

This gives you complete provenance:

```text
user request
    ↓
intake v1
    ↓
spec v2
    ↓
risk report v1
    ↓
test plan v1
    ↓
test design v1
    ↓
implementation commit abc123
    ↓
review report v2
    ↓
verify report v1
    ↓
align report v1
    ↓
release manifest v1
```

---

# 6. Recommended Repository / Workspace Layout

The framework should maintain two distinct areas:

1. **Product repository** — generated/modified application code.
2. **AIDLC control workspace** — lifecycle artifacts, evidence, state and traces.

Recommended layout:

```text
project/
├── interview.md              # Discovery questionnaire generated at `aidlc init` for project description & methodology
├── .aidlc/
│   ├── run.yaml
│   ├── state/
│   │   ├── current.json
│   │   └── history/
│   │
│   ├── artifacts/
│   │   ├── intake/
│   │   ├── scaffold/
│   │   ├── spec/
│   │   ├── risks/
│   │   ├── test-plan/
│   │   ├── test-design/
│   │   ├── build/
│   │   ├── review/
│   │   ├── verify/
│   │   ├── align/
│   │   ├── release/
│   │   └── retro/
│   │
│   ├── evidence/
│   │   ├── test-results/
│   │   ├── security/
│   │   ├── build/
│   │   ├── coverage/
│   │   └── deployment/
│   │
│   ├── traces/
│   ├── prompts/
│   ├── policies/
│   └── manifests/
│
├── src/
├── tests/
├── docs/
├── scripts/
├── infra/
└── .github/
```

For production, artifacts can also be stored externally:

```text
Artifact Store
   ├── object storage: actual files
   ├── relational DB: metadata + lineage
   └── vector/index store: retrieval
```

The repo `.aidlc/` folder can contain the local manifest and pointers.

---

# 7. Phase Architecture

# 7.1 Intake Agent

## Goal

Convert a raw request into a structured engineering problem.

## Inputs

- `interview.md` (developer-authored or pre-filled discovery interview in workspace root)
- user request / optional `--ask` CLI override
- conversation context
- attached documents
- project metadata
- organization policies
- optional existing issue/ticket

## Skills

### Skill 1 — Clarifying-question generation

Purpose:

- find missing information
- identify ambiguity
- distinguish required from optional information

Tools:

- `read_prior_context`
- `read_attachment`
- `read_project_metadata`

### Skill 2 — Requirement extraction

Extract:

- problem
- user/persona
- desired behavior
- functional requirements
- non-functional requirements
- constraints
- acceptance signals
- dependencies

Tools:

- `structure_requirements`
- `write_artifact`

### Skill 3 — Constraint identification

Identify:

- deadline
- budget
- security requirements
- regulatory requirements
- technology constraints
- deployment constraints

Tools:

- `read_org_policy`
- `read_project_policy`
- `write_artifact`

## Output

```text
.aidlc/artifacts/intake/intake.v001.md
.aidlc/artifacts/intake/intake.v001.json
.aidlc/artifacts/intake/interview.v001.md
.aidlc/artifacts/intake/interview.v001.json
```

### Artifacts

#### 1. `intake.md` (Requirements Specification)

Suggested structure:

```text
Problem
User / Actor
Desired Outcome
Functional Requirements
Non-Functional Requirements
Constraints
Dependencies
Open Questions
Assumptions
Success Criteria
```

#### 2. `interview.md` (Discovery & Architectural Alignment Interview)

Foundational architectural discovery artifact produced during Intake to validate technical alignment, methodology, and trade-offs before entering specification.

Suggested structure:

```text
# Discovery & Architectural Alignment Interview: <Title>

## 1. Project Vision & Core Description
- Clarified problem statement, target audience, and primary success metric.

## 2. Methodology & Driven-Development Selection
- Evaluation of development paradigm options:
  - TDD (Test-Driven Development): Red-Green-Refactor, test-first design.
  - BDD (Behavior-Driven Development): User story and scenario-first Given-When-Then criteria.
  - CDD (Contract-Driven Development): API/schema interface contracts first.
  - EDD (Event-Driven Development): Asynchronous event/message decoupled architecture.
  - DDD (Domain-Driven Design): Domain aggregates, ubiquitous language, and entity modeling.
- Selected methodology, reasoning, and implementation implications.

## 3. Architectural Style & Interface Boundaries
- Target form factor (CLI tool, HTTP microservice, SDK library, worker daemon).
- State and persistence needs (stateless, SQLite, object store, in-memory).
- Dependency boundaries (zero-dependency standard library vs curated ecosystem).

## 4. Testing & Quality Strategy
- Test pyramid distribution (unit, integration, end-to-end).
- Coverage targets and test harness expectations.

## 5. Non-Functional Priorities & Trade-Offs
- Latency and performance constraints.
- Portability across operating systems and shells.
- Error handling posture (fail-fast vs graceful degradation).

## 6. Alignment Status & Pre-populated Defaults
- Suggested answers pre-populated based on raw ask, ready for human sign-off.
```

### Human-in-the-Loop (HITL) Discovery Gate

Upon generating `intake.md` and `interview.md`, the framework presents an alignment summary to the user and prompts for explicit confirmation (`Is everything good? [Y/n]`). This ensures developer intent and methodology choices are verified before triggering the Spec Agent.

## Route

```text
intake → scaffold / spec
```

Escalate to human when:

- critical requirement is missing
- request contradicts policy
- budget/timeline is impossible
- user declines interview confirmation gate

---

# 7.2 Scaffold Agent

## Goal

Create the initial engineering workspace from scratch.

## Skills

### Skill 1 — Stack selection

Inputs:

- intake
- organization defaults
- supported platform matrix

Tools:

- `read_artifact`
- `inspect_supported_stacks`
- `propose_stack`

### Skill 2 — Repository structure generation

Tools:

- `create_directory`
- `write_file`
- `initialize_git`

### Skill 3 — CI/tooling setup

Generate:

- formatter configuration
- linter
- test runner
- type checker
- CI workflow
- dependency management
- pre-commit hooks where appropriate

Tools:

- `write_file`
- `validate_config`
- `run_local_checks`

## Output

```text
.aidlc/artifacts/scaffold/scaffold.v001.md
.aidlc/artifacts/scaffold/stack-manifest.json
```

Product repo:

```text
src/
tests/
docs/
infra/
.github/
...
```

## Route

```text
scaffold → spec
```

---

# 7.3 Spec Agent

## Goal

Create the authoritative engineering specification — either by generating stories from
prior artifacts, or by formalizing stories the human supplies directly.

## Story-Sourcing Modes

Before any generation skill runs, the agent resolves which of two modes this run is in.
The mode is a property of the *run*, not a permanent agent setting — everything after the
fork is mode-agnostic.

**Mode A — Agent-generated.** Default. The agent derives stories entirely from
`intake.md` (and `scaffold.md` if present).

**Mode B — Human-supplied.** The human writes or pastes the stories themselves. The
agent's job shifts from *generating* to *formalizing and validating* — mapping informal
story text into the same structured schema Mode A would have produced, catching gaps,
never silently inventing scope the human didn't ask for.

```yaml
spec_mode: agent_generated | human_supplied
```

Set either explicitly on the intake artifact (`intake.story_source`), or resolved by a
one-question HITL prompt at the start of this phase if intake didn't specify it:
*"Do you want to write the stories yourself, or should I generate them from intake?"*

## Skills

### Skill 0 — Mode resolution (routing gate, not a generation skill)

Reads `intake.story_source` if present; otherwise asks the human once. Routes to Skill 1A
or Skill 1B. Runs exactly once per run, before either path.

Tools: `read_artifact(intake)`, `ask_user`

---

**Path A — Agent-generated**

### Skill 1A — Story decomposition

Convert the intake into:

```text
Epic
 ├── Story 1
 ├── Story 2
 └── Story 3
```

Tools: `read_artifact(intake)`, `write_artifact`

---

**Path B — Human-supplied**

### Skill 1B — Story ingestion & normalization

Purpose:

- accept human-written stories (free text, template, or structured input)
- map them into the same Epic → Story schema Path A would have produced
- flag anything the human's stories don't cover but intake implies (e.g. a stated
  non-functional requirement that no supplied story addresses)

Tools: `read_human_input`, `read_artifact(intake)`, `structure_requirements`,
`flag_finding`

**Escalation:** if a human-supplied story directly contradicts an intake constraint, this
is a `blocker` finding, not a silent override. The story passes through unedited, with the
contradiction flagged — a human decides, the agent doesn't overrule the human's own input.

---

Both paths converge here — everything downstream no longer knows or cares which mode
produced the stories:

### Skill 2 — Acceptance criteria generation

- Path A: generate ACs from scratch for every story.
- Path B: generate ACs only where the human didn't supply their own; where they did,
  *validate* (testable? unambiguous?) rather than replace.

Prefer:

```text
Given
When
Then
```

Tools: `generate_acs`, `read_artifact(spec_draft)`, `flag_finding`

### Skill 3 — Scope / UI / interface drafting

Depending on project type:

- APIs
- UI elements
- data contracts
- events
- workflows
- error behavior
- permissions

## Output

```text
.aidlc/artifacts/spec/spec.v001.md
.aidlc/artifacts/spec/spec.v001.json
```

`spec.md` should contain:

```text
Summary
Business Context
Problem
Actors
Story Source: agent_generated | human_supplied
Stories
Scope
Out of Scope
UI / API / Event Elements
Data Requirements
Constraints
Assumptions
Acceptance Criteria
Definition of Done
Test Notes
```

`Story Source` matters downstream: it tells `analyze-risks` how to word a finding — "the
agent assumed X" reads and gets resolved differently than "the human specified X, worth
confirming."

## Route

```text
spec → analyze-risks
```

Additional edge: if Skill 1B raises a blocker (human story contradicts intake), route to
a HITL gate first — a contradiction in the human's own input needs a human decision, not
just a logged finding passed downstream.

---

# 7.4 Analyze-Risks Agent

## Goal

Attack the specification before code is written.

This should be a **multi-lens red-team**, not one generic review.

## Internal reviewers

```text
                  analyze-risks
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     ambiguity     edge cases    scope drift
          │            │            │
          ├────────────┼────────────┤
                       ▼
                 findings merger
```

## Skills

### Ambiguity detection

Look for:

- undefined words
- conflicting requirements
- missing error behavior
- missing ownership
- vague acceptance criteria

### Edge-case analysis

Check:

- empty input
- null values
- duplicates
- concurrency
- retries
- partial failures
- timeouts
- large payloads
- permissions
- invalid state transitions

### Scope-creep detection

Compare:

```text
intake ↔ spec
```

Detect:

- feature expansion
- hidden requirements
- unsupported assumptions

### Security preflight

Recommended additional lens:

- auth/authz
- secrets
- PII
- injection surfaces
- unsafe file access
- tenant isolation
- external calls

## Output

```text
.aidlc/artifacts/risks/risk-report.v001.md
.aidlc/artifacts/risks/risk-report.v001.json
```

Each finding:

```yaml
id: RISK-004
severity: blocker
category: ambiguity
location: AC-07
description: ...
impact: ...
recommendation: ...
```

## Routing

```text
no blockers → create-test-plan
blockers    → spec
warnings    → create-test-plan OR human gate depending on policy
```

---

# 7.5 Create-Test-Plan Agent

## Goal

Create the **test strategy**, not test code.

## Skills

### Skill 1 — AC-to-test mapping

For every AC identify:

- unit test
- integration test
- API test
- UI test
- contract test
- security test
- performance test
- e2e test

### Skill 2 — Coverage-gap analysis

Enforce:

```text
every AC → ≥ 1 verification mechanism
```

Also detect:

```text
high-risk area → stronger test type
```

## Output

```text
.aidlc/artifacts/test-plan/test-plan.v001.md
.aidlc/artifacts/test-plan/coverage-matrix.json
```

Example matrix:

```text
AC-01 → unit + integration
AC-02 → API contract
AC-03 → e2e
AC-04 → security + integration
```

## Route

```text
create-test-plan → test-design
```

---

# 7.6 Test-Design Agent

## Goal

Create tests **before implementation**.

This makes the framework test-first by default.

## Skills

### Skill 1 — Test case generation

Generate deterministic cases from:

- ACs
- risk report
- test plan
- architecture assumptions

### Skill 2 — Fixture / mock design

Generate:

- test data
- fixtures
- mocks
- stubs
- test factories

### Skill 3 — Failure expectation

Run the tests against the empty/scaffolded implementation where useful.

The framework should record:

```text
expected failure = valid
unexpected infrastructure failure = invalid
```

## Output

Product repo:

```text
tests/
```

Control artifact:

```text
.aidlc/artifacts/test-design/test-design.v001.md
.aidlc/artifacts/test-design/test-map.json
```

Evidence:

```text
.aidlc/evidence/test-results/test-design-baseline.json
```

## Route

```text
test-design → build
```

---

# 7.7 Build Agent

## Goal

Implement the feature against the spec and tests.

## Critical design

The Build Agent should **not be one giant coding prompt**.

Use an internal loop:

```text
inspect → plan → edit → run checks → diagnose → edit → summarize
```

## Skills

### Skill 1 — Repository reconnaissance

Tools:

- `git_status`
- `git_log`
- `git_grep`
- `read_file`
- `search_symbols`

Goal:

understand existing patterns before changing code.

### Skill 2 — Implementation planning

Produce an internal implementation plan:

```text
files to change
interfaces
data model
control flow
test impact
migration impact
```

### Skill 3 — Code generation

Tools:

- `write_file`
- `apply_patch`

### Skill 4 — Local validation

Tools:

- `run_tests`
- `run_lint`
- `run_typecheck`
- `run_build`

### Skill 5 — Refactoring / consistency

Check:

- naming
- module boundaries
- error handling
- logging
- dependency usage
- project conventions

### Git Context Add-on

Before modifications:

```text
active branches
recent commits
working tree
overlapping file changes
```

## Output

Primary output is the actual repository change:

```text
git diff
```

Control artifact:

```text
.aidlc/artifacts/build/build.v001.md
.aidlc/artifacts/build/implementation-manifest.json
```

Evidence:

```text
.aidlc/evidence/build/build-checks.json
```

## Route

```text
build → adversarial-review
```

---

# 7.8 Adversarial-Review Agent

## Goal

Try to break the implementation.

This is the framework's main **independent criticism layer**.

Do not make the same agent that generated code the sole judge of the code.

## Internal review lenses

```text
                    implementation diff
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
   correctness          security            maintainability
        │                   │                    │
        └───────────────────┼────────────────────┘
                            ▼
                       spec compliance
                            │
                            ▼
                      concurrency/Git
                            │
                            ▼
                     findings merger
```

## Skills

### Skill 1 — Diff retrieval

Tools:

- `git_diff`
- `git_show`
- `read_file`

### Skill 2 — Spec compliance

Map:

```text
AC → changed code → evidence
```

### Skill 3 — Security review

Check:

- auth bypass
- injection
- secret exposure
- unsafe deserialization
- path traversal
- SSRF
- insecure defaults
- excessive privileges
- data leakage

### Skill 4 — Reliability review

Check:

- race conditions
- retry storms
- idempotency
- resource leaks
- transaction boundaries
- timeout handling
- partial failure behavior

### Skill 5 — Git conflict review

Detect overlapping unmerged changes.

## Output

```text
.aidlc/artifacts/review/review-report.v001.md
.aidlc/artifacts/review/findings.v001.json
```

Verdict:

```text
PASS
PASS_WITH_WARNINGS
FAIL
```

## Route

```text
PASS             → verify
PASS_WITH_WARNING→ verify OR human gate by severity
FAIL             → build
```

Bound retries:

```text
MAX_BUILD_REVIEW_LOOPS = configurable
```

---

# 7.9 Verify Agent

## Goal

Prove that the implementation works.

This phase should be substantially more mechanical than semantic review.

## Skills

### Skill 1 — Test execution

Run:

- unit
- integration
- contract
- e2e
- regression
- security checks

### Skill 2 — Test result interpretation

Collect:

```text
passed
failed
skipped
flaky
infrastructure error
```

Do not classify an infrastructure outage as a product failure.

### Skill 3 — AC traceability

Build:

```text
AC-01
  ├── test T-11
  └── evidence E-91

AC-02
  ├── test T-14
  └── evidence E-94
```

## Output

```text
.aidlc/artifacts/verify/verify-report.v001.md
.aidlc/artifacts/verify/traceability.v001.json
```

Evidence:

```text
.aidlc/evidence/test-results/
.aidlc/evidence/coverage/
.aidlc/evidence/security/
```

## Route

```text
PASS → align
FAIL → build
```

Important:

A test failure should create a structured finding:

```yaml
id: VERIFY-003
type: failed_test
test: test_create_user_invalid_email
likely_area:
  - validation
  - schema
evidence:
  logs: ...
```

That finding becomes input to the next Build attempt.

---

# 7.10 Align Agent

## Goal

Answer:

> "Did we build the thing the stakeholder actually wanted?"

Passing tests is not enough.

## Skills

### Skill 1 — Semantic diff

Compare:

```text
intake
spec
implementation
verify report
```

Ask:

- Does the behavior match intent?
- Did implementation interpret requirements too literally?
- Did important user outcomes disappear?
- Is the UX / API behavior actually useful?

### Skill 2 — Stakeholder perspective

Simulate the requester:

```text
Would the original requester look at this and say:
"Yes, this solves my problem"?
```

### Skill 3 — Drift detection

Detect:

- requirement drift
- scope drift
- unexpected behavior
- accidental feature addition
- missing user-visible behavior

## Output

```text
.aidlc/artifacts/align/align-report.v001.md
.aidlc/artifacts/align/semantic-trace.v001.json
```

Verdict:

```text
ALIGNED
DRIFT
ALIGNED_WITH_WARNING
```

## Route

```text
ALIGNED → release
DRIFT   → spec
```

This is intentionally the most expensive backward edge because it means the solution or requirement itself needs reconsideration.

---

# 7.11 Release Agent

## Goal

Turn verified code into a releasable software artifact.

## Skills

### Skill 1 — Release readiness

Confirm:

- verify passed
- review passed
- alignment passed
- required approvals exist
- security gates pass
- versioning is valid

### Skill 2 — Versioning

Tools:

- `bump_version`
- `git_tag`

### Skill 3 — Changelog generation

Input:

- spec
- implementation diff
- phase history
- release metadata

Output:

```text
CHANGELOG
release notes
migration notes
```

### Skill 4 — Packaging

Tools:

- `build_package`
- `build_container`
- `publish_artifact`

### Skill 5 — Deployment

Tools:

- `deploy`
- `health_check`
- `rollback`

## Output

```text
.aidlc/artifacts/release/release-manifest.v001.json
.aidlc/artifacts/release/release-notes.v001.md
.aidlc/evidence/deployment/deploy-result.v001.json
```

Example release manifest:

```yaml
release_id: rel_2026_001
version: 1.4.0
commit: abc123
artifacts:
  container: registry/app:1.4.0
environment: production
verification:
  verify: PASS
  security: PASS
  alignment: PASS
deployment:
  status: SUCCESS
```

## Route

```text
release → retro
```

---

# 7.12 Retro Agent

## Goal

Close the lifecycle and improve the system itself.

The retro should learn from **the entire execution**, not just the implementation.

## Skills

### Skill 1 — Phase history summarization

Extract:

- total attempts
- blocked phases
- backward edges
- failures
- cost
- elapsed time

### Skill 2 — Pattern extraction

Compare findings:

```text
risk report
review report
verify report
align report
```

Look for recurrence.

Example:

```text
Pattern:
API validation requirements are repeatedly underspecified.

Action:
strengthen intake/spec skill with explicit input-validation checklist.
```

### Skill 3 — Prompt / policy refinement suggestions

The retro can suggest updates to:

- skill prompts
- checklists
- policy rules
- templates
- routing thresholds

But **do not automatically mutate production prompts**.

Use a controlled improvement workflow.

## Output

```text
.aidlc/artifacts/retro/retro.v001.md
.aidlc/artifacts/retro/learning-signals.v001.json
```

Optional:

```text
.aidlc/artifacts/retro/prompt-improvement-proposals/
```

## Route

```text
retro → END
```

---

# 8. Cross-Cutting Services

These are not normal lifecycle phases.

They are platform services available to agents.

# 8.1 Git Context Agent / Service

Responsibilities:

```text
branch state
commit history
diffs
file ownership
concurrent runs
merge risk
```

Used by:

- scaffold
- build
- adversarial-review
- align
- release

---

# 8.2 Context Retrieval Service

Never dump the entire repository into an LLM context window.

Use layered retrieval:

```text
Layer 1: phase artifacts
Layer 2: relevant files
Layer 3: symbol-level context
Layer 4: Git history
Layer 5: organizational policies
Layer 6: prior run learnings
```

Retrieval order:

```text
current task
   ↓
relevant artifact
   ↓
relevant symbols/files
   ↓
relevant tests
   ↓
history only when necessary
```

---

# 8.3 Policy Engine

Before every high-impact tool call:

```text
Agent
  ↓
Policy Engine
  ↓
allowed?
  ├── yes → Tool
  └── no  → deny / HITL
```

Examples:

```text
Can agent deploy production?        → policy
Can agent delete database data?    → policy
Can agent access secrets?           → policy
Can agent modify CI credentials?   → policy
Can agent push to protected branch?→ policy
```

---

# 8.4 Budget Ledger

Before phase:

```text
estimated_phase_cost
+
current_spend
≤
budget_cap
```

After phase:

```text
record actual tokens
record tool cost
record compute cost
record external API cost
```

Track:

```yaml
cost:
  input_tokens: 12000
  output_tokens: 4800
  model_cost: 0.91
  tool_cost: 0.10
  total: 1.01
```

---

# 8.5 Human-in-the-Loop Gate

The HITL system should not be "ask a human whenever the model is uncertain."

Make it policy-driven.

Examples:

```text
production deploy
security critical finding
budget exceeded
data migration
breaking API change
permission escalation
persistent retry exhaustion
```

Gate record:

```yaml
gate_id: gate_42
reason: production_deployment
required_role: release_manager
status: pending
decision: approved
actor: human
timestamp: ...
```

---

# 8.6 Observability

Every agent invocation emits:

```text
run_id
phase
agent
skill
model
prompt_version
tool
input_artifact_ids
output_artifact_ids
duration
tokens
cost
status
```

Use a trace tree:

```text
run
 ├── intake
 │    ├── clarify
 │    ├── extract
 │    └── constraints
 │
 ├── spec
 │    ├── decompose
 │    ├── acceptance-criteria
 │    └── scope
 │
 └── build
      ├── repo-retrieval
      ├── implementation
      ├── tests
      └── lint
```

---

# 9. Recommended Tool Taxonomy

Expose tools in namespaces.

```text
fs.*
git.*
test.*
build.*
security.*
cloud.*
artifact.*
policy.*
human.*
observability.*
```

## fs

```text
read_file
write_file
apply_patch
list_files
search_files
```

## git

```text
status
diff
log
show
create_branch
commit
tag
merge
open_pr
```

## test

```text
run_unit
run_integration
run_e2e
run_contract
collect_coverage
```

## build

```text
install
compile
package
build_container
```

## security

```text
secret_scan
dependency_scan
sast
container_scan
policy_scan
```

## cloud

```text
deploy_staging
deploy_production
health_check
rollback
```

## artifact

```text
create
read
list_versions
compare
link_evidence
```

## policy

```text
check_action
check_file_access
check_environment
check_release
```

---

# 10. Phase Contracts

Every phase should expose a standard interface.

```typescript
interface PhaseAgent {
  name: string;

  canRun(state: RunState): Promise<boolean>;

  estimate(state: RunState): Promise<CostEstimate>;

  execute(
    state: RunState,
    context: PhaseContext
  ): Promise<PhaseResult>;
}
```

`PhaseResult`:

```typescript
interface PhaseResult {
  status: "passed" | "failed" | "blocked";
  artifacts: ArtifactRef[];
  findings: Finding[];
  evidence: EvidenceRef[];

  route: {
    nextPhase: string;
    reason: string;
  };

  metrics: {
    durationMs: number;
    inputTokens: number;
    outputTokens: number;
    cost: number;
  };
}
```

---

# 11. Skill Contract

Every skill should have a machine-readable definition.

```yaml
skill:
  id: analyze-spec-ambiguity
  phase: analyze-risks

  objective: >
    Identify ambiguous requirements that can cause multiple reasonable implementations.

  inputs:
    - spec

  outputs:
    - risk_findings

  tools:
    - read_artifact
    - flag_finding

  constraints:
    - must cite requirement location
    - must classify severity
    - must provide remediation

  stop_condition:
    - all spec sections evaluated
```

---

# 12. Standard Finding Model

All phases should share one finding format.

```yaml
finding:
  id: FIND-001
  phase: adversarial-review

  severity:
    blocker|critical|major|minor|info

  category:
    correctness
    security
    performance
    reliability
    ambiguity
    scope
    maintainability
    compliance

  title: string
  description: string

  source:
    artifact_id: ...
    file: ...
    line_range: ...

  impact: string
  recommendation: string

  status:
    open|resolved|accepted|wont_fix

  evidence:
    - ...
```

This allows findings to travel backward through the graph.

---

# 13. Artifact Dependency Graph

The framework should maintain lineage.

```text
                  intake
                    │
             ┌──────┴──────┐
             ▼             ▼
          scaffold        spec
                            │
                            ▼
                         risks
                            │
                    ┌───────┴────────┐
                    ▼                ▼
                test-plan          build context
                    │                │
                    ▼                │
               test-design          │
                    │                │
                    └──────┬─────────┘
                           ▼
                         build
                           │
                           ▼
                     adversarial-review
                           │
                           ▼
                        verify
                           │
                           ▼
                         align
                           │
                           ▼
                        release
                           │
                           ▼
                         retro
```

Every output must record its parent artifact IDs.

---

# 14. Recommended State Machine

```yaml
states:
  intake:
    success: scaffold
    failure: human_gate

  scaffold:
    success: spec
    failure: human_gate

  spec:
    success: analyze-risks
    failure: intake

  analyze-risks:
    pass: create-test-plan
    blocker: spec

  create-test-plan:
    success: test-design
    failure: spec

  test-design:
    success: build
    failure: create-test-plan

  build:
    success: adversarial-review
    exhausted_retries: human_gate

  adversarial-review:
    pass: verify
    fail: build

  verify:
    pass: align
    fail: build

  align:
    pass: release
    drift: spec

  release:
    pass: retro
    failure: human_gate

  retro:
    success: end
```

---

# 15. Retry Strategy

Never allow infinite loops.

Recommended policy:

```yaml
retry:
  default_max_attempts: 3

  phase_overrides:
    analyze-risks: 2
    test-design: 2
    build: 4
    adversarial-review: 3
    verify: 3
    align: 2

  on_exhaustion:
    action: human_gate
```

Each retry should carry a **delta context**:

```text
Previous attempt failed because:
FIND-021
FIND-024
VERIFY-007
```

Do not force the agent to rediscover the same failure from scratch.

---

# 16. Model Routing Strategy

Do not use the most expensive model for every task.

Use model tiers.

```text
Tier 1 — fast / cheap
  routing
  extraction
  formatting
  classification
  simple summaries

Tier 2 — strong general model
  spec generation
  test planning
  code implementation
  semantic analysis

Tier 3 — strongest reasoning / critic
  adversarial review
  architecture tradeoffs
  security review
  difficult alignment decisions
```

Example:

```yaml
routing:
  intake.extract: tier1
  spec.generate: tier2
  analyze-risks: tier3
  build: tier2
  adversarial-review: tier3
  verify.interpret: tier1
  align: tier3
  retro: tier2
```

---

# 17. Prompt Architecture

Do not keep one giant prompt.

Use composition:

```text
system policy
+
agent identity
+
phase contract
+
skill instructions
+
project context
+
artifact context
+
tool schema
+
current findings
+
task
```

Example:

```text
[GLOBAL POLICY]
[AGENT: adversarial-review]
[SKILL: security-review]
[PROJECT POLICY]
[SPEC ARTIFACT]
[IMPLEMENTATION DIFF]
[PREVIOUS FINDINGS]
[TOOL DEFINITIONS]
[REVIEW TASK]
```

Version all prompts:

```text
prompts/
  intake/
    v1.yaml
    v2.yaml
  build/
    v3.yaml
```

Record prompt version in every phase trace.

---

# 18. Security Architecture

The agent must be treated as **untrusted execution logic**.

## Principle

```text
LLM ≠ root
```

Agents receive least privilege.

Example:

```text
intake          → read-only artifacts
spec            → read/write artifacts
test-design     → write tests
build           → modify source branch
review          → read-only source
verify          → run tests
release         → deploy only via policy gateway
```

Sensitive tools require explicit permissions.

Never expose raw secrets to the model.

Use:

```text
agent → credential broker → tool
```

rather than:

```text
agent → secret value
```

---

# 19. Recommended Production Data Stores

Use separate storage concerns.

## Relational DB

Store:

- projects
- runs
- phases
- findings
- artifacts metadata
- approvals
- costs
- policy decisions

## Object Storage

Store:

- markdown artifacts
- JSON manifests
- logs
- test reports
- screenshots
- deployment evidence
- generated packages

## Vector / Search Index

Store embeddings for:

- project documentation
- prior phase artifacts
- code summaries
- historical learnings

Do not make the vector store the source of truth.

Source of truth:

```text
Git + Artifact Store + relational metadata
```

---

# 20. Phase Digest — Manager-Readable Summaries

## Problem

`phase_history` rows are correct and complete, but nobody without pipeline context can
read one in under a minute. A manager looking at a specific phase shouldn't have to parse
YAML, cross-reference `artifact_ids`, or understand the finding schema to know what
happened.

## What this is — and, deliberately, what it isn't

This is **not a new agent.** It doesn't decide anything, doesn't call tools in a loop,
and has no judgment about *what* to fetch — that part is fully deterministic code. The
only place an LLM touches this is one single-shot synthesis call at the end, given
everything it needs already assembled. Call it a **Renderer**: deterministic fetch +
one-shot LLM write-up. It's the third category alongside Gate and Agent:

| Category | Decides what to do next? | Loops? | Example |
|---|---|---|---|
| Gate | Yes — routes | No | HLD-need check, spec-mode resolution |
| Agent | Yes — repeatedly | Yes | Build, Adversarial-Review |
| **Renderer** | No — fixed steps | No | **Phase Digest** |

Cheapest tier model, one call, no tool-use loop to pay for.

## Pipeline

```text
1. Deterministic fetch (plain code, not an LLM call):
   - phase_history row (phase, attempt, status, timestamps, cost)
   - dereferenced artifact_ids (pull the actual content or existing summaries)
   - findings[] attached to this phase (open + resolved)

2. Single LLM call — synthesize into a fixed template (below). No tools, no
   iteration, no follow-up questions. If the call fails, retry once; if it
   fails again, fall back to a plain-template render with no prose (still
   usable, just less readable).

3. Write the digest as its own artifact: phase-digest.md
   Store in Object Storage, same as every other artifact.
```

## Trigger: on-demand, not automatic

Generated **lazily**, the first time anyone requests a view of that phase — not
synchronously at phase completion. Most phase runs are never individually inspected by a
manager; generating a digest for all of them by default burns tokens on summaries nobody
reads, which cuts against the optimization goal from earlier. Once generated, it's cached
— the phase is terminal and immutable, so the digest never needs regenerating.

## Digest template (fixed, not left to the LLM to structure)

```text
# Phase: {phase_name} — Attempt {n}
Status: {PASSED | FAILED | BLOCKED}   Cost: ${cost}   Duration: {duration}

## One-line verdict
{single sentence — what happened and whether it's fine}

## What happened
{2-4 plain-English sentences, no jargon, no schema terms}

## Findings that matter
{blockers/majors only, one line each — minors omitted, link to full list}

## Links
Raw phase_history: {deep_link_to_run}#{phase}/{attempt}
Artifacts produced: {list of links}
```

## Bidirectional linking

This is the part that actually needs enforcing, not just documenting:

- The `phase_history` row gets one new field: `digest_artifact_id` — set the first time a
  digest is generated for that phase/attempt, `null` until then.
- The digest file's own header (`## Links` above) carries the reverse pointer straight
  back to `{run_id}/{phase}/{attempt}` in the relational store.

So from either side you're one click away from the other — a manager reading the digest
can jump to raw `phase_history` if they need to dig deeper; someone querying
`phase_history` directly (e.g. debugging a retry loop) can jump straight to the readable
version instead of parsing the row by hand.

## Schema addition to RunState

```yaml
phase_history:
  - phase: string
    attempt: integer
    status: string
    started_at: timestamp
    completed_at: timestamp
    artifact_ids: []
    findings: []
    cost: {}
    digest_artifact_id: string | null   # <-- new
```

---

# 21. Complete Output Matrix

| Phase | Primary Agent | Main Skills | Output |
|---|---|---|---|
| intake | Intake Agent | clarification, extraction, constraints | `artifacts/intake/intake.*` + `artifacts/intake/interview.*` |
| scaffold | Scaffold Agent | stack selection, repo generation, CI | `artifacts/scaffold/*` + repo skeleton |
| spec | Spec Agent | decomposition, AC generation, scope | `artifacts/spec/spec.*` |
| analyze-risks | Risk Agent | ambiguity, edge cases, security, scope | `artifacts/risks/risk-report.*` |
| create-test-plan | Test Strategy Agent | AC mapping, coverage gaps | `artifacts/test-plan/*` |
| test-design | Test Design Agent | test generation, fixtures, mocks | `tests/*` + `artifacts/test-design/*` |
| build | Build Agent | retrieval, planning, coding, checks | source diff + `artifacts/build/*` |
| adversarial-review | Review Agent | correctness, security, reliability, Git | `artifacts/review/*` |
| verify | Verify Agent | execution, evidence, traceability | `artifacts/verify/*` |
| align | Align Agent | semantic diff, stakeholder intent, drift | `artifacts/align/*` |
| release | Release Agent | readiness, versioning, packaging, deploy | `artifacts/release/*` |
| retro | Retro Agent | history, patterns, learning proposals | `artifacts/retro/*` |

---

# 22. Exact Artifact Tree

Recommended final layout:

```text
.aidlc/
│
├── run.yaml
│
├── state/
│   ├── current.json
│   └── history/
│       ├── event-0001.json
│       ├── event-0002.json
│       └── ...
│
├── artifacts/
│   │
│   ├── intake/
│   │   ├── intake.v001.md
│   │   └── intake.v001.json
│   │
│   ├── scaffold/
│   │   ├── scaffold.v001.md
│   │   └── stack-manifest.v001.json
│   │
│   ├── spec/
│   │   ├── spec.v001.md
│   │   └── spec.v001.json
│   │
│   ├── risks/
│   │   ├── risk-report.v001.md
│   │   └── findings.v001.json
│   │
│   ├── test-plan/
│   │   ├── test-plan.v001.md
│   │   └── coverage-matrix.v001.json
│   │
│   ├── test-design/
│   │   ├── test-design.v001.md
│   │   └── test-map.v001.json
│   │
│   ├── build/
│   │   ├── build.v001.md
│   │   └── implementation-manifest.v001.json
│   │
│   ├── review/
│   │   ├── review-report.v001.md
│   │   └── findings.v001.json
│   │
│   ├── verify/
│   │   ├── verify-report.v001.md
│   │   └── traceability.v001.json
│   │
│   ├── align/
│   │   ├── align-report.v001.md
│   │   └── semantic-trace.v001.json
│   │
│   ├── release/
│   │   ├── release-manifest.v001.json
│   │   └── release-notes.v001.md
│   │
│   └── retro/
│       ├── retro.v001.md
│       └── learning-signals.v001.json
│
├── evidence/
│   ├── build/
│   ├── test-results/
│   ├── coverage/
│   ├── security/
│   └── deployment/
│
├── prompts/
├── policies/
├── traces/
└── manifests/
```

---

# 23. End-to-End Example

Suppose the user asks:

> "Build an API for creating wallet transactions with authentication."

The lifecycle should produce:

```text
INTAKE
  ↓
Structured problem:
- authenticated wallet transaction creation
- transaction amount
- wallet ownership
- idempotency
- invalid inputs
  ↓
SCAFFOLD
  ↓
FastAPI / PostgreSQL / JWT / pytest
  ↓
SPEC
  ↓
AC-01 authenticated user can create transaction
AC-02 user cannot modify another wallet
AC-03 duplicate request with same idempotency key is safe
AC-04 invalid amount rejected
  ↓
ANALYZE-RISKS
  ↓
Find:
- authorization ambiguity
- duplicate transaction risk
- race condition risk
  ↓
TEST PLAN
  ↓
AC-01 → integration
AC-02 → security + integration
AC-03 → concurrency/idempotency
AC-04 → unit + API
  ↓
TEST DESIGN
  ↓
tests created
  ↓
BUILD
  ↓
implementation generated
  ↓
ADVERSARIAL REVIEW
  ↓
Find:
"authorization check occurs after wallet lookup/mutation"
  ↓
BUILD RETRY
  ↓
fixed
  ↓
VERIFY
  ↓
all tests pass
  ↓
ALIGN
  ↓
stakeholder intent satisfied
  ↓
RELEASE
  ↓
version + package + deployment
  ↓
RETRO
  ↓
Learning:
"All transaction features should include an explicit idempotency requirement"
```

That learning can later strengthen the `spec` or `analyze-risks` skills.

---

# 24. What Makes This Framework Different From a Simple Coding Agent

A coding agent usually looks like:

```text
prompt → code → done
```

This framework is:

```text
intent
  ↓
specification
  ↓
risk analysis
  ↓
verification design
  ↓
test-first implementation
  ↓
independent adversarial review
  ↓
mechanical verification
  ↓
semantic alignment
  ↓
controlled release
  ↓
organizational learning
```

The important property is **separation of responsibilities**.

The agent that proposes the solution should not be the only agent deciding whether the solution is correct.

---

# 25. Recommended Agent Catalog

Final production catalog:

```text
1. IntakeAgent
2. ScaffoldAgent
3. SpecAgent
4. RiskAgent
5. TestPlanAgent
6. TestDesignAgent
7. BuildAgent
8. AdversarialReviewAgent
9. VerifyAgent
10. AlignAgent
11. ReleaseAgent
12. RetroAgent
```

Cross-cutting:

```text
13. GitContextService
14. ContextRetrievalService
15. PolicyEngine
16. BudgetLedger
17. ArtifactService
18. EvidenceService
19. HumanGateService
20. ObservabilityService
```

---

# 26. Recommended Implementation Boundary

Do not build every feature at once.

## Phase A — Core execution engine

Build:

```text
Orchestrator
State
Artifact Store
Tool Gateway
Intake
Spec
Build
Verify
```

Goal:

```text
raw ask → working code
```

## Phase B — Quality system

Add:

```text
Analyze-Risks
Create-Test-Plan
Test-Design
Adversarial-Review
Align
```

Goal:

```text
working code → trusted code
```

## Phase C — Delivery system

Add:

```text
Release
HITL
Policy Engine
Git concurrency
Deployment evidence
```

Goal:

```text
trusted code → production
```

## Phase D — Learning system

Add:

```text
Retro
pattern extraction
skill quality metrics
prompt versioning
regression suite
```

Goal:

```text
every run improves future runs
```

---

# 27. Metrics That Matter

Do not optimize only for "number of lines generated."

Track:

## Delivery

```text
lead time
cycle time
time per phase
```

## Quality

```text
defect escape rate
review failure rate
verify failure rate
alignment failure rate
```

## Agent efficiency

```text
tool calls per phase
tokens per phase
cost per successful change
retry rate
```

## Reliability

```text
phase failure rate
orchestration failure rate
flaky test rate
rollback rate
```

## Learning

```text
repeated finding frequency
new finding classes
prompt regression rate
skill improvement rate
```

---

# 28. Key Design Decisions

## Decision 1

**Artifacts are the shared memory, not chat history.**

## Decision 2

**The orchestrator controls routing; agents control local reasoning.**

## Decision 3

**Tests are designed before implementation.**

## Decision 4

**Adversarial review is independent from Build.**

## Decision 5

**Verification is evidence-producing, not just "tests passed."**

## Decision 6

**Alignment checks human intent separately from technical correctness.**

## Decision 7

**Production actions go through policy and human gates.**

## Decision 8

**Every artifact is versioned and traceable to its inputs.**

## Decision 9

**Backward edges are first-class features, not exceptions.**

## Decision 10

**Retro produces improvement proposals, not uncontrolled self-modification.**

---

# 29. Final Architecture

```text
                              USER
                               │
                               ▼
                       ┌───────────────┐
                       │   INTENT API  │
                       └───────┬───────┘
                               │
                               ▼
                 ┌──────────────────────────┐
                 │      ORCHESTRATOR        │
                 │ StateGraph + policies    │
                 │ retries + budgets + HITL │
                 └───────────┬──────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   AGENT LAYER          CONTEXT LAYER        POLICY LAYER
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
                       TOOL GATEWAY
                             │
             ┌───────────────┼────────────────┐
             │               │                │
             ▼               ▼                ▼
           Git          Workspace         External Systems
             │               │                │
             └───────────────┼────────────────┘
                             │
                             ▼
                     ARTIFACT + EVIDENCE
                             │
             ┌───────────────┼──────────────────┐
             │               │                  │
             ▼               ▼                  ▼
         Object Store     Metadata DB        Search Index
             │               │                  │
             └───────────────┼──────────────────┘
                             │
                             ▼
                      OBSERVABILITY
                             │
                             ▼
                           RETRO
                             │
                             ▼
                   LEARNING / IMPROVEMENT
```

---

# 30. The Golden Rule

The framework should never be just:

```text
"LLM, build this."
```

It should behave more like:

```text
Understand it.
↓
Structure it.
↓
Challenge it.
↓
Design how to verify it.
↓
Write the tests.
↓
Build it.
↓
Attack it.
↓
Verify it.
↓
Ask whether it actually solves the original problem.
↓
Release it safely.
↓
Learn from what happened.
```

That is the architecture that turns an AI coding agent into an **end-to-end software engineering system**.