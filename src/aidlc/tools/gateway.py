import json
import os
import re
import subprocess
from typing import Any, Callable, Dict, List, Optional

from aidlc.artifact_store import ArtifactStore
from aidlc.model_router import ToolCall, ToolDefinition, ToolResult
from aidlc.state import StateManager


class ToolGateway:
    def __init__(
        self,
        workspace_dir: str,
        state_manager: StateManager,
        artifact_store: ArtifactStore,
        ask_user_fn: Optional[Callable[[str, Optional[List[str]]], str]] = None,
    ):
        self.workspace_dir = workspace_dir
        self.state_manager = state_manager
        self.artifact_store = artifact_store
        self.ask_user_fn = ask_user_fn

        self.phase_policies: Dict[str, List[str]] = {
            "intake": ["write_artifact", "read_artifact", "ask_user", "complete_phase"],
            "scaffold": [
                "fs_read_file",
                "fs_write_file",
                "fs_list_files",
                "write_artifact",
                "read_artifact",
                "complete_phase",
            ],
            "spec": [
                "write_artifact",
                "read_artifact",
                "ask_user",
                "read_human_input",
                "flag_finding",
                "complete_phase",
            ],
            "analyze-risks": [
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "create-test-plan": [
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "test-design": [
                "fs_read_file",
                "fs_write_file",
                "fs_list_files",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "create-tests": [
                "fs_read_file",
                "fs_write_file",
                "fs_list_files",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "build": [
                "fs_read_file",
                "fs_write_file",
                "fs_list_files",
                "run_command",
                "write_artifact",
                "read_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "adversarial-review": [
                "fs_read_file",
                "fs_list_files",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "red_team_review": [
                "fs_read_file",
                "fs_list_files",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "red-team-review": [
                "fs_read_file",
                "fs_list_files",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "verify": [
                "fs_read_file",
                "fs_list_files",
                "run_command",
                "write_artifact",
                "read_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "align": [
                "fs_read_file",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "release": [
                "fs_read_file",
                "fs_write_file",
                "read_artifact",
                "write_artifact",
                "flag_finding",
                "complete_phase",
            ],
            "retro": [
                "read_artifact",
                "write_artifact",
                "complete_phase",
            ],
        }

    def get_tool_definitions(self, phase: str) -> List[ToolDefinition]:
        allowed = self.phase_policies.get(phase, [])
        return [t for t in self._get_all_tool_definitions() if t.name in allowed]

    def execute_tool(self, tool_call: ToolCall, run_id: str, phase: str) -> ToolResult:
        allowed = self.phase_policies.get(phase, [])
        if tool_call.name not in allowed:
            return ToolResult(
                tool_use_id=tool_call.id,
                content=f"Policy violation: Phase '{phase}' is not authorized to execute tool '{tool_call.name}'.",
                is_error=True,
            )

        try:
            output = self._dispatch(tool_call.name, tool_call.input, run_id, phase)
            return ToolResult(tool_use_id=tool_call.id, content=output, is_error=False)
        except Exception as e:
            return ToolResult(
                tool_use_id=tool_call.id,
                content=f"Error executing tool '{tool_call.name}': {str(e)}",
                is_error=True,
            )

    def _dispatch(self, name: str, inp: Dict[str, Any], run_id: str, phase: str) -> str:
        if name == "fs_read_file":
            target = os.path.join(self.workspace_dir, inp["path"])
            if not os.path.exists(target):
                raise FileNotFoundError(f"File not found: {inp['path']}")
            with open(target, "r", encoding="utf-8") as f:
                return f.read()

        elif name == "fs_write_file":
            target = os.path.join(self.workspace_dir, inp["path"])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(inp["content"])
            return f"Successfully wrote {len(inp['content'].encode('utf-8'))} bytes to {inp['path']}"

        elif name == "fs_list_files":
            rel_dir = inp.get("dir")
            target_dir = os.path.join(self.workspace_dir, rel_dir) if rel_dir else self.workspace_dir
            if not os.path.exists(target_dir):
                return json.dumps([])

            entries = []
            recursive = inp.get("recursive", True)
            for root, dirs, files in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in (".git", ".aidlc", "node_modules", "__pycache__", ".pytest_cache")]
                for file in files:
                    full = os.path.join(root, file)
                    entries.append(os.path.relpath(full, self.workspace_dir))
                if not recursive:
                    break
            return json.dumps(entries, indent=2)

        elif name == "run_command":
            cmd = inp["command"]
            cwd = os.path.join(self.workspace_dir, inp.get("cwd", "")) if inp.get("cwd") else self.workspace_dir
            try:
                res = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return json.dumps(
                    {
                        "exitCode": res.returncode,
                        "stdout": res.stdout,
                        "stderr": res.stderr,
                    }
                )
            except subprocess.TimeoutExpired:
                return json.dumps({"exitCode": 124, "stdout": "", "stderr": "Command timed out"})
            except Exception as e:
                return json.dumps({"exitCode": 1, "stdout": "", "stderr": str(e)})

        elif name == "write_artifact":
            raw_name = inp.get("logical_name") or inp.get("name") or phase
            clean_name = re.sub(r"\.(md|json)$", "", str(raw_name), flags=re.IGNORECASE)
            type_ = inp.get("type") or phase
            content = inp["content"]
            json_meta = inp.get("json_metadata")
            verdict = inp.get("verdict", "info")

            artifact = self.artifact_store.store_artifact(
                run_id=run_id,
                phase=phase,
                logical_name=clean_name,
                type_=type_,
                content=content,
                agent_name=f"{phase}-agent",
                verdict=verdict,
                json_metadata=json_meta,
            )
            self.state_manager.add_artifact(run_id, artifact)

            return json.dumps(
                {
                    "success": True,
                    "artifact_id": artifact["id"],
                    "version": artifact["version"],
                    "content_uri": artifact["content_uri"],
                    "checksum": artifact["checksum"],
                }
            )

        elif name == "read_artifact":
            logical_name = inp.get("logical_name")
            target_phase = inp.get("phase") or phase
            direct_path = inp.get("path")

            if logical_name:
                latest = self.artifact_store.get_latest_artifact_content(run_id, target_phase, logical_name)
                if latest:
                    return latest[0]

            if direct_path:
                return self.artifact_store.read_artifact(direct_path)

            raise ValueError("read_artifact requires either 'logical_name' or 'path'")

        elif name == "flag_finding":
            finding = {
                "id": inp.get("id") or f"FIND-{os.urandom(2).hex()}",
                "phase": phase,
                "severity": inp.get("severity", "major"),
                "category": inp.get("category", "correctness"),
                "title": inp.get("title", "Identified finding"),
                "description": inp.get("description", ""),
                "status": "open",
                "evidence": inp.get("evidence", []),
            }
            self.state_manager.add_finding(run_id, finding)
            return json.dumps({"success": True, "finding_id": finding["id"]})

        elif name in ("ask_user", "read_human_input"):
            prompt = inp.get("question") or inp.get("prompt") or ""
            options = inp.get("options")
            if self.ask_user_fn:
                return self.ask_user_fn(prompt, options)
            return inp.get("default", "Proceed with defaults")

        elif name == "complete_phase":
            return json.dumps(
                {
                    "completed": True,
                    "status": inp.get("status", "passed"),
                    "verdict": inp.get("verdict", "pass"),
                    "summary": inp.get("summary", ""),
                }
            )

        else:
            raise ValueError(f"Unrecognized tool: {name}")

    def _get_all_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="fs_read_file",
                description="Read the contents of a file in the workspace.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Relative path to file"}},
                    "required": ["path"],
                },
            ),
            ToolDefinition(
                name="fs_write_file",
                description="Write content to a file in the workspace.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "content": {"type": "string", "description": "File content"},
                    },
                    "required": ["path", "content"],
                },
            ),
            ToolDefinition(
                name="fs_list_files",
                description="List files in the workspace directory.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "dir": {"type": "string", "description": "Subdirectory to list"},
                        "recursive": {"type": "boolean", "description": "Recursive scan"},
                    },
                },
            ),
            ToolDefinition(
                name="run_command",
                description="Execute a shell command (e.g. running tests with pytest).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command line to execute"},
                        "cwd": {"type": "string", "description": "Relative working directory"},
                    },
                    "required": ["command"],
                },
            ),
            ToolDefinition(
                name="write_artifact",
                description="Store an immutable versioned artifact (Markdown or JSON) for this phase.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "logical_name": {"type": "string", "description": "Artifact base name without extension"},
                        "type": {"type": "string", "description": "Artifact type"},
                        "content": {"type": "string", "description": "Artifact content"},
                        "json_metadata": {"type": "object", "description": "Optional companion JSON metadata"},
                        "verdict": {"type": "string", "enum": ["pass", "fail", "warning", "info"]},
                    },
                    "required": ["logical_name", "content"],
                },
            ),
            ToolDefinition(
                name="read_artifact",
                description="Read an artifact produced by this or an earlier phase.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "logical_name": {"type": "string", "description": "Logical artifact name"},
                        "phase": {"type": "string", "description": "Phase that created the artifact"},
                        "path": {"type": "string", "description": "Direct file path"},
                    },
                },
            ),
            ToolDefinition(
                name="flag_finding",
                description="Record an engineering finding (contradiction, risk, or test failure) in state.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique finding ID (e.g. BLOCKER-001)"},
                        "severity": {"type": "string", "enum": ["blocker", "critical", "major", "minor", "info"]},
                        "category": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["title", "severity"],
                },
            ),
            ToolDefinition(
                name="ask_user",
                description="Prompt the human user for a decision or input.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["question"],
                },
            ),
            ToolDefinition(
                name="read_human_input",
                description="Prompt for free-form human text input (e.g. supplied stories).",
                input_schema={
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}},
                    "required": ["prompt"],
                },
            ),
            ToolDefinition(
                name="complete_phase",
                description="Signal completion of the current phase agent execution.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["passed", "failed", "blocked"]},
                        "verdict": {"type": "string", "enum": ["pass", "fail", "warning", "info"]},
                        "summary": {"type": "string"},
                    },
                    "required": ["status"],
                },
            ),
        ]

