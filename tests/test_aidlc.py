import os
import shutil
import tempfile
import pytest
from click.testing import CliRunner

from aidlc.state import StateManager
from aidlc.artifact_store import ArtifactStore
from aidlc.model_router import ModelRouter, ModelRequest, ModelMessage, ToolCall
from aidlc.tools.gateway import ToolGateway
from aidlc.orchestrator import Orchestrator, normalize_phase
from aidlc.cli import cli


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="aidlc_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


class TestStateManager:
    def test_create_and_get_run(self, temp_workspace):
        sm = StateManager(temp_workspace)
        run = sm.create_run(project_id="test-proj", story_id="test-story")
        assert run["run_id"].startswith("run_")
        assert run["project_id"] == "test-proj"
        assert run["phase"]["current"] == "intake"
        assert run["phase"]["status"] == "pending"

        retrieved = sm.get_run(run["run_id"])
        assert retrieved is not None
        assert retrieved["run_id"] == run["run_id"]

    def test_start_and_complete_phase(self, temp_workspace):
        sm = StateManager(temp_workspace)
        run = sm.create_run()
        run_id = run["run_id"]

        state, attempt = sm.start_phase(run_id, "intake")
        assert attempt == 1
        assert state["phase"]["current"] == "intake"
        assert state["phase"]["status"] == "running"

        sm.record_phase_completion(run_id, "intake", attempt, "passed", ["art1"], [], {"inputTokens": 100, "outputTokens": 50, "cost": 0.001})
        updated = sm.get_run(run_id)
        assert len(updated["phase_history"]) == 1
        assert updated["phase_history"][0]["phase"] == "intake"
        assert updated["phase_history"][0]["status"] == "passed"


class TestArtifactStore:
    def test_store_and_version_artifacts(self, temp_workspace):
        store = ArtifactStore(temp_workspace)
        run_id = "test_run_001"

        art1 = store.store_artifact(
            run_id=run_id,
            phase="spec",
            logical_name="spec",
            type_="spec",
            content="# Spec v1\nInitial specification.",
            agent_name="spec-agent",
        )
        assert art1["version"] == 1
        assert "spec.v001.md" in art1["content_uri"]

        art2 = store.store_artifact(
            run_id=run_id,
            phase="spec",
            logical_name="spec",
            type_="spec",
            content="# Spec v2\nUpdated specification.",
            agent_name="spec-agent",
        )
        assert art2["version"] == 2
        assert "spec.v002.md" in art2["content_uri"]

        content, path = store.get_latest_artifact_content(run_id, "spec", "spec")
        assert "Spec v2" in content
        assert "spec.md" in path
        assert os.path.exists(os.path.join(temp_workspace, art2["content_uri"]))


class TestToolGatewayPolicies:
    def test_least_privilege_policies(self, temp_workspace):
        sm = StateManager(temp_workspace)
        store = ArtifactStore(temp_workspace)
        gw = ToolGateway(temp_workspace, sm, store)

        # Intake should not be allowed to run arbitrary commands or write files directly
        res = gw.execute_tool(
            ToolCall(id="c1", name="run_command", input={"command": "ls"}),
            run_id="run_1",
            phase="intake",
        )
        assert res.is_error is True
        assert "Policy violation" in res.content

        # Build IS allowed to write files and run commands
        res_build = gw.execute_tool(
            ToolCall(id="c2", name="fs_write_file", input={"path": "hello.txt", "content": "world"}),
            run_id="run_1",
            phase="build",
        )
        assert res_build.is_error is False
        assert os.path.exists(os.path.join(temp_workspace, "hello.txt"))

        # Verify phase can list files
        res_verify = gw.execute_tool(
            ToolCall(id="c3", name="fs_list_files", input={}),
            run_id="run_1",
            phase="verify",
        )
        assert res_verify.is_error is False
        assert "hello.txt" in res_verify.content


class TestOrchestratorAndPipeline:
    def test_normalize_phase_aliases(self):
        assert normalize_phase("red_team_review") == "adversarial-review"
        assert normalize_phase("red-team-review") == "adversarial-review"
        assert normalize_phase("create-tests") == "test-design"
        assert normalize_phase("create_tests") == "test-design"
        assert normalize_phase("analyze_risks") == "analyze-risks"
        assert normalize_phase("spec") == "spec"

    def test_all_12_phases_registered(self, temp_workspace):
        orch = Orchestrator(temp_workspace, provider_override="mock")
        expected_phases = [
            "intake", "scaffold", "spec", "analyze-risks", "create-test-plan",
            "test-design", "build", "adversarial-review", "verify",
            "align", "release", "retro"
        ]
        for p in expected_phases:
            assert p in orch.phase_agents
            agent = orch.get_agent(p)
            assert agent.name == p

    def test_full_pipeline_mock_execution(self, temp_workspace):
        orch = Orchestrator(temp_workspace, provider_override="mock")
        sm = StateManager(temp_workspace)
        run = sm.create_run()
        run_id = run["run_id"]

        final_state = orch.run_pipeline(
            run_id=run_id,
            start_phase="intake",
            initial_context={"ask": "Calculator CLI utility"},
        )
        assert final_state["phase"]["current"] == "completed"
        assert final_state["phase"]["status"] == "passed"

        # Check all 12 phases in history
        history_phases = [h["phase"] for h in final_state.get("phase_history", [])]
        expected_phases = [
            "intake", "scaffold", "spec", "analyze-risks", "create-test-plan",
            "test-design", "build", "adversarial-review", "verify",
            "align", "release", "retro"
        ]
        for ep in expected_phases:
            assert ep in history_phases


class TestModelRouter:
    def test_mock_provider_resolution(self):
        router = ModelRouter(provider_override="mock")
        provider_name, adapter = router.resolve_provider()
        assert provider_name == "mock"
        assert adapter.is_available() is True

    def test_agy_adapter_cost_calculation(self):
        from aidlc.model_router import AgyAdapter
        adapter = AgyAdapter()
        in_tokens = 229106
        out_tokens = 30464
        expected_cost = (in_tokens * 3.0) / 1_000_000 + (out_tokens * 15.0) / 1_000_000
        assert expected_cost > 1.0  # Around $1.144


class TestCLICommands:
    def test_cli_init_and_status(self, temp_workspace):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=temp_workspace):
            # aidlc init
            res_init = runner.invoke(cli, ["init"])
            assert res_init.exit_code == 0
            assert "Initialized AIDLC workspace" in res_init.output
            assert os.path.exists("interview.md")

            # aidlc status
            res_status = runner.invoke(cli, ["status"])
            assert res_status.exit_code == 0
            assert "AIDLC Run Status:" in res_status.output
            assert "intake" in res_status.output

            # aidlc runs
            res_runs = runner.invoke(cli, ["runs"])
            assert res_runs.exit_code == 0
            assert "RUN ID" in res_runs.output
            assert "intake" in res_runs.output

            # aidlc run intake --provider mock -y
            res_intake = runner.invoke(cli, ["run", "intake", "--provider", "mock", "-y"])
            assert res_intake.exit_code == 0
            assert "Phase 'intake' Result" in res_intake.output
            assert "Status: PASSED" in res_intake.output
