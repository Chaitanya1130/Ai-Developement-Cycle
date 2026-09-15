import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from aidlc.state import current_iso_timestamp


class ArtifactStore:
    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = workspace_dir or os.getcwd()
        self.base_dir = os.path.join(self.workspace_dir, ".aidlc", "artifacts")
        os.makedirs(self.base_dir, exist_ok=True)

    def get_phase_artifact_dir(self, run_id: str, phase: str) -> str:
        d = os.path.join(self.base_dir, run_id, phase)
        os.makedirs(d, exist_ok=True)
        return d

    def get_next_version(self, run_id: str, phase: str, logical_name: str) -> int:
        d = self.get_phase_artifact_dir(run_id, phase)
        pattern = re.compile(rf"^{re.escape(logical_name)}\.v(\d+)\.")
        max_v = 0
        if os.path.exists(d):
            for fname in os.listdir(d):
                m = pattern.match(fname)
                if m:
                    v = int(m.group(1))
                    if v > max_v:
                        max_v = v
        return max_v + 1

    def store_artifact(
        self,
        run_id: str,
        phase: str,
        logical_name: str,
        type_: str,
        content: str,
        agent_name: str,
        verdict: str = "info",
        json_metadata: Optional[Dict[str, Any]] = None,
        parent_artifacts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        d = self.get_phase_artifact_dir(run_id, phase)
        version = self.get_next_version(run_id, phase, logical_name)
        v_str = f"{version:03d}"

        # Clean logical name of any accidental extensions
        clean_name = re.sub(r"\.(md|json)$", "", logical_name, flags=re.IGNORECASE)

        is_json = content.strip().startswith("{") or content.strip().startswith("[")
        ext = "json" if is_json else "md"

        versioned_file_name = f"{clean_name}.v{v_str}.{ext}"
        versioned_path = os.path.join(d, versioned_file_name)

        with open(versioned_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Unversioned convenience alias
        unversioned_path = os.path.join(d, f"{clean_name}.{ext}")
        with open(unversioned_path, "w", encoding="utf-8") as f:
            f.write(content)

        if json_metadata is not None and ext != "json":
            meta_versioned = f"{clean_name}.v{v_str}.json"
            with open(os.path.join(d, meta_versioned), "w", encoding="utf-8") as f:
                json.dump(json_metadata, f, indent=2)
            with open(os.path.join(d, f"{clean_name}.json"), "w", encoding="utf-8") as f:
                json.dump(json_metadata, f, indent=2)

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        art_id = f"art_{checksum[:12]}_{int(time.time() * 1000)}"
        rel_uri = os.path.relpath(versioned_path, self.workspace_dir)

        artifact_ref = {
            "id": art_id,
            "type": type_,
            "project_id": "default-project",
            "story_id": "default-story",
            "phase": phase,
            "version": version,
            "created_at": current_iso_timestamp(),
            "created_by_agent": agent_name,
            "parent_artifacts": parent_artifacts or [],
            "content_uri": rel_uri,
            "checksum": checksum,
            "verdict": verdict,
            "logical_name": clean_name,
        }

        return artifact_ref

    def read_artifact(self, path_or_uri: str) -> str:
        full_path = (
            path_or_uri
            if os.path.isabs(path_or_uri)
            else os.path.join(self.workspace_dir, path_or_uri)
        )
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Artifact file not found: {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_latest_artifact_content(
        self, run_id: str, phase: str, logical_name: str
    ) -> Optional[Tuple[str, str]]:
        d = self.get_phase_artifact_dir(run_id, phase)
        clean_name = re.sub(r"\.(md|json)$", "", logical_name, flags=re.IGNORECASE)

        # Check unversioned alias first
        for ext in ["md", "json"]:
            p = os.path.join(d, f"{clean_name}.{ext}")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return f.read(), p

        # Check highest versioned
        if not os.path.exists(d):
            return None

        pattern = re.compile(rf"^{re.escape(clean_name)}\.v(\d+)\.(md|json)$")
        max_v = -1
        max_file = None
        for fname in os.listdir(d):
            m = pattern.match(fname)
            if m:
                v = int(m.group(1))
                if v > max_v:
                    max_v = v
                    max_file = fname

        if max_file:
            p = os.path.join(d, max_file)
            with open(p, "r", encoding="utf-8") as f:
                return f.read(), p

        return None

    def list_artifacts_for_run(self, run_id: str) -> List[str]:
        run_dir = os.path.join(self.base_dir, run_id)
        if not os.path.exists(run_dir):
            return []

        results = []
        for root, _, files in os.walk(run_dir):
            for file in files:
                full = os.path.join(root, file)
                results.append(os.path.relpath(full, self.workspace_dir))
        return results

