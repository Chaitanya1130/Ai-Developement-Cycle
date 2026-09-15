import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class ModelMessage:
    role: str  # "user" or "assistant"
    content: Union[str, List[Dict[str, Any]]]


@dataclass
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0


@dataclass
class ModelResponse:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: ModelUsage = field(default_factory=ModelUsage)
    stop_reason: str = "end_turn"
    raw_content: Any = None


@dataclass
class ModelRequest:
    messages: List[ModelMessage]
    tier: str = "tier2"  # "tier1", "tier2", "tier3"
    model: Optional[str] = None
    system: Optional[str] = None
    tools: Optional[List[ToolDefinition]] = None
    temperature: float = 0.2
    max_tokens: int = 4096


class ModelProviderAdapter:
    name: str

    def is_available(self) -> bool:
        raise NotImplementedError

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class AnthropicAdapter(ModelProviderAdapter):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def is_available(self) -> bool:
        key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        return bool(key and key.strip())

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
                if not key:
                    raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
                self._client = anthropic.Anthropic(api_key=key)
            except ImportError:
                raise RuntimeError(
                    "The 'anthropic' Python package is not installed. Install with 'pip install anthropic'."
                )
        return self._client

    def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._get_client()
        model_name = request.model or "claude-3-5-sonnet-20241022"

        messages = []
        for m in request.messages:
            messages.append({"role": m.role, "content": m.content})

        tools_param = None
        if request.tools:
            tools_param = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in request.tools
            ]

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system:
            kwargs["system"] = request.system
        if tools_param:
            kwargs["tools"] = tools_param

        resp = client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []

        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input if isinstance(block.input, dict) else {},
                    )
                )

        in_tokens = getattr(resp.usage, "input_tokens", 0)
        out_tokens = getattr(resp.usage, "output_tokens", 0)
        cost = (in_tokens * 3.0) / 1_000_000 + (out_tokens * 15.0) / 1_000_000

        return ModelResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=ModelUsage(input_tokens=in_tokens, output_tokens=out_tokens, cost_estimate=cost),
            stop_reason=getattr(resp, "stop_reason", "end_turn") or "end_turn",
            raw_content=resp.content,
        )


class AgyAdapter(ModelProviderAdapter):
    name = "agy"

    def __init__(self):
        self.agy_path = self._resolve_agy_path()

    def _resolve_agy_path(self) -> Optional[str]:
        custom = os.getenv("AGY_PATH")
        if custom and os.path.exists(custom):
            return custom

        home = os.path.expanduser("~")
        local_agy = os.path.join(home, ".local", "bin", "agy")
        if os.path.exists(local_agy):
            return local_agy

        which_path = shutil.which("agy")
        if which_path and os.path.exists(which_path):
            return which_path

        return None

    def is_available(self) -> bool:
        if not self.agy_path or not os.path.exists(self.agy_path):
            self.agy_path = self._resolve_agy_path()
        if not self.agy_path:
            return False

        # Verify agy is runnable
        try:
            res = subprocess.run(
                [self.agy_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return False
        except Exception:
            return False

        # Verify cached session/credentials exist
        home = os.path.expanduser("~")
        gemini_dir = os.path.join(home, ".gemini", "antigravity")
        config_dir = os.path.join(home, ".config", "antigravity")
        has_creds = os.path.exists(gemini_dir) or os.path.exists(config_dir)

        return has_creds or (res.returncode == 0)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not self.agy_path:
            self.agy_path = self._resolve_agy_path()
        if not self.agy_path:
            raise RuntimeError("agy CLI is not installed or not found in PATH or ~/.local/bin/agy")

        prompt_text = ""
        if request.system:
            prompt_text += f"[SYSTEM INSTRUCTIONS]\n{request.system}\n\n"

        if request.tools:
            prompt_text += "[AVAILABLE TOOLS]\n"
            for t in request.tools:
                prompt_text += (
                    f"- Tool: {t.name}\n"
                    f"  Description: {t.description}\n"
                    f"  Parameters Schema: {json.dumps(t.input_schema)}\n\n"
                )
            prompt_text += (
                "[TOOL CALL INSTRUCTIONS]\n"
                "To call one or more tools, you MUST output a valid JSON object in the following format:\n"
                "{\n"
                '  "thought": "your brief reasoning",\n'
                '  "tool_calls": [\n'
                "    {\n"
                '      "name": "tool_name",\n'
                '      "input": { ... }\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "If you do not need to call any tools, reply with normal text or call complete_phase.\n\n"
            )

        prompt_text += "[CONVERSATION]\n"
        for m in request.messages:
            if isinstance(m.content, str):
                prompt_text += f"[{m.role.upper()}]:\n{m.content}\n\n"
            elif isinstance(m.content, list):
                prompt_text += f"[{m.role.upper()}]:\n"
                for part in m.content:
                    if part.get("type") == "text":
                        prompt_text += f"{part.get('text')}\n"
                    elif part.get("type") == "tool_result":
                        prompt_text += f"[TOOL RESULT for {part.get('tool_use_id')}]:\n{part.get('content')}\n"
                    elif part.get("type") == "tool_use":
                        prompt_text += f"[CALLED TOOL {part.get('name')}]:\n{json.dumps(part.get('input'))}\n"
                prompt_text += "\n"

        timeout_seconds = int(os.getenv("AGY_TIMEOUT", "600"))
        print_timeout_str = f"{max(1, timeout_seconds // 60)}m"

        cmd = [
            self.agy_path,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--print-timeout",
            print_timeout_str,
            "-p",
            prompt_text,
        ]
        effort = os.getenv("AGY_EFFORT")
        if effort:
            cmd.insert(1, "--effort")
            cmd.insert(2, effort)
        elif request.tier == "tier1":
            cmd.insert(1, "--effort")
            cmd.insert(2, "low")

        max_retries = 3
        res = None
        for attempt in range(1, max_retries + 1):
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=timeout_seconds + 30,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    f"Antigravity CLI (agy) call timed out after {timeout_seconds} seconds during code generation. "
                    f"You can increase this limit by setting AGY_TIMEOUT (e.g. export AGY_TIMEOUT=900) "
                    f"or set AGY_EFFORT=medium for faster generation."
                )

            if res.returncode != 0:
                err_msg = res.stderr or res.stdout
                is_transient = any(
                    phrase in err_msg.lower()
                    for phrase in [
                        "connection reset",
                        "broken pipe",
                        "eof",
                        "tls handshake",
                        "timed out",
                        "network is unreachable",
                    ]
                )
                if is_transient and attempt < max_retries:
                    time.sleep(2 * attempt)
                    continue
                raise RuntimeError(f"agy CLI failed (code {res.returncode}): {err_msg}")
            break

        raw_response = ""
        in_tokens = 0
        out_tokens = 0

        try:
            parsed = json.loads(res.stdout)
            raw_response = parsed.get("response", "")
            in_tokens = parsed.get("usage", {}).get("input_tokens", 0)
            out_tokens = parsed.get("usage", {}).get("output_tokens", 0)
        except Exception:
            raw_response = res.stdout

        tool_calls = self._parse_tool_calls(raw_response)
        # Compute cost estimate (using standard tier pricing: $3.00/M in, $15.00/M out)
        cost = (in_tokens * 3.0) / 1_000_000 + (out_tokens * 15.0) / 1_000_000

        if tool_calls:
            return ModelResponse(
                text=raw_response,
                tool_calls=tool_calls,
                usage=ModelUsage(input_tokens=in_tokens, output_tokens=out_tokens, cost_estimate=cost),
                stop_reason="tool_use",
            )

        return ModelResponse(
            text=raw_response,
            tool_calls=[],
            usage=ModelUsage(input_tokens=in_tokens, output_tokens=out_tokens, cost_estimate=cost),
            stop_reason="end_turn",
        )

    def _parse_tool_calls(self, text: str) -> Optional[List[ToolCall]]:
        candidates = []

        # 1. Code blocks
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
            candidates.append(match.group(1).strip())

        # 2. Entire text
        candidates.append(text.strip())

        # 3. Outer braces
        first_b = text.find("{")
        last_b = text.rfind("}")
        if first_b != -1 and last_b > first_b:
            candidates.append(text[first_b : last_b + 1])

        for c in candidates:
            try:
                obj = json.loads(c)
                if isinstance(obj, dict) and "tool_calls" in obj and isinstance(obj["tool_calls"], list):
                    calls = []
                    for i, tc in enumerate(obj["tool_calls"]):
                        calls.append(
                            ToolCall(
                                id=tc.get("id", f"call_{int(time.time() * 1000)}_{i}"),
                                name=tc.get("name") or tc.get("tool"),
                                input=tc.get("input") or tc.get("args") or {},
                            )
                        )
                    return calls
                if isinstance(obj, dict) and "name" in obj and ("input" in obj or "args" in obj):
                    return [
                        ToolCall(
                            id=obj.get("id", f"call_{int(time.time() * 1000)}_0"),
                            name=obj["name"],
                            input=obj.get("input") or obj.get("args") or {},
                        )
                    ]
            except Exception:
                continue

        return None


class MockAdapter(ModelProviderAdapter):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def complete(self, request: ModelRequest) -> ModelResponse:
        last_msg = request.messages[-1]
        last_content = ""
        has_tool_results = False

        if isinstance(last_msg.content, str):
            last_content = last_msg.content
        elif isinstance(last_msg.content, list):
            for item in last_msg.content:
                if item.get("type") == "tool_result":
                    has_tool_results = True
                    last_content += item.get("content", "") + " "
                elif item.get("type") == "text":
                    last_content += item.get("text", "") + " "

        system = request.system or ""
        tool_names = [t.name for t in (request.tools or [])]

        is_intake = "Intake Agent" in system
        is_scaffold = "Scaffold Agent" in system
        is_spec = "Spec Agent" in system
        is_analyze_risks = "Analyze-Risks Agent" in system
        is_create_test_plan = "Create-Test-Plan Agent" in system
        is_test_design = "Test-Design Agent" in system
        is_build = "Build Agent" in system
        is_adversarial_review = "Adversarial-Review Agent" in system
        is_verify = "Verify Agent" in system
        is_align = "Align Agent" in system
        is_release = "Release Agent" in system
        is_retro = "Retro Agent" in system

        if has_tool_results:
            if "complete_phase" in tool_names:
                return ModelResponse(
                    text="Phase completed successfully.",
                    tool_calls=[
                        ToolCall(
                            id=f"call_{int(time.time() * 1000)}",
                            name="complete_phase",
                            input={
                                "status": "passed",
                                "verdict": "pass",
                                "summary": "Requirements processed and artifacts stored.",
                            },
                        )
                    ],
                    usage=ModelUsage(input_tokens=500, output_tokens=200),
                    stop_reason="tool_use",
                )
            return ModelResponse(text="Done.", tool_calls=[])

        if is_intake:
            m = re.search(r'"""\s*([\s\S]*?)\s*"""', last_content)
            raw_input = m.group(1).strip() if m else "Software Project"

            title_m = re.search(r"\*\*(?:Project Name / Title|Title)\*\*:\s*([^\n]+)", raw_input)
            prob_m = re.search(r"\*\*(?:Problem Statement|Problem)\*\*:\s*([^\n]+)", raw_input)
            user_m = re.search(r"\*\*(?:Target Users & Personas|Target Users & Actors|Users)\*\*:\s*([^\n]+)", raw_input)
            outcome_m = re.search(r"\*\*(?:Desired Outcome & Value|Desired Outcome)\*\*:\s*([^\n]+)", raw_input)

            proj_title = title_m.group(1).strip() if title_m and title_m.group(1).strip() else "Software Project"
            problem_text = prob_m.group(1).strip() if prob_m and prob_m.group(1).strip() else (raw_input if len(raw_input) < 300 else "Core domain software utility.")
            user_text = user_m.group(1).strip() if user_m and user_m.group(1).strip() else "Developers and automated systems."
            outcome_text = outcome_m.group(1).strip() if outcome_m and outcome_m.group(1).strip() else "A reliable, high-quality implementation meeting all specifications."

            # Parse [x] or [X] checkboxes
            chosen_methodology = "TDD (Test-Driven Development)"
            for line in raw_input.splitlines():
                if re.search(r"-\s*\[[xX]\]\s*\*\*TDD", line):
                    chosen_methodology = "TDD (Test-Driven Development)"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*BDD", line):
                    chosen_methodology = "BDD (Behavior-Driven Development)"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*CDD", line):
                    chosen_methodology = "CDD (Contract-Driven Development)"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*EDD", line):
                    chosen_methodology = "EDD (Event-Driven Development)"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*DDD", line):
                    chosen_methodology = "DDD (Domain-Driven Design)"

            chosen_form_factor = "CLI Application / Utility"
            for line in raw_input.splitlines():
                if re.search(r"-\s*\[[xX]\]\s*\*\*CLI", line):
                    chosen_form_factor = "CLI Application / Utility"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*REST", line):
                    chosen_form_factor = "REST / HTTP API Microservice"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*Reusable Library", line):
                    chosen_form_factor = "Reusable Library / SDK"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*Background Worker", line):
                    chosen_form_factor = "Background Worker / Daemon"
                elif re.search(r"-\s*\[[xX]\]\s*\*\*Full-stack", line):
                    chosen_form_factor = "Full-stack Web Application"

            intake_md = f"""# Requirements Specification: {proj_title}

## 1. Problem Statement
{problem_text}

## 2. User / Actor
{user_text}

## 3. Desired Outcome
{outcome_text}

## 4. Functional Requirements
- FR-01: Core capability evaluation
- FR-02: Input validation and formatting
- FR-03: Process standard output and error diagnostics

## 5. Non-Functional Requirements
- NFR-01: Low latency (< 100ms)
- NFR-02: Zero non-standard dependencies

## 6. Constraints
- Runtime: Standard Python environment

## 7. Story Sourcing Mode
agent_generated

## 8. Acceptance Signals
- Baseline commands execute successfully with exit code 0
- Invalid arguments output diagnostics to stderr with exit code 1
"""
            intake_json = {
                "problem": problem_text,
                "actor": user_text,
                "story_source": "agent_generated",
                "functional_requirements": ["FR-01: Core capability", "FR-02: Validation"],
            }

            interview_md = f"""# Discovery & Architectural Alignment Interview: {proj_title}

## 1. Project Vision & Core Description
- **Vision**: {outcome_text}
- **Core Problem**: {problem_text}

## 2. Methodology & Driven-Development Selection
- **Chosen Paradigm**: **{chosen_methodology}**
- **Methodology Rationale**: Selected by developer in discovery interview to govern specification and test creation.

## 3. Architectural Style & Interface Boundaries
- **Form Factor**: {chosen_form_factor}
- **State Management**: Stateless execution
- **Dependency Philosophy**: Standard library only

## 4. Testing & Quality Strategy
- **Framework**: pytest
- **Test Distribution**: 100% acceptance criteria coverage

## 5. Non-Functional Priorities & Trade-Offs
- Latency and performance bounds
- Platform portability and POSIX error diagnostics

## 6. Pre-filled Recommended Defaults & Sign-off Status
- **Status**: Ready for developer confirmation.
"""
            interview_json = {
                "chosen_methodology": chosen_methodology,
                "architecture_style": chosen_form_factor,
                "test_framework": "pytest",
                "dependency_strategy": "zero external dependencies",
                "status": "ready_for_review",
            }

            return ModelResponse(
                text="Writing intake and architectural interview artifacts.",
                tool_calls=[
                    ToolCall(
                        id=f"call_intake_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "intake",
                            "type": "intake",
                            "content": intake_md,
                            "json_metadata": intake_json,
                        },
                    ),
                    ToolCall(
                        id=f"call_interview_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "interview",
                            "type": "interview",
                            "content": interview_md,
                            "json_metadata": interview_json,
                        },
                    ),
                ],
                usage=ModelUsage(input_tokens=400, output_tokens=300),
                stop_reason="tool_use",
            )

        if is_scaffold:
            scaffold_md = """# Scaffold Report

## Stack Selection
- Language: Python 3.10+
- Packaging: setuptools / pyproject.toml
- Test Framework: pytest

## Repository Topology
- `src/`: Core implementation modules
- `tests/`: Automated unit and integration test suites
- `docs/`: Architectural documentation and specifications
"""
            return ModelResponse(
                text="Writing scaffold and stack manifest artifacts.",
                tool_calls=[
                    ToolCall(
                        id=f"call_scaffold_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "scaffold",
                            "type": "scaffold",
                            "content": scaffold_md,
                            "json_metadata": {
                                "language": "python",
                                "framework": "none",
                                "test_framework": "pytest",
                                "directories": ["src", "tests", "docs"],
                                "entry_point": "generated.calc",
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=400, output_tokens=300),
                stop_reason="tool_use",
            )

        if is_spec:
            is_human = (
                "Current Story-Sourcing Mode: human_supplied" in system
                or "Story-Sourcing Mode: human_supplied" in last_content
            )
            story_source = "human_supplied" if is_human else "agent_generated"

            # Check contradiction
            if is_human and ("Python" in last_content or "Flask" in last_content or "web API" in last_content):
                return ModelResponse(
                    text="Contradiction detected: Human story requests Python web API contradicting CLI calculator intake.",
                    tool_calls=[
                        ToolCall(
                            id=f"call_blocker_{int(time.time() * 1000)}",
                            name="flag_finding",
                            input={
                                "id": "BLOCKER-001",
                                "severity": "blocker",
                                "category": "scope",
                                "title": "Contradiction between human story and intake constraints",
                                "description": "Human story requests Python web API microservice, which contradicts CLI intake.",
                            },
                        ),
                        ToolCall(
                            id=f"call_complete_{int(time.time() * 1000)}",
                            name="complete_phase",
                            input={
                                "status": "blocked",
                                "verdict": "fail",
                                "summary": "Human story contradicts intake. Escalating to human gate.",
                            },
                        ),
                    ],
                    usage=ModelUsage(input_tokens=500, output_tokens=300),
                    stop_reason="tool_use",
                )

            spec_md = f"""# Engineering Specification: Calculator

## Summary
Authoritative specification for calculator.

## Business Context
Developer productivity tool.

## Problem
Evaluate arithmetic expressions.

## Actors
CLI User, Automated Pipeline

## Story Source: {story_source}

## Stories
- STORY-001: Addition and subtraction CLI operations

## Scope
- add and subtract commands

## Out of Scope
- web APIs, GUI

## Acceptance Criteria
- AC-01: Given numbers When add executed Then sum is returned
- AC-02: Given numbers When subtract executed Then difference is returned

## Definition of Done
- Tests pass cleanly
"""
            return ModelResponse(
                text="Writing spec artifact.",
                tool_calls=[
                    ToolCall(
                        id=f"call_spec_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "spec",
                            "type": "spec",
                            "content": spec_md,
                            "json_metadata": {
                                "story_source": story_source,
                                "stories": ["STORY-001"],
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=500, output_tokens=400),
                stop_reason="tool_use",
            )

        if is_analyze_risks:
            risk_md = """# Risk Analysis Report

## Multi-Lens Assessment

### 1. Ambiguity Detection
- Low risk: arithmetic operations are mathematically well-defined.

### 2. Edge-Case Analysis
- Large numbers: Python natively supports arbitrary precision integers.
- Division by zero: Not applicable to addition/subtraction, but must handle non-numeric inputs.

### 3. Scope-Creep Detection
- Clean boundary: restricted to addition and subtraction operations.

### 4. Security Preflight
- Zero untrusted code execution. Pure numeric arguments.
"""
            return ModelResponse(
                text="Analyzing risks and generating risk report artifact.",
                tool_calls=[
                    ToolCall(
                        id=f"call_risk_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "risk-report",
                            "type": "risk_report",
                            "content": risk_md,
                            "json_metadata": {
                                "risks": [
                                    {
                                        "id": "RISK-001",
                                        "severity": "low",
                                        "category": "edge_case",
                                        "recommendation": "Ensure graceful error handling for invalid input strings",
                                    }
                                ],
                                "blockers_count": 0,
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=450, output_tokens=300),
                stop_reason="tool_use",
            )

        if is_create_test_plan:
            plan_md = """# Test Strategy & Plan

## Acceptance Criteria Coverage Matrix
- **AC-01 (Addition)**: Unit tests for positive, negative, and floating point operands.
- **AC-02 (Subtraction)**: Unit tests for positive, negative, and zero operands.

## Verification Levels
- **Unit Testing**: 100% coverage of arithmetic operations.
- **Boundary & Regression**: Edge cases with zero and floating point values.
"""
            return ModelResponse(
                text="Formulating test plan and coverage matrix.",
                tool_calls=[
                    ToolCall(
                        id=f"call_tp_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "test-plan",
                            "type": "test_plan",
                            "content": plan_md,
                            "json_metadata": {
                                "ac_coverage_matrix": {
                                    "AC-01": ["unit", "edge_case"],
                                    "AC-02": ["unit", "edge_case"],
                                }
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=400, output_tokens=250),
                stop_reason="tool_use",
            )

        if is_test_design:
            test_code = """from generated.calc import add, subtract

def test_add():
    assert add(5, 3) == 8
    assert add(2.5, 1.5) == 4.0

def test_subtract():
    assert subtract(10, 4) == 6
    assert subtract(5, 8) == -3
"""
            td_md = """# Test Design Report

## Test Suites Designed
Created `tests/test_calc.py` covering AC-01 and AC-02 before implementation code generation.
"""
            return ModelResponse(
                text="Writing executable test suites and test design artifact.",
                tool_calls=[
                    ToolCall(
                        id=f"call_td1_{int(time.time() * 1000)}",
                        name="fs_write_file",
                        input={"path": "tests/test_calc.py", "content": test_code},
                    ),
                    ToolCall(
                        id=f"call_td2_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "test-design",
                            "type": "test_design",
                            "content": td_md,
                            "json_metadata": {
                                "test_files": ["tests/test_calc.py"],
                                "ac_to_test_mapping": {"AC-01": "test_add", "AC-02": "test_subtract"},
                            },
                        },
                    ),
                ],
                usage=ModelUsage(input_tokens=500, output_tokens=350),
                stop_reason="tool_use",
            )

        if is_build:
            impl_code = """def add(a: float, b: float) -> float:
    return a + b

def subtract(a: float, b: float) -> float:
    return a - b
"""
            test_code = """from generated.calc import add, subtract

def test_add():
    assert add(5, 3) == 8
    assert add(2.5, 1.5) == 4.0

def test_subtract():
    assert subtract(10, 4) == 6
"""
            build_md = "# Build Report\n\nImplemented generated/calc.py and tests/test_calc.py.\n"

            return ModelResponse(
                text="Writing build files.",
                tool_calls=[
                    ToolCall(
                        id=f"call_b1_{int(time.time() * 1000)}",
                        name="fs_write_file",
                        input={"path": "generated/calc.py", "content": impl_code},
                    ),
                    ToolCall(
                        id=f"call_b2_{int(time.time() * 1000)}",
                        name="fs_write_file",
                        input={"path": "tests/test_calc.py", "content": test_code},
                    ),
                    ToolCall(
                        id=f"call_b3_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "build",
                            "type": "build",
                            "content": build_md,
                            "json_metadata": {"files_created": ["generated/calc.py", "tests/test_calc.py"]},
                        },
                    ),
                ],
                usage=ModelUsage(input_tokens=600, output_tokens=500),
                stop_reason="tool_use",
            )

        if is_adversarial_review:
            review_md = """# Adversarial Red-Team Review Report

## Verdict: PASS

### Evaluation Lenses
1. **Correctness**: Implementation cleanly handles arithmetic operations and adheres to AC-01 and AC-02.
2. **Security**: No dangerous dynamic evaluation (eval/exec) or unsafe system calls.
3. **Reliability**: Pure arithmetic functions without resource leaks or side effects.
4. **Spec Compliance**: 100% compliant with specifications.
"""
            return ModelResponse(
                text="Performing adversarial red team review.",
                tool_calls=[
                    ToolCall(
                        id=f"call_rev_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "review-report",
                            "type": "review_report",
                            "content": review_md,
                            "json_metadata": {
                                "verdict": "PASS",
                                "findings": [],
                                "security_issues": 0,
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=500, output_tokens=300),
                stop_reason="tool_use",
            )

        if is_verify:
            verify_md = """# Verification Report

## Verdict: PASSED
All tests passed via pytest.

## Traceability
- AC-01 -> test_add (PASSED)
- AC-02 -> test_subtract (PASSED)

## Test Summary
- Passed: 2
- Failed: 0
"""
            return ModelResponse(
                text="Running test verification.",
                tool_calls=[
                    ToolCall(
                        id=f"call_v1_{int(time.time() * 1000)}",
                        name="run_command",
                        input={"command": "pytest -v tests/test_calc.py"},
                    ),
                    ToolCall(
                        id=f"call_v2_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "verify-report",
                            "type": "verify_report",
                            "content": verify_md,
                            "json_metadata": {"verdict": "pass", "passed": 2, "failed": 0},
                        },
                    ),
                ],
                usage=ModelUsage(input_tokens=500, output_tokens=350),
                stop_reason="tool_use",
            )

        if is_align:
            align_md = """# Semantic Alignment Report

## Verdict: ALIGNED

## Evaluation Summary
- **Stakeholder Vision**: Fast, zero-dependency arithmetic functions for CLI and automated scripts.
- **Delivered Product**: Clean, verified addition and subtraction functions matching all criteria.
- **Drift Score**: 0.00 (No requirement or scope drift detected).
"""
            return ModelResponse(
                text="Evaluating stakeholder semantic alignment.",
                tool_calls=[
                    ToolCall(
                        id=f"call_align_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "align-report",
                            "type": "align_report",
                            "content": align_md,
                            "json_metadata": {
                                "verdict": "ALIGNED",
                                "drift_detected": False,
                                "semantic_score": 1.0,
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=450, output_tokens=250),
                stop_reason="tool_use",
            )

        if is_release:
            rel_md = """# Release Notes - v0.1.0

## Highlights
- Initial production release of calculator arithmetic engine.
- Implemented addition and subtraction with comprehensive automated tests.
- 100% verification and alignment sign-off.
"""
            changelog_content = """# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - Initial Release
### Added
- Addition and subtraction calculation functions (`generated/calc.py`).
- Automated unit test suite (`tests/test_calc.py`).
"""
            return ModelResponse(
                text="Packaging release and generating changelog.",
                tool_calls=[
                    ToolCall(
                        id=f"call_rel1_{int(time.time() * 1000)}",
                        name="fs_write_file",
                        input={"path": "CHANGELOG.md", "content": changelog_content},
                    ),
                    ToolCall(
                        id=f"call_rel2_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "release-manifest",
                            "type": "release_manifest",
                            "content": rel_md,
                            "json_metadata": {
                                "version": "0.1.0",
                                "status": "RELEASED",
                                "verification": "PASS",
                                "alignment": "PASS",
                            },
                        },
                    ),
                ],
                usage=ModelUsage(input_tokens=450, output_tokens=300),
                stop_reason="tool_use",
            )

        if is_retro:
            retro_md = """# Lifecycle Retrospective Report

## Executive Summary
- Execution completed all 12 phases from Intake to Release.
- Zero backward retry loops required.
- Quality Grade: A

## Recommendations for Future Iterations
1. Maintain test-first test design before code synthesis.
2. Continue enforcing strict AC traceability matrix.
"""
            return ModelResponse(
                text="Synthesizing retrospective analysis.",
                tool_calls=[
                    ToolCall(
                        id=f"call_retro_{int(time.time() * 1000)}",
                        name="write_artifact",
                        input={
                            "logical_name": "retro",
                            "type": "retro",
                            "content": retro_md,
                            "json_metadata": {
                                "total_phases_executed": 12,
                                "backward_loops_count": 0,
                                "overall_quality_grade": "A",
                            },
                        },
                    )
                ],
                usage=ModelUsage(input_tokens=500, output_tokens=300),
                stop_reason="tool_use",
            )

        return ModelResponse(text="OK", tool_calls=[])


class ModelRouter:
    def __init__(self, provider_override: Optional[str] = None):
        self.provider_override = provider_override
        self.adapters: Dict[str, ModelProviderAdapter] = {
            "anthropic": AnthropicAdapter(),
            "agy": AgyAdapter(),
            "mock": MockAdapter(),
        }

    def resolve_provider(self) -> Tuple[str, ModelProviderAdapter]:
        # 1. Explicit provider flag
        if self.provider_override:
            p = self.provider_override.lower().strip()
            if p == "mock":
                return "mock", self.adapters["mock"]
            elif p == "anthropic":
                adapter = self.adapters["anthropic"]
                if not adapter.is_available():
                    raise RuntimeError("ANTHROPIC_API_KEY is not set or empty in environment")
                return "anthropic", adapter
            elif p == "agy":
                adapter = self.adapters["agy"]
                if not adapter.is_available():
                    raise RuntimeError("agy CLI is not available or authenticated")
                return "agy", adapter
            else:
                raise ValueError(f"Unsupported provider: '{self.provider_override}'. Choose from: anthropic, agy, mock.")

        # 2. Priority: ANTHROPIC_API_KEY -> agy -> explicit error
        anthropic_adapter = self.adapters["anthropic"]
        if anthropic_adapter.is_available():
            return "anthropic", anthropic_adapter

        agy_adapter = self.adapters["agy"]
        if agy_adapter.is_available():
            return "agy", agy_adapter

        # 3. Explicit error (never silent mock)
        raise RuntimeError(
            "No LLM provider available. Neither ANTHROPIC_API_KEY is configured nor was an authenticated agy CLI found. "
            "Set ANTHROPIC_API_KEY, authenticate agy, or pass --provider mock explicitly."
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        _, adapter = self.resolve_provider()
        return adapter.complete(request)

