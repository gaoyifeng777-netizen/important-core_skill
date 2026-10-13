"""Independent synthetic audit of executable staging boundaries.

These tests assert observable contracts, not particular implementation wording.
No customer materials or global ACL/configuration are used.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from sandbox_adapter import SandboxViolation, compile_contract, sha, stage_task, write_json


def task_for(tmp_path, role="proposal_extract", scope="all"):
    source = tmp_path / "original" / "source.txt"
    source.parent.mkdir()
    source.write_text("ALLOWED FIRST LINE\nOTHER ROLE PRIVATE CANARY\n", encoding="utf-8")
    ref = {"file_id": "F1", "path": str(source), "sha256": sha(source), "assigned_scope": scope}
    output = str(tmp_path / "run" / "role_output.json")
    inp = {"task_id": "T1", "run_id": "R1", "agent_name": role, "meeting_package_id": "M1",
           "files": [ref], "output_path": output}
    return {"task_id": "T1", "run_id": "R1", "agent_name": role,
            "source_refs": [ref], "basis_refs": [], "output_path": output,
            "input_ref": write_json(tmp_path / "run" / "input.json", inp),
            "prompt_ref": write_json(tmp_path / "run" / "prompt.json", {"instruction": "synthetic audit only"}),
            "runtime": {"mode": "windows_appcontainer", "history_inheritance": False}}


def replace_input(task, tmp_path, update):
    inp = json.loads(Path(task["input_ref"]["path"]).read_text(encoding="utf-8"))
    update(inp)
    task["input_ref"] = write_json(tmp_path / "modified.json", inp)


def test_extractor_cannot_register_judge_only_extraction_results(tmp_path):
    task = task_for(tmp_path)
    foreign = tmp_path / "foreign_record_output.json"
    foreign.write_text('{"private": "other role facts"}', encoding="utf-8")
    replace_input(task, tmp_path, lambda inp: inp.update(extraction_results=[{"path": str(foreign), "sha256": sha(foreign)}]))
    with pytest.raises(SandboxViolation):
        compile_contract(task)


@pytest.mark.parametrize("scope", ["line 1", "page 1", {"start": 1, "end": 1}])
def test_partial_scope_never_stages_complete_mixed_original(tmp_path, scope):
    task = task_for(tmp_path, scope=scope)
    with pytest.raises(SandboxViolation):
        stage_task(task, tmp_path / "attempt")


def test_origin_locator_is_not_rewritten_to_sandbox_copy(tmp_path):
    task = task_for(tmp_path)
    original = task["source_refs"][0]["path"]
    def update(inp):
        inp["files"][0]["origin_source"] = {"source_key": "ORIGINAL1", "original_path": original, "version": "V1"}
        inp["files"][0]["origin_map"] = [{"derived_path": original, "derived_location": "line 1",
                                             "original_path": original, "original_location": "line 1"}]
    replace_input(task, tmp_path, update)
    stage = stage_task(task, tmp_path / "attempt")
    assert stage["staged_input"]["files"][0]["path"] != original
    assert stage["staged_input"]["files"][0]["origin_source"]["original_path"] == original
    assert stage["staged_input"]["files"][0]["origin_map"][0]["original_path"] == original


def test_empty_read_adjust_root_is_preserved_as_an_empty_staged_directory(tmp_path):
    task = task_for(tmp_path, role="read_adjust")
    empty = tmp_path / "empty_original"
    empty.mkdir()
    task["source_refs"] = []
    replace_input(task, tmp_path, lambda inp: (inp.pop("files"), inp.update(path=[str(empty)], derived_output_dir=None)))
    stage = stage_task(task, tmp_path / "attempt")
    projected = Path(stage["staged_input"]["path"][0])
    assert projected.is_relative_to(Path(stage["input_dir"]))
    assert projected.is_dir() and not list(projected.iterdir())


def test_long_nested_read_adjust_material_remains_in_assigned_enumeration_root(tmp_path):
    task = task_for(tmp_path, role="read_adjust")
    original = tmp_path / "nested_original"
    source = original / ("nested-" * 8) / ("deeper-" * 8) / "own.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"OWN LONG PATH MATERIAL")
    task["source_refs"] = []
    replace_input(task, tmp_path, lambda inp: (inp.pop("files"), inp.update(path=[str(original)], derived_output_dir=None)))
    stage = stage_task(task, tmp_path / "attempt", role_root=tmp_path / "short")
    enumeration_root = Path(stage["staged_input"]["path"][0])
    copied = list(enumeration_root.rglob("*.pdf"))
    assert len(copied) == 1 and copied[0].read_bytes() == source.read_bytes()
    assert stage["path_map"][str(source)] == str(copied[0])


def test_quality_review_plural_results_are_staged_and_mapped(tmp_path):
    task = task_for(tmp_path, role="quality_review")
    judge = tmp_path / "judge_results.json"
    extracted = tmp_path / "extract_results.json"
    judge.write_text('{"decisions": []}', encoding="utf-8")
    extracted.write_text('{"records": []}', encoding="utf-8")
    def update(inp):
        inp["judge_results"] = [{"path_or_attachment_id": str(judge), "sha256": sha(judge)}]
        inp["extract_results"] = [{"path_or_attachment_id": str(extracted), "sha256": sha(extracted)}]
    replace_input(task, tmp_path, update)
    stage = stage_task(task, tmp_path / "attempt")
    for key, original in (("judge_results", judge), ("extract_results", extracted)):
        projected = Path(stage["staged_input"][key][0]["path_or_attachment_id"])
        assert projected.is_relative_to(Path(stage["input_dir"]))
        assert projected.read_bytes() == original.read_bytes()


@pytest.mark.parametrize("key", ["result", "judge_result"])
def test_quality_review_unknown_singular_input_does_not_expand_authorization(tmp_path, key):
    task = task_for(tmp_path, role="quality_review")
    foreign = tmp_path / "foreign_private_document.json"
    foreign.write_text('{"private": "outside actual review contract"}', encoding="utf-8")
    replace_input(task, tmp_path, lambda inp: inp.update({key: {"path": str(foreign), "sha256": sha(foreign)}}))
    with pytest.raises(SandboxViolation):
        compile_contract(task)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction boundary")
def test_read_adjust_does_not_follow_authorized_root_junction(tmp_path):
    task = task_for(tmp_path, role="read_adjust")
    foreign = tmp_path / "foreign_private_directory"
    foreign.mkdir()
    (foreign / "private.txt").write_text("OUTSIDE AUTHORIZED ROOT CANARY", encoding="utf-8")
    junction = tmp_path / "authorized_junction"
    def ps_quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                             "New-Item -ItemType Junction -Path " + ps_quote(junction) + " -Target " + ps_quote(foreign)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr
    try:
        assert junction.is_junction()
        task["source_refs"] = []
        replace_input(task, tmp_path, lambda inp: (inp.pop("files"), inp.update(path=[str(junction)], derived_output_dir=None)))
        with pytest.raises(SandboxViolation):
            compile_contract(task)
    finally:
        # Remove only the junction itself; never recursively traverse its target.
        os.rmdir(junction)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows AppContainer access checks")
def test_real_worker_cannot_modify_input_metadata_or_write_host_receipt(tmp_path):
    from windows_appcontainer import A, acl_tree, create_profile, delete_profile, launch
    import ctypes
    fixture = tmp_path / "kernel_stage"
    inp, out, host = fixture / "role" / "input", fixture / "role" / "output", fixture / "host"
    inp.mkdir(parents=True)
    out.mkdir()
    host.mkdir()
    (fixture / ".synthetic-appcontainer-root").write_text("Independent synthetic test only", encoding="utf-8")
    source = inp / "original.txt"
    source.write_text("IMMUTABLE OWN SOURCE", encoding="ascii")
    receipt = host / "execution_receipt.json"
    receipt.write_text("TRUSTED HOST RECEIPT CANARY", encoding="ascii")
    script = inp / "probe.cmd"
    script.write_text(
        '@echo off\r\n'
        'type "%AUDIT_INPUT%" > "%AUDIT_OUT%\\own.txt" 2> "%AUDIT_OUT%\\own.err"\r\n'
        'echo WORKER CORRUPTION > "%AUDIT_INPUT%" 2> "%AUDIT_OUT%\\input_write.err"\r\n'
        'attrib +H "%AUDIT_INPUT%" > "%AUDIT_OUT%\\metadata.log" 2>&1\r\n'
        'type "%AUDIT_RECEIPT%" > "%AUDIT_OUT%\\host_read.txt" 2> "%AUDIT_OUT%\\host_read.err"\r\n'
        'echo FORGED RECEIPT > "%AUDIT_RECEIPT%" 2> "%AUDIT_OUT%\\host_write.err"\r\n'
        'exit /b 0\r\n', encoding="ascii")
    name = "sanzhong.audit." + uuid.uuid4().hex
    sid_ptr, sid = create_profile(name)
    try:
        acl_tree(fixture / "role", sid, False)
        acl_tree(out, sid, True)
        result = launch(sid_ptr, [str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"),
                                  "/D", "/Q", "/C", str(script)], out,
                        env={"AUDIT_INPUT": str(source), "AUDIT_OUT": str(out), "AUDIT_RECEIPT": str(receipt)},
                        stdout_path=out / "stdout.log", stderr_path=out / "stderr.log", timeout=20)
        assert result["exit_code"] == 0, result
        assert result["token"]["is_appcontainer"] == 1
        assert (out / "own.txt").read_text(encoding="ascii") == "IMMUTABLE OWN SOURCE"
        assert source.read_text(encoding="ascii") == "IMMUTABLE OWN SOURCE"
        assert not (source.stat().st_file_attributes & 0x2), "Worker changed read-only input metadata"
        assert (out / "host_read.txt").read_bytes() == b"", "Worker could read trusted host receipt"
        assert receipt.read_text(encoding="ascii") == "TRUSTED HOST RECEIPT CANARY"
    finally:
        A.FreeSid(sid_ptr)
        delete_profile(name)


def test_model_broker_refuses_remote_item_reference_before_forwarding():
    import httpx
    from model_auth_broker import AuthBrokerError, CodexAuthBroker
    forwarded = []
    def fake_upstream(request):
        forwarded.append(request)
        completed = {"type": "response.completed", "response": {"status": "completed", "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}]}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=("data: " + json.dumps(completed) + "\n\n").encode("utf-8"))
    broker = CodexAuthBroker({"tokens": {"access_token": "SYNTHETIC-NOT-A-REAL-CREDENTIAL"}},
                            proxy=None, serve_http=False, upstream_transport=httpx.MockTransport(fake_upstream))
    try:
        with pytest.raises(AuthBrokerError):
            broker.respond({"model": "synthetic-model", "input": [{"type": "item_reference", "id": "msg_foreign_stored_item"}],
                            "tools": []})
        assert forwarded == [], "Remote item references must be rejected before any upstream request"
    finally:
        broker.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows real-worker scripted inference")
def test_scripted_kernel_host_rejects_conflicting_business_outputs(tmp_path):
    from langgraph_runtime import Runtime
    from sandbox_executor import execute_task
    # Keep the new runtime root short; this test concerns output adoption, not
    # the host Windows MAX_PATH configuration or global long-path settings.
    runtime = Runtime(tmp_path.parent / "kp")
    runtime.init({"project_id": "SYNTHETIC-AUDIT-MISMATCH", "model": "scripted-fixture"})
    runtime.event("enqueue", {"agent_name": "base_rule", "batch_id": "B1", "input": {"source_files": []}})
    task = next(iter(runtime.status(True)["tasks"].values()))
    calls = []
    def scripted_inference(payload):
        calls.append(payload)
        if len(calls) == 1:
            received = json.loads(payload["input"][0]["content"][0]["text"].split("\n", 1)[1])
            wrong = {k: task[k] for k in ("task_id", "run_id", "agent_name")}
            wrong["fact"] = "FILE A"
            return {"status": "completed", "output": [{"type": "function_call", "call_id": "write-A", "name": "write_file",
                    "arguments": json.dumps({"path": received["output_path"], "content": json.dumps(wrong)})}]}
        correct = {k: task[k] for k in ("task_id", "run_id", "agent_name")}
        correct["fact"] = "ASSISTANT B"
        return {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": json.dumps(correct)}]}]}
    result = execute_task(runtime.project, task["task_id"], model="scripted-fixture", timeout=30, inference=scripted_inference)
    assert len(calls) == 2, result
    assert result["ok"] is False, "Host must never adopt FILE A after the assistant delivers distinct JSON B"
    audit_path = Path(result["failed_attempt_path"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["model_process"]["token"]["is_appcontainer"] == 1
    outputs = Path(audit["role_root"]) / "output"
    assert json.loads((outputs / "role_output.json").read_text(encoding="utf-8"))["fact"] == "FILE A"
    assert json.loads((outputs / "final_message.json").read_text(encoding="utf-8"))["fact"] == "ASSISTANT B"
    assert not (audit_path.parent / "execution_receipt.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="NTFS hard-link import guard")
def test_host_does_not_import_worker_hardlink_as_normal_output(tmp_path):
    from sandbox_executor import untrusted_file
    original = tmp_path / "host_reference.json"
    original.write_text('{"private": "synthetic"}', encoding="utf-8")
    linked = tmp_path / "worker_output.json"
    os.link(original, linked)
    assert linked.stat().st_nlink == 2
    with pytest.raises(SandboxViolation):
        untrusted_file(linked)
