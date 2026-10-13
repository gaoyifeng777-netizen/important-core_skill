"""Synthetic control-plane tests; these are not customer-workbook/business acceptance."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from langgraph_runtime import Runtime, RuntimeViolation, EXTRACTORS, DIMENSIONS, digest, load_json, write_once


class Case:
    def __init__(self, root):
        self.root = root
        self.runtime = Runtime(root / "run")
        self.runtime.init({"project_id": "SYNTHETIC-CONTROL-ONLY", "entity": "虚构验证单位", "period": "2099", "execution_mode": "codex_external_bridge"})
        self.sources = {}
        for role in EXTRACTORS:
            path = root / f"{role}.txt"
            path.write_text("虚构会议原文，仅用于软件控制测试。证据不足不能推定未履行。\n", encoding="utf-8")
            self.sources[role] = {"path": str(path.resolve()), "sha256": digest(path), "file_id": "F001",
                                  "assigned_scope": "all", "version": "synthetic-1", "origin_map": None,
                                  "document_type": role, "extraction_refs": []}
        self.basis = write_once(root / "synthetic-human-basis.txt", b"SYNTHETIC human confirmation fixture, not customer evidence")

    def gate(self, gate_id="G1", version="v1", items=None, ready=True):
        if items is None:
            if gate_id == "G1":
                items = [{"item_id": role, "label": "虚构" + role,
                          "payload": {"batch_ids": ["B1"], "ready": ready, "source_refs": [source]}}
                         for role, source in self.sources.items()]
            else:
                items = [{"item_id": "RULE1", "label": "虚构待确认规则一",
                          "payload": {"rule_id": "SYN-R1", "version": "SYN-1", "text": "仅为软件验证虚构规则",
                                      "confirmation_status": "pending", "source_refs": []}}]
        manifest = {"gate_id": gate_id, "version": version, "title": "虚构验证确认单", "items": items,
                    "producer_task_ids": [], "basis_refs": [self.basis]}
        self.runtime.event("propose_gate", manifest)
        return manifest

    def confirm(self, gate_id="G1", decision="all", approved=None, conditions=None, **changes):
        gate = self.runtime.status(True)["gates"][gate_id]
        record = {"confirmation_id": "SYN-C-" + uuid.uuid4().hex, "gate_id": gate_id, "version": gate["version"],
                  "manifest_sha256": gate["manifest_ref"]["sha256"], "decision": decision,
                  "approved_item_ids": approved if approved is not None else [i["item_id"] for i in gate["manifest"]["items"]],
                  "conditions": conditions or [], "confirmed_by": "synthetic-human-fixture",
                  "authority_ref": "explicitly simulated confirmation for control test only"}
        record.update(changes)
        self.runtime.event("confirm", record)
        return record

    def refs(self, roles=None):
        state = self.runtime.status(True)
        refs = [{"gate_id": "G1", "version": state["gates"]["G1"]["version"], "item_ids": roles or list(EXTRACTORS)}]
        if "G2" in state["gates"]:
            refs.append({"gate_id": "G2", "version": state["gates"]["G2"]["version"], "item_ids": ["RULE1"]})
        return refs

    def extraction_spec(self, role):
        return {"agent_name": role, "batch_id": "B1", "input": {"meeting_package_id": "SYN-B1", "files": [self.sources[role]]},
                "gate_refs": self.refs([role])[:1]}

    def enqueue(self, spec):
        before = set(self.runtime.status(True)["tasks"])
        self.runtime.event("enqueue", spec)
        state = self.runtime.status(True)
        return state["tasks"][(set(state["tasks"]) - before).pop()]

    def extract_data(self, task):
        data = load_json(ROOT / "validation" / "behavior" / "results" / (task["agent_name"] + ".json"))
        data.update({k: task[k] for k in ("task_id", "run_id", "agent_name")})
        data["meeting_package_id"] = "SYN-B1"
        data["coverage"][0]["assigned_scope"] = "all"
        return data

    def submit(self, task, data, receipt_changes=None):
        ref = write_once(self.root / (uuid.uuid4().hex + ".json"), data)
        receipt = {k: task[k] for k in ("task_id", "run_id", "agent_name")}
        receipt.update({"input_sha256": task["input_ref"]["sha256"], "result_sha256": ref["sha256"],
                        "context_id": "synthetic-test-context-" + uuid.uuid4().hex, "history_inheritance": False,
                        "executed": True, "executor": "codex-collaboration"})
        if receipt_changes:
            receipt.update(receipt_changes)
        result = self.runtime.event("submit", {"task_id": task["task_id"], "result_ref": ref, "receipt": receipt})
        return result, receipt

    def all_extractions(self):
        self.gate(); self.confirm()
        tasks = []
        for role in EXTRACTORS:
            task = self.enqueue(self.extraction_spec(role))
            self.submit(task, self.extract_data(task))
            assert self.runtime.status(True)["tasks"][task["task_id"]]["status"] == "completed"
            tasks.append(task)
        self.gate("G2"); self.confirm("G2")
        return tasks

    def judge(self, two=True):
        task = self.enqueue({"agent_name": "rule_judge", "batch_id": "B1", "input": {"entity": "虚构验证单位", "period": "2099", "scope": "仅虚构测试事项"}, "gate_refs": self.refs()})
        data = self.judge_data(task, two)
        return task, data

    def judge_data(self, task, two=True):
        inp = load_json(task["input_ref"]["path"])
        data = {"schema_version": "1.3", "prompt_version": "1.4", **{k: task[k] for k in ("task_id", "run_id", "agent_name")},
                "status": "completed", "input_snapshot": inp, "rules_version": inp["rules"]["version"], "dictionary_version": "1.1",
                "links": [], "comparisons": [], "coverage": [], "matters": [], "decisions": [], "leads": [], "lead_scan": [],
                "requests": [], "completion_note": "SYNTHETIC control fixture; no claim of actual business review"}
        for number in range(1, 3 if two else 2):
            mid, did = f"M{number}", f"D{number}"
            data["matters"].append({"matter_id": mid, "title": "虚构测试事项", "link_status": "unlinked", "subject_refs": [], "basis": "测试", "uncertainty": []})
            data["decisions"].append({"decision_id": did, "matter_id": mid, "rule_id": "SYN-R1", "result": "证据不足", "applicability_reason": "虚构软件测试",
                                      "rule_basis": {"rule_id": "SYN-R1", "version": "SYN-1", "source_key": None, "source_file_id": None, "locator": None, "confirmation_ref": inp["rules"]["confirmation_ref"]},
                                      "record_refs": [], "counter_record_refs": [], "source_checks": [], "reason": "未提供执行证据，不能推断未履行", "limits": ["仅为测试"], "needed_evidence": ["执行证据"], "comparison_ids": []})
        return data

    def review_data(self, task, disposition="accepted"):
        inp = load_json(task["input_ref"]["path"])
        src = inp["source_files"][0]
        check = {"source_key": src["source_key"], "file_id": src["file_id"], "version": src["version"], "locator": "L1",
                 "quote": "虚构会议原文，仅用于软件控制测试。证据不足不能推定未履行。", "read_state": "verified"}
        rows = [{"review_id": "RV-" + u["result_ref"]["item_id"], "decision_ref": {"run_id": u["result_ref"]["run_id"], "decision_id": u["result_ref"]["item_id"]},
                 "review_result": disposition, "dimensions": [{"dimension": d, "state": "checked", "basis": "synthetic software fixture"} for d in sorted(DIMENSIONS)],
                 "source_checks": [check], "finding_ids": [], "note": "SYNTHETIC test assertion; not actual review"}
                for u in task["review_target_units"] if u["result_ref"]["collection"] == "decisions"]
        return {"schema_version": "1.0", "prompt_version": "1.4", **{k: task[k] for k in ("task_id", "run_id", "agent_name")},
                "status": "completed", "review_disposition": "pass" if disposition == "accepted" else "return_for_revision",
                "input_snapshot": inp, "rules_version": inp["rules"]["version"], "review_mode": inp["review_mode"],
                "target_run_ids": sorted({u["result_ref"]["run_id"] for u in task["review_target_units"]}),
                "scope_coverage": [{"scope_id": s["scope_id"], "assigned_scope": s["assigned_scope"], "processed_scope": "all", "unprocessed_scope": None,
                                    "review_mode": inp["review_mode"], "population_count": len(rows), "reviewed_count": len(rows), "source_checks": [check],
                                    "omission_state": "checked", "note": "synthetic scan and omission test"} for s in inp["review_scope"]],
                "decision_reviews": rows, "lead_reviews": [], "findings": [], "requests": [], "completion_note": "SYNTHETIC"}


@pytest.fixture
def case(tmp_path):
    return Case(tmp_path)


def test_real_stategraph_sqlite_survives_new_process(case):
    case.gate(); case.confirm()
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_langgraph.py"), "status", "--project", str(case.runtime.project)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0
    assert json.loads(out.stdout)["pending_tasks"][0]["task_id"] == task["task_id"]
    with sqlite3.connect(case.runtime.project / "checkpoints.sqlite") as db:
        assert db.execute("select count(*) from checkpoints").fetchone()[0] >= 7
    case.submit(task, case.extract_data(task))
    assert Runtime(case.runtime.project).status(True)["tasks"][task["task_id"]]["status"] == "completed"


@pytest.mark.parametrize("decision", ["all", "partial", "conditional"])
def test_confirmations_release_only_selected_items_even_old_pending(case, decision):
    case.gate()
    approved = list(EXTRACTORS) if decision == "all" else ["proposal_extract"]
    conditions = [{"item_id": "proposal_extract", "kind": "restriction", "text": "保留虚构范围限制，不得外推"}] if decision == "conditional" else []
    case.confirm(decision=decision, approved=approved, conditions=conditions)
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    assert task["status"] == "pending"
    assert len(task["conditions"]) == len(conditions)
    if decision != "all":
        with pytest.raises(RuntimeViolation, match="unconfirmed"):
            case.enqueue(case.extraction_spec("meeting_record"))


def test_unsatisfied_prerequisite_is_item_local(case):
    case.gate()
    case.confirm(decision="conditional", conditions=[{"item_id": "meeting_record", "kind": "prerequisite", "text": "先取得资料", "satisfied": False}])
    case.enqueue(case.extraction_spec("proposal_extract"))
    with pytest.raises(RuntimeViolation, match="unsatisfied"):
        case.enqueue(case.extraction_spec("meeting_record"))


@pytest.mark.parametrize("changes,match", [({"version": "wrong"}, "stale"), ({"manifest_sha256": "0" * 64}, "hash"), ({"confirmed_by": ""}, "identity")])
def test_stale_or_wrong_confirmation_rejected(case, changes, match):
    case.gate()
    with pytest.raises(RuntimeViolation, match=match):
        case.confirm(**changes)
    assert case.runtime.status(True)["gates"]["G1"]["confirmation_id"] is None


def test_repeat_confirmation_rejected(case):
    case.gate(); record = case.confirm()
    with pytest.raises(RuntimeViolation, match="duplicate"):
        case.runtime.event("confirm", record)


def test_ready_update_does_not_repeat_human_authorization(case):
    case.gate(ready=False); record = case.confirm()
    with pytest.raises(RuntimeViolation, match="not prepared"):
        case.enqueue(case.extraction_spec("proposal_extract"))
    case.runtime.event("mark_ready", {"gate_id": "G1", "version": "v1", "item_id": "proposal_extract", "ready": True, "evidence_refs": [case.basis]})
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    assert task["status"] == "pending"
    assert case.runtime.status(True)["gates"]["G1"]["confirmation_id"] == record["confirmation_id"]


@pytest.mark.parametrize("field,value", [("assigned_scope", "page 999"), ("path", "C:/not-authorized.txt"), ("file_id", "BAD")])
def test_arbitrary_g1_ref_does_not_authorize_actual_source(case, field, value):
    case.gate(); case.confirm()
    spec = case.extraction_spec("proposal_extract")
    spec["input"]["files"] = copy.deepcopy(spec["input"]["files"])
    spec["input"]["files"][0][field] = value
    with pytest.raises(RuntimeViolation, match="does not match"):
        case.enqueue(spec)


@pytest.mark.parametrize("corruption", ["identity", "schema", "coverage", "duplicate_record"])
def test_four_route_structure_returns_local_scope(case, corruption):
    case.gate(); case.confirm()
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    data = case.extract_data(task)
    if corruption == "identity": data["run_id"] = "wrong"
    if corruption == "schema": data["schema_version"] = "0"
    if corruption == "coverage": data["coverage"][0]["file_id"] = "wrong"
    if corruption == "duplicate_record": data["records"].append(copy.deepcopy(data["records"][0]))
    case.submit(task, data)
    state = case.runtime.status(True)
    assert state["tasks"][task["task_id"]]["status"] == "returned"
    assert state["returns"][-1]["business_review_performed"] is False
    assert not state["effective"]


def test_four_routes_required_before_judge(case):
    case.gate(); case.confirm(); case.gate("G2"); case.confirm("G2")
    with pytest.raises(RuntimeViolation, match="four"):
        case.judge()


def test_raw_json_preserved_and_g2_effective_snapshot_overrides_old_pending(case):
    extracts = case.all_extractions()
    judge, data = case.judge()
    inp = load_json(judge["input_ref"]["path"])
    rules = load_json(inp["rules"]["path"])
    assert rules["rules"][0]["confirmation_status"] == "confirmed"
    assert case.runtime.status(True)["gates"]["G2"]["manifest"]["items"][0]["payload"]["confirmation_status"] == "pending"
    assert len(inp["extraction_results"]) == 4
    for ref in inp["extraction_results"]:
        assert digest(ref["path"]) == ref["sha256"]
        assert load_json(ref["path"])["records"]
    case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    ri = load_json(review["input_ref"]["path"])
    assert ri["review_mode"] == "full" and len(ri["extract_results"]) == 4
    assert ri["rules"]["path_or_attachment_id"] == inp["rules"]["path"]
    assert all("path_or_attachment_id" in r for r in ri["judge_results"])
    assert ri["context_declaration"]["judge_internal_analysis_excluded"] is True
    assert case.runtime.status()["reviewed_results"] == []


def test_blanket_pending_on_confirmed_rule_needs_specific_issue(case):
    case.all_extractions(); judge, data = case.judge()
    data["decisions"][0]["result"] = "规则待确认"
    case.submit(judge, data)
    assert case.runtime.status(True)["tasks"][judge["task_id"]]["status"] == "returned"
    case.submit(judge, data, {"specific_rule_issues": {"D1": {"specific_issue_ref": "SYN-specific-entity-period-conflict", "reason": "测试具体主体冲突", "affected_scope": "D1"}}})
    assert case.runtime.status(True)["tasks"][judge["task_id"]]["status"] == "completed"


def test_duplicate_submission_and_reused_context_rejected(case):
    case.gate(); case.confirm()
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    _, receipt = case.submit(task, case.extract_data(task))
    with pytest.raises(RuntimeViolation, match="already submitted"):
        case.submit(task, case.extract_data(task))
    task2 = case.enqueue(case.extraction_spec("meeting_schedule"))
    with pytest.raises(RuntimeViolation, match="context_id reused"):
        case.submit(task2, case.extract_data(task2), {"context_id": receipt["context_id"]})


@pytest.mark.parametrize("changes,match", [({"history_inheritance": True}, "fresh context"), ({"executed": False}, "execution"), ({"input_sha256": "wrong"}, "hash"), ({"result_sha256": "wrong"}, "hash")])
def test_host_receipt_invariants(case, changes, match):
    case.gate(); case.confirm()
    task = case.enqueue(case.extraction_spec("proposal_extract"))
    with pytest.raises(RuntimeViolation, match=match):
        case.submit(task, case.extract_data(task), changes)


def test_missing_original_never_proves_nonperformance(case):
    case.all_extractions(); judge, data = case.judge()
    data["decisions"][0].update(result="初步偏差", reason="没有提供原件，因此未履行")
    case.submit(judge, data)
    state = case.runtime.status(True)
    assert state["tasks"][judge["task_id"]]["status"] == "returned"
    assert "missing original" in state["returns"][-1]["reason"]


def test_review_cannot_self_sample_or_omit_decision(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    rd = case.review_data(review); rd["review_mode"] = "sample"
    case.submit(review, rd)
    assert case.runtime.status(True)["tasks"][review["task_id"]]["status"] == "returned"
    rd = case.review_data(review); rd["decision_reviews"].pop()
    case.submit(review, rd)
    assert "every assigned" in case.runtime.status(True)["returns"][-1]["reason"]


def test_scan_is_explicitly_reviewed_in_transport(case):
    case.all_extractions(); judge, data = case.judge(two=False)
    data["lead_scan"] = [{"scan_id": "S1", "matter_id": "M1", "rule_id": "L01", "rule_version": "1", "state": "insufficient", "record_refs": [], "item_refs": [], "lead_ids": [], "linked_decision_ids": [], "reason": "合成测试证据不足", "limits": []}]
    case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    rd = case.review_data(review)
    case.submit(review, rd)
    assert "scan_reviews" in case.runtime.status(True)["returns"][-1]["reason"]
    case.submit(review, rd, {"scan_reviews": [{"run_id": judge["run_id"], "scan_id": "S1", "review_result": "accepted", "note": "SYNTHETIC scan verification fixture"}]})
    assert case.runtime.status(True)["effective"]["B1:rule_judge:lead_scan:S1"]["review_status"] == "accepted"


def test_local_revision_retains_other_unit_and_requires_new_review(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(review, case.review_data(review))
    before = case.runtime.status(True)
    d2 = copy.deepcopy(before["effective"]["B1:rule_judge:decisions:D2"])
    replacements = {"matters:M1": "B1:rule_judge:matters:M1", "decisions:D1": "B1:rule_judge:decisions:D1"}
    request = {"reason": "虚构局部修改D1", "professional_basis_ref": case.basis,
               "spec": {"agent_name": "rule_judge", "batch_id": "B1", "input": {"entity": "虚构验证单位", "period": "2099", "scope": "仅M1/D1局部修订"}, "gate_refs": case.refs(), "replaces": replacements}}
    case.runtime.event("revise", request)
    revised = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "rule_judge")
    case.submit(revised, case.judge_data(revised, two=False))
    after = case.runtime.status(True)
    assert after["effective"]["B1:rule_judge:decisions:D2"] == d2
    d1 = after["effective"]["B1:rule_judge:decisions:D1"]
    assert d1["review_status"] == "pending" and d1["review_refs"] == [] and d1["replaced_refs"]
    assert len([t for t in after["tasks"].values() if t["agent_name"] == "quality_review"]) == 2


def test_gate_change_invalidates_only_changed_item_dependency(case):
    case.gate(); case.confirm()
    for role in ("proposal_extract", "meeting_record"):
        t = case.enqueue(case.extraction_spec(role)); case.submit(t, case.extract_data(t))
    old = case.runtime.status(True)
    original_units = [u["unit_id"] for u in old["effective"].values() if u["agent_name"] == "meeting_record"]
    manifest = copy.deepcopy(old["gates"]["G1"]["manifest"])
    manifest["version"] = "v2"
    next(i for i in manifest["items"] if i["item_id"] == "proposal_extract")["payload"]["source_refs"][0]["assigned_scope"] = "L1"
    case.runtime.event("propose_gate", manifest)
    new = case.runtime.status(True)
    assert all(new["effective"][uid]["status"] == "effective" for uid in original_units)
    assert any(u["status"] == "stale" for u in new["effective"].values() if u["agent_name"] == "proposal_extract")


def test_final_human_confirmation_is_not_business_review(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    assert case.runtime.status()["final_human_confirmation"] is None
    case.submit(review, case.review_data(review))
    state = case.runtime.status(True)
    assert not state.get("final_human_confirmation")
    u = state["effective"]["B1:rule_judge:decisions:D1"]
    case.gate("FINAL", items=[{"item_id": "FINAL-D1", "label": "虚构单项终签", "payload": {"unit_id": u["unit_id"], "result_ref": u["result_ref"], "human_decision": "虚构测试签认"}}])
    case.confirm("FINAL")
    assert case.runtime.status()["final_human_confirmation"]["unit_ids"] == [u["unit_id"]]


def test_close_partial_preserves_pending_scope_and_resume(case):
    case.gate(); case.confirm(); t = case.enqueue(case.extraction_spec("proposal_extract"))
    case.runtime.event("close_partial", {"reason": "synthetic budget stop"})
    state = Runtime(case.runtime.project).status()
    assert state["status"] == "closed_partial" and state["pending_tasks"][0]["task_id"] == t["task_id"]
    with pytest.raises(RuntimeViolation, match="resume"):
        case.submit(t, case.extract_data(t))
    case.runtime.event("resume", {})
    case.submit(t, case.extract_data(t))
    assert case.runtime.status(True)["tasks"][t["task_id"]]["status"] == "completed"


def test_internal_original_artifacts_are_not_silently_mutable(case):
    case.gate(); case.confirm(); t = case.enqueue(case.extraction_spec("proposal_extract")); case.submit(t, case.extract_data(t))
    ref = case.runtime.status(True)["results"][t["task_id"]]["result_ref"]
    Path(ref["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeViolation, match="sha256 mismatch"):
        case.runtime.status()


def test_current_fourth_route_stale_cannot_be_hidden_by_historical_completion(case):
    case.all_extractions()
    manifest = copy.deepcopy(case.runtime.status(True)["gates"]["G1"]["manifest"])
    manifest["version"] = "v2"
    next(i for i in manifest["items"] if i["item_id"] == "meeting_schedule")["payload"]["source_refs"][0]["assigned_scope"] = "L1"
    case.runtime.event("propose_gate", manifest); case.confirm()
    with pytest.raises(RuntimeViolation, match="currently effective"):
        case.judge()


@pytest.mark.parametrize("key,value", [("version", "unapproved-v999"), ("origin_map", [{"unapproved": True}])])
def test_g1_provenance_version_cannot_change_under_same_hash(case, key, value):
    case.gate(); case.confirm()
    spec = copy.deepcopy(case.extraction_spec("proposal_extract"))
    spec["input"]["files"][0][key] = value
    with pytest.raises(RuntimeViolation, match="differs from G1"):
        case.enqueue(spec)


def test_base_rule_citations_resolve_through_source_files_without_rewriting_citations(case):
    case.all_extractions()
    policy = {**case.basis, "source_key": "POLICY", "file_id": "POLICY", "version": "reading-v1", "assigned_scope": "all", "origin_map": None}
    citation = {"source_key": "POLICY", "file_id": "POLICY", "version": "reading-v1", "locator": "L1", "quote": "SYNTHETIC human confirmation fixture"}
    manifest = copy.deepcopy(case.runtime.status(True)["gates"]["G2"]["manifest"])
    manifest["version"] = "v2"
    manifest["source_files"] = [policy]
    manifest["items"][0]["payload"]["source_refs"] = [citation]
    case.runtime.event("propose_gate", manifest); case.confirm("G2")
    judge, _ = case.judge()
    inp = load_json(judge["input_ref"]["path"])
    assert load_json(inp["rules"]["path"])["rules"][0]["source_refs"] == [citation]
    assert any(s["file_id"] == "POLICY" and s["path"] == policy["path"] for s in inp["source_files"])
    assert all(s["extraction_refs"] for s in inp["source_files"] if s["file_id"] != "POLICY")


@pytest.mark.parametrize("corruption", ["lead_matter", "lead_record", "scan_lead", "matter_subject", "comparison_item", "decision_comparison"])
def test_judge_business_references_are_closed(case, corruption):
    case.all_extractions(); judge, data = case.judge(two=False)
    if corruption.startswith("lead"):
        data["leads"] = [{"lead_id": "L1", "matter_id": "BAD" if corruption == "lead_matter" else "M1", "record_refs": [{"run_id": "never-ran", "record_id": "wrong"}] if corruption == "lead_record" else []}]
    if corruption == "scan_lead":
        data["lead_scan"] = [{"scan_id": "S1", "matter_id": "M1", "lead_ids": ["wrong"], "linked_decision_ids": []}]
    if corruption == "matter_subject":
        data["matters"][0]["subject_refs"] = [{"run_id": "never-ran", "subject_ref": "wrong"}]
    if corruption == "comparison_item":
        data["comparisons"] = [{"comparison_id": "C1", "matter_id": "M1", "link_ids": [], "input_refs": [{"run_id": "never-ran", "record_id": "wrong", "item_index": 999}]}]
    if corruption == "decision_comparison":
        data["decisions"][0]["comparison_ids"] = ["wrong"]
    case.submit(judge, data)
    assert case.runtime.status(True)["tasks"][judge["task_id"]]["status"] == "returned"


@pytest.mark.parametrize("rule_id", [None, "C01"])
def test_blanket_pending_cannot_hide_behind_null_or_catalog_rule(case, rule_id):
    case.all_extractions(); judge, data = case.judge(two=False)
    data["decisions"][0].update(result="规则待确认", rule_id=rule_id)
    case.submit(judge, data)
    assert "specific_issue_ref" in case.runtime.status(True)["returns"][-1]["reason"]


def test_comparison_revision_invalidates_dependent_decision_and_old_review(case):
    case.all_extractions(); judge, data = case.judge()
    data["comparisons"] = [{"comparison_id": "C1", "matter_id": "M1", "link_ids": [], "input_refs": [], "dimension": "测试比较", "operator": "eq", "preconditions": [], "normalization": [], "calculation": "测试", "result": "insufficient", "reason": "仅测试", "limits": []}]
    data["decisions"][0]["comparison_ids"] = ["C1"]
    case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(review, case.review_data(review))
    case.runtime.event("revise", {"reason": "C1比较前提需修订", "professional_basis_ref": case.basis,
                       "spec": {"agent_name": "rule_judge", "batch_id": "B1", "gate_refs": case.refs(), "input": {"scope": "仅比较C1"},
                                "replaces": {"comparisons:C1": "B1:rule_judge:comparisons:C1"}}})
    state = case.runtime.status(True)
    assert state["effective"]["B1:rule_judge:decisions:D1"]["review_status"] == "stale"
    assert state["effective"]["B1:rule_judge:decisions:D2"]["review_status"] == "accepted"


def test_missing_material_authorized_inventory_can_remain_partial(case):
    source = case.sources["meeting_minutes"]
    source.update(path=None, sha256=None, version=None, availability="not_provided")
    case.gate(); case.confirm()
    for role in EXTRACTORS:
        task = case.enqueue(case.extraction_spec(role)); data = case.extract_data(task)
        if role == "meeting_minutes":
            data.update(status="partial", subjects=[], records=[], time_index=[], completion_note="资料未提供；不能推定未履行")
            data["coverage"][0].update(processed_scope=None, unprocessed_scope="all", read_status="not_provided", note="经确认的缺件范围")
            for check in data["field_checks"]:
                check.update(subject_ref=None, state="not_provided", record_ids=[], reason="资料未提供")
            data["candidate_tags"] = []
            data["requests"] = []
        case.submit(task, data)
        assert case.runtime.status(True)["tasks"][task["task_id"]]["status"] == "completed"
    case.gate("G2"); case.confirm("G2")
    judge, data = case.judge(two=False); case.submit(judge, data)
    assert case.runtime.status(True)["tasks"][judge["task_id"]]["status"] == "completed"
    assert next(r for r in load_json(judge["input_ref"]["path"])["extraction_results"] if r["agent_name"] == "meeting_minutes")


def test_review_reduction_requires_bound_human_plan_and_leaves_others_pending(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    with pytest.raises(RuntimeViolation, match="binding"):
        case.runtime.event("scope_review", {"task_id": review["task_id"], "gate_refs": []})
    gate_id = "REVIEW:" + review["task_id"]
    case.gate(gate_id, items=[{"item_id": "sample-plan", "label": "虚构抽样方案", "payload": {"unit_ids": ["B1:rule_judge:decisions:D1"], "selection_basis": "人工明确仅复核D1", "limitations": "D2未复核，不外推"}}])
    case.confirm(gate_id)
    case.runtime.event("scope_review", {"task_id": review["task_id"], "gate_refs": [{"gate_id": gate_id, "version": "v1", "item_ids": ["sample-plan"]}]})
    sampled = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(sampled, case.review_data(sampled))
    state = case.runtime.status(True)
    assert state["effective"]["B1:rule_judge:decisions:D1"]["review_status"] == "accepted"
    assert state["effective"]["B1:rule_judge:decisions:D2"]["review_status"] == "pending"


def test_external_source_drift_removes_old_results_from_reviewed_delivery(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(review, case.review_data(review))
    assert case.runtime.status()["reviewed_results"]
    Path(case.sources["proposal_extract"]["path"]).write_text("changed source bytes", encoding="utf-8")
    status = case.runtime.status()
    assert status["source_integrity_issues"]
    assert status["reviewed_results"] == []


def test_dictionary_guide_is_frozen_and_tampering_rejected(case):
    case.all_extractions()
    dictionary = write_once(case.root / "dictionary.json", {"dictionary_version": "synthetic-1"})
    guide = write_once(case.root / "guide.md", b"Synthetic dictionary interpretation")
    judge = case.enqueue({"agent_name": "rule_judge", "batch_id": "B1", "gate_refs": case.refs(),
                          "input": {"scope": "synthetic", "dictionary": {"path": dictionary["path"], "version": "synthetic-1", "guide_path": guide["path"]}}})
    frozen = load_json(judge["input_ref"]["path"])["dictionary"]
    assert frozen["guide_path"] != guide["path"]
    assert digest(frozen["guide_path"]) == frozen["guide_sha256"]
    Path(guide["path"]).write_text("later source guide version", encoding="utf-8")
    assert case.runtime.status()["pending_tasks"]
    Path(frozen["guide_path"]).write_text("tampered frozen guide", encoding="utf-8")
    with pytest.raises(RuntimeViolation, match="sha256 mismatch"):
        case.runtime.status()


def test_gate_version_cannot_be_recycled(case):
    first = case.gate(); case.confirm()
    changed = copy.deepcopy(first); changed["version"] = "v2"
    case.runtime.event("propose_gate", changed)
    with pytest.raises(RuntimeViolation, match="previously used"):
        case.runtime.event("propose_gate", first)


def test_two_rule_revision_retains_independently_reviewed_other_decision(case):
    case.all_extractions()
    manifest = copy.deepcopy(case.runtime.status(True)["gates"]["G2"]["manifest"])
    manifest["version"] = "two-rules-v1"
    rule2 = copy.deepcopy(manifest["items"][0])
    rule2.update(item_id="RULE2", label="第二条独立虚构规则")
    rule2["payload"]["rule_id"] = "SYN-R2"
    manifest["items"].append(rule2)
    case.runtime.event("propose_gate", manifest); case.confirm("G2")
    refs = case.refs(); refs[1]["item_ids"] = ["RULE1", "RULE2"]
    judge = case.enqueue({"agent_name": "rule_judge", "batch_id": "B1", "gate_refs": refs, "input": {"scope": "两个规则分别对应独立事项"}})
    data = case.judge_data(judge)
    data["decisions"][1]["rule_id"] = "SYN-R2"
    data["decisions"][1]["rule_basis"]["rule_id"] = "SYN-R2"
    case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(review, case.review_data(review))
    before = copy.deepcopy(case.runtime.status(True)["effective"]["B1:rule_judge:decisions:D2"])
    manifest["version"] = "two-rules-v2"
    manifest["items"][0]["payload"]["text"] = "第一条规则经确认拟调整，第二条不变"
    case.runtime.event("propose_gate", manifest)
    after = case.runtime.status(True)
    assert after["effective"]["B1:rule_judge:decisions:D1"]["status"] == "stale"
    assert after["effective"]["B1:rule_judge:decisions:D2"] == before


def test_pending_unaffected_review_item_is_requeued_after_local_revision(case):
    case.all_extractions(); judge, data = case.judge(); case.submit(judge, data)
    original = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.runtime.event("revise", {"reason": "仅D1及对应M1需修订，D2仍须复核", "professional_basis_ref": case.basis,
                       "spec": {"agent_name": "rule_judge", "batch_id": "B1", "gate_refs": case.refs(), "input": {"scope": "仅M1/D1"},
                                "replaces": {"matters:M1": "B1:rule_judge:matters:M1", "decisions:D1": "B1:rule_judge:decisions:D1"}}})
    state = case.runtime.status(True)
    assert state["tasks"][original["task_id"]]["status"] == "stale"
    carried = next(t for t in state["tasks"].values() if t["agent_name"] == "quality_review" and t["status"] == "pending")
    ci = load_json(carried["input_ref"]["path"])
    assert ci["review_mode"] == "full" and ci["sample_basis"] is None
    assert ci["review_scope"][0]["decision_ids"] == ["D2"]
    assert carried["review_partition"]["original_review_task_id"] == original["task_id"]
    assert "B1:rule_judge:decisions:D1" in carried["review_partition"]["invalidated_unit_ids"]
    case.submit(carried, case.review_data(carried))
    state = case.runtime.status(True)
    assert state["effective"]["B1:rule_judge:decisions:D2"]["review_status"] == "accepted"
    assert state["effective"]["B1:rule_judge:decisions:D1"]["review_status"] == "stale"
    revised = next(t for t in state["tasks"].values() if t["agent_name"] == "rule_judge" and t["status"] == "pending")
    case.submit(revised, case.judge_data(revised, two=False))
    fresh_review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    assert {u["result_ref"]["item_id"] for u in fresh_review["review_target_units"] if u["result_ref"]["collection"] == "decisions"} == {"D1"}


@pytest.mark.parametrize("change", ["rule_source_mapping", "human_condition"])
def test_same_rule_payload_cannot_hide_changed_source_binding_or_human_condition(case, change):
    case.all_extractions()
    manifest = copy.deepcopy(case.runtime.status(True)["gates"]["G2"]["manifest"])
    manifest["version"] = "bound-v1"
    source = {**case.basis, "source_key": "POLICY", "file_id": "POLICY", "version": "read-v1", "assigned_scope": "all"}
    manifest["source_files"] = [source]
    manifest["items"][0]["payload"]["source_refs"] = [{"source_key": "POLICY", "file_id": "POLICY", "version": "read-v1", "locator": "L1", "quote": "SYNTHETIC"}]
    case.runtime.event("propose_gate", manifest); case.confirm("G2")
    judge, data = case.judge(two=False); case.submit(judge, data)
    review = next(t for t in case.runtime.status()["pending_tasks"] if t["agent_name"] == "quality_review")
    case.submit(review, case.review_data(review))
    manifest["version"] = "bound-v2"
    if change == "rule_source_mapping":
        other = write_once(case.root / "changed-policy.txt", b"A different synthetic source file")
        manifest["source_files"][0].update(other)
        case.runtime.event("propose_gate", manifest)
    else:
        case.runtime.event("propose_gate", manifest)
        case.confirm("G2", decision="conditional", conditions=[{"item_id": "RULE1", "kind": "restriction", "text": "仅在新条件下采用，既有判断需重新核验"}])
    assert case.runtime.status(True)["effective"]["B1:rule_judge:decisions:D1"]["review_status"] == "stale"
