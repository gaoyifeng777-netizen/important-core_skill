"""Control and staging tests; Windows kernel acceptance is run separately."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from langgraph_runtime import Runtime, RuntimeViolation, digest, write_once
from sandbox_adapter import SandboxViolation, compile_contract, stage_task, validate_sandbox_receipt


def make_task(tmp_path):
    source = tmp_path / "original" / "source.txt"
    source.parent.mkdir()
    source.write_text("synthetic private proposal", encoding="utf-8")
    inp = {"task_id": "T1", "run_id": "R1", "agent_name": "proposal_extract",
           "meeting_package_id": "M1", "files": [{"file_id": "F1", "path": str(source),
           "sha256": digest(source), "assigned_scope": "all"}], "output_path": str(tmp_path / "run" / "role_output.json")}
    return {"task_id": "T1", "run_id": "R1", "agent_name": "proposal_extract", "source_refs": inp["files"],
            "basis_refs": [], "input_ref": write_once(tmp_path / "run" / "input.json", inp),
            "prompt_ref": write_once(tmp_path / "run" / "prompt.md", b"Read only assigned evidence"),
            "runtime": {"mode": "windows_appcontainer", "history_inheritance": False},
            "output_path": inp["output_path"]}


def test_contract_collects_only_authorized_files(tmp_path):
    task = make_task(tmp_path)
    contract = compile_contract(task)
    assert {r["path"] for r in contract["files"]} == {task["source_refs"][0]["path"]}
    assert contract["task_id"] == task["task_id"]


def test_unknown_path_in_input_is_not_implicitly_authorized(tmp_path):
    task = make_task(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("not assigned", encoding="utf-8")
    inp = json.loads(Path(task["input_ref"]["path"]).read_text(encoding="utf-8"))
    inp["unrecognized_file"] = {"path": str(secret), "sha256": digest(secret)}
    task["input_ref"] = write_once(tmp_path / "modified_input.json", inp)
    with pytest.raises(SandboxViolation, match="unregistered"):
        compile_contract(task)


def test_staging_copies_and_preserves_original_mapping(tmp_path):
    task = make_task(tmp_path)
    stage = stage_task(task, tmp_path / "executions" / "attempt1")
    original = Path(task["source_refs"][0]["path"])
    staged = Path(stage["staged_input"]["files"][0]["path"])
    assert staged != original and staged.read_bytes() == original.read_bytes()
    assert stage["path_map"][str(original)] == str(staged)
    assert stage["staged_input"]["output_path"].startswith(str(stage["output_dir"]))


def test_short_role_workspace_is_independent_of_long_archive_path(tmp_path):
    task = make_task(tmp_path)
    archive = tmp_path / ("long-project-" * 3) / ("long-task-" * 3) / "attempt"
    short = tmp_path / "short-role"
    stage = stage_task(task, archive, role_root=short)
    assert Path(stage["role_root"]) == short
    assert Path(stage["host_dir"]).is_relative_to(archive)
    assert Path(stage["staged_input"]["files"][0]["path"]).is_relative_to(short)
    assert Path(stage["staged_input"]["files"][0]["path"]).read_bytes() == Path(task["source_refs"][0]["path"]).read_bytes()


def test_hash_drift_stops_staging(tmp_path):
    task = make_task(tmp_path)
    Path(task["source_refs"][0]["path"]).write_text("changed source", encoding="utf-8")
    with pytest.raises(SandboxViolation, match="hash"):
        stage_task(task, tmp_path / "executions" / "attempt1")


def test_self_reported_sandbox_receipt_without_host_attempt_is_rejected(tmp_path):
    task = make_task(tmp_path)
    result = write_once(tmp_path / "fake.json", {"status": "completed"})
    receipt = {"task_id": "T1", "run_id": "R1", "agent_name": "proposal_extract",
               "executor": "appcontainer-python-agent", "executed": True,
               "sandbox": {"isolation_verified": True, "sid": "made-up"}}
    with pytest.raises(SandboxViolation, match="attempt"):
        validate_sandbox_receipt(tmp_path, task, receipt, result)


def test_new_runtime_requires_sandbox_by_default(tmp_path):
    runtime = Runtime(tmp_path / "run")
    runtime.init({"project_id": "SYNTHETIC-SANDBOX"})
    assert runtime.status(True)["project"]["execution_mode"] == "windows_appcontainer"


def test_explicit_legacy_is_reported_without_claiming_hard_isolation(tmp_path):
    runtime = Runtime(tmp_path / "run")
    runtime.init({"project_id": "SYNTHETIC-LEGACY", "execution_mode": "codex_external_bridge"})
    assert "contractual" in " ".join(runtime.status(True)["limitations"]).lower()


def test_hard_sandbox_task_rejects_native_spawn_receipt(tmp_path):
    runtime = Runtime(tmp_path / "run")
    runtime.init({"project_id": "SYNTHETIC-SANDBOX"})
    runtime.event("enqueue", {"agent_name": "base_rule", "batch_id": "B1", "input": {"source_files": []}})
    task = next(iter(runtime.status(True)["tasks"].values()))
    result = write_once(tmp_path / "fake.json", {"status": "blocked"})
    receipt = {k: task[k] for k in ("task_id", "run_id", "agent_name")}
    receipt.update(input_sha256=task["input_ref"]["sha256"], result_sha256=result["sha256"],
                   executor="codex-collaboration", context_id="fake-context", executed=True, history_inheritance=False)
    with pytest.raises(RuntimeViolation, match="sandbox"):
        runtime.event("submit", {"task_id": task["task_id"], "result_ref": result, "receipt": receipt})
