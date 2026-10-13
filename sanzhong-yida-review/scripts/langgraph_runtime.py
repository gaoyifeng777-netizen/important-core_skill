"""Persistent, fail-closed control plane for the Codex external-task bridge.

This module never invokes Codex tools or a model. The host really dispatches each
task in a fresh context, then submits the original JSON and a host receipt.
Receipts are provenance assertions, not cryptographic identity authentication.
The default executor requires an independently launched whole-process sandbox.
Explicit legacy projects retain contractual scopes without claiming OS isolation.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from typing import Any, TypedDict
import uuid

from validate_result import validate as validate_extraction, load_json

PROTOCOL = "1.0"
EXTRACTORS = ("meeting_schedule", "proposal_extract", "meeting_record", "meeting_minutes")
ROLES = ("read_adjust", "base_rule", *EXTRACTORS, "rule_judge", "quality_review")
IDS = {"records": "record_id", "coverage": "check_id", "matters": "matter_id",
       "links": "link_id", "comparisons": "comparison_id", "decisions": "decision_id",
       "leads": "lead_id", "lead_scan": "scan_id"}
DIMENSIONS = {"rule_applicability", "source_traceability", "fact_fidelity", "matter_linkage",
              "logic_counterevidence", "omission_coverage", "wording_classification"}


class RuntimeViolation(ValueError):
    pass


def need(test, message):
    if not test:
        raise RuntimeViolation(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_once(path, data):
    """Only identical replay of an internal graph write is idempotent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = data if isinstance(data, bytes) else json_bytes(data)
    try:
        with path.open("xb") as f:
            f.write(content)
    except FileExistsError:
        need(path.read_bytes() == content, f"immutable artifact already exists: {path}")
    return {"path": str(path.resolve()), "sha256": digest(path)}


def checked_ref(ref):
    need(isinstance(ref, dict) and ref.get("path") and ref.get("sha256"), "path and sha256 required")
    path = Path(ref["path"])
    need(path.is_absolute() and path.is_file(), f"source/artifact is not an existing absolute file: {path}")
    need(digest(path) == ref["sha256"], f"sha256 mismatch: {path}")
    return ref


def normalized_path(path):
    return os.path.normcase(str(Path(path).resolve()))


def source_key(row):
    return (normalized_path(row["path"]) if row.get("path") else None, row.get("file_id"), row.get("assigned_scope"))


def checked_source(ref):
    if ref.get("availability") == "not_provided":
        need(ref.get("path") is None and ref.get("sha256") is None, "missing source must not claim a path/hash")
        need(ref.get("file_id") and ref.get("assigned_scope"), "missing source needs an explicit inventory scope")
        return ref
    return checked_ref(ref)


def unique_rows(rows, field, label):
    need(isinstance(rows, list), f"{label} must be an array")
    result = {}
    for row in rows:
        need(isinstance(row, dict) and isinstance(row.get(field), str) and row[field].strip(),
             f"{label}: nonblank {field} required")
        need(row[field] not in result, f"{label}: duplicate {field}")
        result[row[field]] = row
    return result


class GraphState(TypedDict, total=False):
    data: dict
    event: dict


class Runtime:
    def __init__(self, project, skill_root=None):
        self.project = Path(project).resolve()
        self.skill_root = Path(skill_root or Path(__file__).resolve().parents[1]).resolve()

    @contextmanager
    def _lock(self):
        self.project.mkdir(parents=True, exist_ok=True)
        # OS lock is released even if the process crashes; the file may remain.
        f = (self.project / ".runtime.lock").open("a+b")
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            f.close()
            raise RuntimeViolation("another runtime command holds the project lock") from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()

    @contextmanager
    def _graph(self):
        from langgraph.graph import StateGraph, START
        from langgraph.types import interrupt
        from langgraph.checkpoint.sqlite import SqliteSaver

        def wait(state):
            event = interrupt(self._summary(state["data"]))
            return {"event": event}

        def apply(state):
            before = copy.deepcopy(state["data"])
            self._refresh_source_drift(before, state["event"]["event_id"])
            updated = copy.deepcopy(before)
            event = state["event"]
            try:
                self._check_internal(before)
                need(event["event_id"] not in before["event_ids"], "duplicate event")
                self._dispatch(updated, event)
                updated["event_ids"].append(event["event_id"])
                updated["last_event"] = {"event_id": event["event_id"], "ok": True, "action": event["action"]}
            except (RuntimeViolation, OSError, ValueError, KeyError, TypeError) as exc:
                updated = copy.deepcopy(before)
                updated["last_event"] = {"event_id": event["event_id"], "ok": False,
                                         "action": event.get("action"), "error": str(exc)}
            return {"data": updated, "event": {}}

        builder = StateGraph(GraphState)
        builder.add_node("await_external_event", wait)
        builder.add_node("apply_validated_event", apply)
        builder.add_edge(START, "await_external_event")
        builder.add_edge("await_external_event", "apply_validated_event")
        builder.add_edge("apply_validated_event", "await_external_event")
        with SqliteSaver.from_conn_string(str(self.project / "checkpoints.sqlite")) as saver:
            yield builder.compile(checkpointer=saver)

    @property
    def graph_config(self):
        return {"configurable": {"thread_id": "sanzhong-review"}, "recursion_limit": 20}

    def init(self, config):
        need(isinstance(config, dict) and config.get("project_id"), "config.project_id required")
        config = copy.deepcopy(config)
        config.setdefault("execution_mode", "windows_appcontainer")
        need(config["execution_mode"] in ("windows_appcontainer", "codex_external_bridge"), "unsupported execution_mode")
        with self._lock(), self._graph() as graph:
            need(not graph.get_state(self.graph_config).values, "project already initialized")
            ref = write_once(self.project / "config.json", config)
            state = {"protocol_version": PROTOCOL, "project": config, "config_ref": ref,
                     "status": "active", "tasks": {}, "gates": {}, "gate_history": {}, "confirmations": {},
                     "results": {}, "effective": {}, "invalidation_log": [], "returns": [],
                     "preparation": {},
                     "event_ids": [], "last_event": None, "limitations": [
                         "Host receipts assert actual isolated context; they are not cryptographic authentication.",
                         ("Whole-process sandbox receipts are required; OS availability and actual model execution are checked by the adapter."
                          if config["execution_mode"] == "windows_appcontainer" else
                          "Allowlist is contractual, not an OS sandbox; explicit legacy executor selected."),
                         "Structural checks do not prove factual accuracy, actual reading, or final human approval."]}
            graph.invoke({"data": state}, self.graph_config)
            return self._summary(state)

    def status(self, full=False):
        with self._lock(), self._graph() as graph:
            state = graph.get_state(self.graph_config).values.get("data")
            need(state, "project not initialized")
            self._check_internal(state)
            self._refresh_source_drift(state, "status-live-source-check")
            return copy.deepcopy(state) if full else self._summary(state)

    def event(self, action, payload):
        from langgraph.types import Command
        with self._lock(), self._graph() as graph:
            snap = graph.get_state(self.graph_config)
            need(snap.values.get("data"), "project not initialized")
            event = {"event_id": uuid.uuid4().hex, "action": action, "payload": payload}
            write_once(self.project / "events" / (event["event_id"] + ".json"), event)
            # If interrupted after validation began, finish that checkpoint first.
            if snap.next and snap.next != ("await_external_event",):
                graph.invoke(None, self.graph_config)
            graph.invoke(Command(resume=event), self.graph_config)
            state = graph.get_state(self.graph_config).values["data"]
            result = self._summary(state)
            if not state["last_event"]["ok"]:
                raise RuntimeViolation(state["last_event"]["error"])
            return result

    def _summary(self, state):
        effective = list(state["effective"].values())
        return {"protocol_version": PROTOCOL, "project_id": state["project"]["project_id"],
                "status": state["status"], "last_event": state["last_event"],
                "pending_tasks": [copy.deepcopy(t) for t in state["tasks"].values() if t["status"] in ("pending", "returned")],
                "gates": copy.deepcopy(state["gates"]), "returns": copy.deepcopy(state["returns"]),
                "effective_results": effective,
                "reviewed_results": [u for u in effective if u["status"] == "effective" and u.get("review_status") == "accepted"],
                "initial_or_limited_results": [u for u in effective if u.get("review_status") != "accepted" or u["status"] != "effective"],
                "final_human_confirmation": state.get("final_human_confirmation"),
                "source_integrity_issues": state.get("source_integrity_issues", []),
                "limitations": state["limitations"]}

    def _refresh_source_drift(self, state, event_id):
        affected_tasks, issues = set(), []
        for tid, task in state["tasks"].items():
            for ref in task.get("source_refs", []):
                try:
                    checked_source(ref)
                except (RuntimeViolation, OSError) as exc:
                    affected_tasks.add(tid)
                    issues.append({"task_id": tid, "source_ref": ref, "issue": str(exc)})
        units = [u["unit_id"] for u in state["effective"].values()
                 if u["result_ref"]["task_id"] in affected_tasks and u["status"] != "stale"]
        if units:
            self._invalidate(state, units, "actual source content/path changed from adopted hash", event_id)
        for tid in affected_tasks:
            if state["tasks"][tid]["status"] in ("pending", "returned"):
                state["tasks"][tid]["status"] = "stale"
        state["source_integrity_issues"] = issues

    def _check_internal(self, state):
        checked_ref(state["config_ref"])
        for task in state["tasks"].values():
            for key in ("input_ref", "envelope_ref", "prompt_ref"):
                checked_ref(task[key])
            for ref in task.get("basis_refs", []):
                checked_ref(ref)
        for result in state["results"].values():
            checked_ref(result["result_ref"])
            checked_ref(result["receipt_ref"])
        for gate in state["gates"].values():
            checked_ref(gate["manifest_ref"])
        for versions in state.get("gate_history", {}).values():
            for gate in versions:
                checked_ref(gate["manifest_ref"])
        for confirmation in state["confirmations"].values():
            checked_ref(confirmation["record_ref"])

    def _dispatch(self, state, event):
        action, payload = event["action"], event["payload"]
        if action == "resume":
            need(state["status"] == "closed_partial", "only closed_partial can resume")
            state["status"] = "active"
            return
        need(state["status"] == "active", "project is closed_partial; explicit resume required")
        if action == "enqueue":
            self._enqueue(state, payload, event["event_id"])
        elif action == "propose_gate":
            self._propose_gate(state, payload, event["event_id"])
        elif action == "confirm":
            self._confirm(state, payload, event["event_id"])
        elif action == "submit":
            self._submit(state, payload, event["event_id"])
        elif action == "revise":
            self._revise(state, payload, event["event_id"])
        elif action == "close_partial":
            need(payload.get("reason"), "close_partial reason required")
            state["status"] = "closed_partial"
            state["close_reason"] = payload["reason"]
        elif action == "scope_review":
            self._scope_review(state, payload, event["event_id"])
        elif action == "mark_ready":
            gate = state["gates"].get(payload.get("gate_id"))
            need(gate and gate["gate_id"] == "G1" and gate["version"] == payload.get("version"), "mark_ready requires current G1 version")
            items, _ = self._gate_items(state, [{"gate_id": "G1", "version": gate["version"], "item_ids": [payload.get("item_id")]}], "G1")
            need(payload.get("ready") is True and payload.get("evidence_refs"), "ready requires actual preparation evidence")
            for ref in payload["evidence_refs"]:
                checked_ref(ref)
            for source in items[0]["payload"]["source_refs"]:
                checked_source(source)
            state.setdefault("preparation", {})[f"G1:{gate['version']}:{payload['item_id']}"] = {"ready": True, "evidence_refs": payload["evidence_refs"], "event_id": event["event_id"]}
        else:
            raise RuntimeViolation(f"unknown action: {action}")

    def _propose_gate(self, state, manifest, event_id):
        gate_id = manifest.get("gate_id")
        need(gate_id in ("G1", "G2", "FINAL") or str(gate_id).startswith("REVIEW:"), "unknown gate_id")
        need(isinstance(manifest.get("version"), str) and manifest["version"].strip(), "gate version required")
        need(manifest.get("title"), "Chinese/reviewable title required")
        items = unique_rows(manifest.get("items"), "item_id", "gate.items")
        need(items, "confirmation manifest cannot be empty")
        for item in items.values():
            need(item.get("label") and isinstance(item.get("payload"), dict), "gate item label/payload required")
        expected = "read_adjust" if gate_id == "G1" else "base_rule"
        producers = manifest.get("producer_task_ids", [])
        bases = manifest.get("basis_refs", [])
        rule_sources = copy.deepcopy(manifest.get("source_files", []))
        if gate_id in ("G1", "G2"):
            need(producers or bases, "gate needs actual preparation result or immutable external basis")
            for tid in producers:
                need(tid in state["results"] and state["tasks"][tid]["agent_name"] == expected,
                     "gate producer role/result mismatch")
                need(state["tasks"][tid]["status"] == "completed", "gate producer not usable")
                if gate_id == "G2":
                    rule_sources.extend(copy.deepcopy(state["tasks"][tid]["source_refs"]))
            for ref in bases:
                checked_ref(ref)
        for item in items.values():
            if gate_id == "G1":
                need(isinstance(item["payload"].get("source_refs"), list), "G1 source_refs required")
                for ref in item["payload"]["source_refs"]:
                    checked_source(ref)
                    need(ref.get("file_id") and ref.get("assigned_scope"), "G1 file_id and exact assigned_scope required")
            elif gate_id == "G2":
                need(item["payload"].get("rule_id") and item["payload"].get("version"), "G2 rule identity/version required")
                for source in item["payload"].get("source_refs", []):
                    if source.get("path") or source.get("availability") == "not_provided":
                        checked_source(source)
                        rule_sources.append(copy.deepcopy(source))
                    else:
                        matches = [s for s in rule_sources if s.get("source_key") == source.get("source_key") and s.get("file_id") == source.get("file_id") and s.get("version") == source.get("version")]
                        need(len(matches) == 1, "G2 citation requires one source_files/producer source match for source_key/file_id/version")
                        checked_source(matches[0])
            elif gate_id == "FINAL":
                current = state["effective"].get(item["payload"].get("unit_id"))
                need(current and current["status"] == "effective" and current.get("review_status") == "accepted", "FINAL only covers effective independently accepted units")
                need(item["payload"].get("result_ref") == current["result_ref"], "FINAL must bind exact adopted result version")
        old = state["gates"].get(gate_id)
        need(not old or old["version"] != manifest["version"], "gate version already exists")
        need(not any(g["version"] == manifest["version"] for g in state.get("gate_history", {}).get(gate_id, [])), "gate version previously used; versions cannot be recycled")
        ref = write_once(self.project / "gates" / event_id / "manifest.json", manifest)
        if old:
            old_items = {i["item_id"]: i["payload"] for i in old["manifest"]["items"]}
            def bound_payload(payload, source_files):
                bound_sources = []
                if gate_id == "G2":
                    for citation in payload.get("source_refs", []):
                        if not citation.get("path"):
                            bound_sources.extend(s for s in source_files if s.get("source_key") == citation.get("source_key") and s.get("file_id") == citation.get("file_id") and s.get("version") == citation.get("version"))
                return {"payload": payload, "resolved_source_files": bound_sources}
            changed_ids = {iid for iid, value in old_items.items() if iid not in items or
                           bound_payload(items[iid]["payload"], rule_sources) != bound_payload(value, old.get("source_files", []))}
            self._invalidate(state, [u["unit_id"] for u in state["effective"].values()
                                     if any(r["gate_id"] == gate_id and set(r["item_ids"]) & changed_ids for r in u.get("gate_item_refs", []))],
                             "gate item changed or removed; unchanged items retained against their original confirmation", event_id)
            for task in state["tasks"].values():
                if task["status"] in ("pending", "returned") and any(r["gate_id"] == gate_id and set(r["item_ids"]) & changed_ids for r in task["gate_refs"]):
                    task["status"] = "stale"
        state["gates"][gate_id] = {"gate_id": gate_id, "version": manifest["version"],
                                   "manifest_ref": ref, "manifest": manifest, "confirmation_id": None,
                                   "source_files": rule_sources,
                                   "previous_confirmation_id": (old.get("confirmation_id") or old.get("previous_confirmation_id")) if old else None}
        history = state.setdefault("gate_history", {}).setdefault(gate_id, [])
        if old and not any(g["version"] == old["version"] for g in history):
            history.append(copy.deepcopy(old))
        history.append(copy.deepcopy(state["gates"][gate_id]))

    def _confirm(self, state, record, event_id):
        gate = state["gates"].get(record.get("gate_id"))
        need(gate, "unknown confirmation gate")
        cid = record.get("confirmation_id")
        need(isinstance(cid, str) and cid.strip() and cid not in state["confirmations"], "missing/duplicate confirmation_id")
        need(not gate["confirmation_id"], "gate version already confirmed; propose a new manifest version")
        need(record.get("version") == gate["version"], "stale confirmation version")
        need(record.get("manifest_sha256") == gate["manifest_ref"]["sha256"], "confirmation manifest hash mismatch")
        need(record.get("confirmed_by") and record.get("authority_ref"), "actual human identity and authority_ref required")
        decision = record.get("decision")
        need(decision in ("all", "partial", "conditional"), "unknown confirmation decision")
        all_ids = {i["item_id"] for i in gate["manifest"]["items"]}
        approved = record.get("approved_item_ids")
        need(isinstance(approved, list) and len(set(approved)) == len(approved) and set(approved) <= all_ids,
             "approved_item_ids must explicitly enumerate unique manifest items")
        need(decision != "all" or set(approved) == all_ids, "all confirmation must cover every item")
        conditions = record.get("conditions", [])
        need(isinstance(conditions, list), "conditions must be an array")
        need(decision != "conditional" or conditions, "conditional confirmation needs explicit conditions")
        usable = set(approved)
        for condition in conditions:
            need(condition.get("item_id") in approved and condition.get("text"), "invalid condition item/text")
            need(condition.get("kind") in ("restriction", "prerequisite"), "condition kind required")
            need(not condition.get("changes_read_scope") and not condition.get("scope_overrides"), "read scope change must be represented in an exact revised manifest, not free text")
            if condition["kind"] == "prerequisite":
                if condition.get("satisfied") is True:
                    need(condition.get("evidence_ref"), "satisfied prerequisite requires evidence_ref")
                else:
                    usable.discard(condition["item_id"])
        ref = write_once(self.project / "confirmations" / event_id / "record.json", record)
        state["confirmations"][cid] = {"record_ref": ref, "record": record, "usable_item_ids": sorted(usable)}
        gate["confirmation_id"] = cid
        changed_conditions = set()
        previous_id = gate.get("previous_confirmation_id")
        if previous_id:
            previous = state["confirmations"][previous_id]["record"]
            for iid in all_ids:
                old_conditions = [c for c in previous.get("conditions", []) if c["item_id"] == iid]
                new_conditions = [c for c in conditions if c["item_id"] == iid]
                if old_conditions != new_conditions:
                    changed_conditions.add(iid)
        invalid_items = (all_ids - usable) | changed_conditions
        if invalid_items:
            self._invalidate(state, [u["unit_id"] for u in state["effective"].values()
                                     if any(r["gate_id"] == gate["gate_id"] and set(r["item_ids"]) & invalid_items for r in u.get("gate_item_refs", []))],
                             "human confirmation withheld or changed conditions on specific items", event_id)
            for task in state["tasks"].values():
                if task["status"] in ("pending", "returned") and any(r["gate_id"] == gate["gate_id"] and set(r["item_ids"]) & invalid_items for r in task["gate_refs"]):
                    task["status"] = "stale"
        if gate["gate_id"] == "FINAL":
            final_units = []
            for item in gate["manifest"]["items"]:
                if item["item_id"] in usable:
                    unit = state["effective"].get(item["payload"]["unit_id"])
                    need(unit and unit["status"] == "effective" and unit.get("review_status") == "accepted" and unit["result_ref"] == item["payload"]["result_ref"], "FINAL adoption changed before confirmation")
                    final_units.append(unit["unit_id"])
            state["final_human_confirmation"] = {"confirmation_id": cid, "record_ref": ref, "unit_ids": final_units,
                                                   "status": "confirmed", "classification_scope": "only the actual recorded human decision"}

    def _gate_items(self, state, refs, gate_id):
        matches = [r for r in refs if r.get("gate_id") == gate_id]
        need(len(matches) == 1, f"exactly one {gate_id} binding required")
        ref = matches[0]
        gate = state["gates"].get(gate_id)
        need(gate and gate["version"] == ref.get("version"), f"missing/stale {gate_id}")
        cid = gate["confirmation_id"]
        need(cid, f"{gate_id} requires actual human confirmation")
        selected = ref.get("item_ids")
        need(isinstance(selected, list) and selected and len(set(selected)) == len(selected), "gate item_ids required")
        confirmation = state["confirmations"][cid]
        need(set(selected) <= set(confirmation["usable_item_ids"]), f"unconfirmed/unsatisfied {gate_id} items")
        return [i for i in gate["manifest"]["items"] if i["item_id"] in selected], confirmation

    def _g1_sources(self, state, refs, batch_id, files):
        items, confirmation = self._gate_items(state, refs, "G1")
        allowed = {}
        for item in items:
            payload = item["payload"]
            gate_version = next(r["version"] for r in refs if r["gate_id"] == "G1")
            prepared = state.get("preparation", {}).get(f"G1:{gate_version}:{item['item_id']}", {}).get("ready", payload.get("ready"))
            need(prepared is True, f"G1 approved but not prepared: {item['item_id']}")
            need(batch_id in payload.get("batch_ids", []), "G1 batch mapping mismatch")
            for source in payload["source_refs"]:
                allowed[source_key(source)] = source
        for source in files:
            need(source.get("file_id") and source.get("assigned_scope"), "source identity/scope required")
            key = source_key(source)
            need(key in allowed, "actual source path/file_id/scope does not match G1 approved item")
            approved = checked_source(allowed[key])
            need(not source.get("sha256") or source["sha256"] == approved["sha256"], "source sha256 differs from G1")
            need(source.get("version") == approved.get("version"), "source version differs from G1 approved reading version")
            for mapping_key in ("origin_map", "origin_source"):
                need(source.get(mapping_key) == approved.get(mapping_key), f"source {mapping_key} differs from G1 approved provenance")
        return allowed, confirmation

    def _enqueue(self, state, spec, event_id, automatic=False):
        role = spec.get("agent_name")
        need(role in ROLES, "unknown role")
        need(role != "quality_review" or automatic, "quality_review is generated from a checked judge result")
        batch = spec.get("batch_id")
        need(isinstance(batch, str) and batch, "batch_id required")
        task_input = copy.deepcopy(spec.get("input"))
        need(isinstance(task_input, dict), "business input object required")
        need(not any(k in task_input for k in ("gate_refs", "runtime_protocol", "receipt")), "transport fields must stay outside business input")
        task_id, run_id = f"{role}-{event_id}", f"run-{event_id}"
        need(task_id not in state["tasks"], "duplicate task")
        task_input.update(task_id=task_id, run_id=run_id, agent_name=role)
        refs = copy.deepcopy(spec.get("gate_refs", []))
        dependencies = []
        source_refs = []
        basis_refs = []
        if role == "base_rule":
            for source in task_input.get("source_files", []):
                need(source.get("path") and source.get("file_id") and source.get("assigned_scope"), "base_rule source path/file/scope required")
                frozen_source = copy.deepcopy(source)
                frozen_source["sha256"] = digest(frozen_source["path"])
                checked_source(frozen_source)
                source_refs.append(frozen_source)
        if role in EXTRACTORS:
            need(task_input.get("meeting_package_id"), "extraction meeting_package_id required")
            files = task_input.get("files")
            need(isinstance(files, list) and files, "extraction files required, including explicit missing-material scope where appropriate")
            allowed, confirmation = self._g1_sources(state, refs, batch, files)
            source_refs = [allowed[source_key(f)] for f in files]
        if role == "rule_judge":
            extracts = [t for t in state["tasks"].values() if t["batch_id"] == batch and t["agent_name"] in EXTRACTORS and t["status"] == "completed"]
            need(set(t["agent_name"] for t in extracts) == set(EXTRACTORS), "all four validated extraction routes required")
            units = [u for u in state["effective"].values() if u["batch_id"] == batch and u["agent_name"] in EXTRACTORS and u["status"] == "effective"]
            need(units, "no effective extraction scope")
            need({u["agent_name"] for u in units if u["result_ref"]["collection"] == "coverage"} == set(EXTRACTORS), "all four currently effective extraction coverage routes required; historical completed is insufficient")
            need(not any(u["status"] == "stale" for u in state["effective"].values() if u["batch_id"] == batch and u["agent_name"] in EXTRACTORS), "stale extraction units must be resolved before batch judgment")
            dependencies = [u["unit_id"] for u in units]
            task_ids = sorted({u["result_ref"]["task_id"] for u in units})
            task_input["extraction_results"] = [self._result_descriptor(state, tid) for tid in task_ids]
            task_input["effective_results"] = copy.deepcopy(units)
            files = []
            for tid in task_ids:
                for original_source in state["tasks"][tid]["source_refs"]:
                    source = copy.deepcopy(original_source)
                    source["extraction_refs"] = [{"run_id": state["tasks"][tid]["run_id"], "file_id": source["file_id"]}]
                    files.append(source)
            self._g1_sources(state, refs, batch, files)
            g2_items, confirmation = self._gate_items(state, refs, "G2")
            gate = state["gates"]["G2"]
            confirmed_rules = []
            for item in g2_items:
                rule = copy.deepcopy(item["payload"])
                rule["confirmation_status"] = "confirmed"
                rule["confirmation_ref"] = gate["confirmation_id"]
                confirmed_rules.append(rule)
            selected_ids = {i["item_id"] for i in g2_items}
            rules_snapshot = {"protocol_version": PROTOCOL, "gate_id": "G2", "version": gate["version"],
                              "confirmation_ref": confirmation["record_ref"], "manifest_ref": gate["manifest_ref"],
                              "rules": confirmed_rules,
                              "conditions": [c for c in confirmation["record"].get("conditions", []) if c["item_id"] in selected_ids]}
            rules_ref = write_once(self.project / "tasks" / task_id / "confirmed_rules.json", rules_snapshot)
            task_input["rules"] = {**rules_ref, "version": gate["version"],
                                   "confirmation_ref": gate["confirmation_id"]}
            basis_refs.append(rules_ref)
            # Existing full source_files are retained only if they match approved sources.
            if task_input.get("source_files"):
                self._g1_sources(state, refs, batch, task_input["source_files"])
            else:
                task_input["source_files"] = [dict(f, source_key=f"source-{i}") for i, f in enumerate(files)]
            source_refs = list(files)
            for item in g2_items:
                for citation in item["payload"].get("source_refs", []):
                    if citation.get("path") or citation.get("availability") == "not_provided":
                        source = citation
                    else:
                        matches = [s for s in gate.get("source_files", []) if s.get("source_key") == citation.get("source_key") and s.get("file_id") == citation.get("file_id") and s.get("version") == citation.get("version")]
                        need(len(matches) == 1, "G2 citation no longer resolves uniquely")
                        source = matches[0]
                    checked_source(source)
                    source_refs.append(source)
                    if not any(source_key(f) == source_key(source) for f in task_input["source_files"]):
                        task_input["source_files"].append(dict(source, source_key=f"rule-source-{len(task_input['source_files'])}"))
            for key in ("logic", "dictionary", "rule_catalog"):
                if task_input.get(key) and task_input[key].get("path"):
                    p = Path(task_input[key]["path"])
                    need(p.is_absolute() and p.is_file(), f"{key} must use an actual absolute file")
                    frozen = write_once(self.project / "tasks" / task_id / "basis" / (key + p.suffix), p.read_bytes())
                    task_input[key].update(frozen)
                    basis_refs.append(frozen)
                    if key == "dictionary" and task_input[key].get("guide_path"):
                        guide = Path(task_input[key]["guide_path"])
                        need(guide.is_absolute() and guide.is_file(), "dictionary.guide_path must use an actual absolute file")
                        frozen_guide = write_once(self.project / "tasks" / task_id / "basis" / ("dictionary_guide" + guide.suffix), guide.read_bytes())
                        task_input[key]["guide_path"] = frozen_guide["path"]
                        task_input[key]["guide_sha256"] = frozen_guide["sha256"]
                        basis_refs.append(frozen_guide)
        if role == "quality_review":
            dependencies = spec["dependencies"]
            source_refs = spec["source_refs"]
            basis_refs = spec["basis_refs"]
        replaces = spec.get("replaces", {})
        if not replaces and role in (*EXTRACTORS, "rule_judge"):
            need(not any(t["batch_id"] == batch and t["agent_name"] == role and t["status"] in ("pending", "completed", "returned") for t in state["tasks"].values()),
                 "existing role/batch requires explicit local revise")
        for local_id, deps in spec.get("item_dependencies", {}).items():
            need(isinstance(deps, list) and set(deps) <= set(dependencies), f"unknown item dependencies: {local_id}")
        task_dir = self.project / "tasks" / task_id
        task_input["output_path"] = str(task_dir / "role_output.json")
        input_ref = write_once(task_dir / "input.json", task_input)
        prompt_path = self.skill_root / "prompts" / f"{role}.md"
        need(prompt_path.is_file(), f"missing role prompt: {prompt_path}")
        prompt_ref = write_once(task_dir / "role_prompt.md", prompt_path.read_bytes())
        execution_mode = state["project"].get("execution_mode", "codex_external_bridge")
        envelope = {"protocol_version": PROTOCOL, "task_id": task_id, "run_id": run_id, "agent_name": role,
                    "batch_id": batch, "input_ref": input_ref, "prompt_ref": prompt_ref, "gate_refs": refs,
                    "source_refs": source_refs, "dependencies": dependencies,
                    "basis_refs": basis_refs,
                    "runtime": {"mode": execution_mode, "history_inheritance": False,
                                "allowlist_enforcement": "whole_process_appcontainer_required" if execution_mode == "windows_appcontainer" else "contractual_only",
                                "executor_must_actually_spawn": execution_mode == "codex_external_bridge",
                                "executor_must_actually_launch": execution_mode == "windows_appcontainer"},
                    "output_path": task_input["output_path"], "replaces": replaces,
                    "item_dependencies": spec.get("item_dependencies", {}),
                    "review_target_units": spec.get("review_target_units", [])}
        if spec.get("review_partition"):
            envelope["review_partition"] = copy.deepcopy(spec["review_partition"])
        if role == "quality_review":
            envelope["scan_reviews_path"] = str(task_dir / "scan_reviews.json")
        if role == "rule_judge":
            envelope["specific_rule_issues_path"] = str(task_dir / "specific_rule_issues.json")
        envelope["conditions"] = []
        for gate_ref in refs:
            gate = state["gates"].get(gate_ref["gate_id"])
            if gate and gate.get("confirmation_id"):
                record = state["confirmations"][gate["confirmation_id"]]["record"]
                envelope["conditions"].extend({"gate_id": gate_ref["gate_id"], **c} for c in record.get("conditions", []) if c["item_id"] in gate_ref["item_ids"])
        envelope["condition_enforcement"] = "Exact path/hash/scope is enforced; natural-language restrictions require professional execution and review."
        if execution_mode == "windows_appcontainer":
            from sandbox_adapter import compile_contract, SandboxViolation
            try:
                contract = compile_contract(envelope)
            except SandboxViolation as exc:
                raise RuntimeViolation("sandbox contract rejected: " + str(exc)) from exc
            envelope["sandbox_contract_ref"] = write_once(task_dir / "sandbox_contract.json", contract)
        envelope_ref = write_once(task_dir / "task.json", envelope)
        state["tasks"][task_id] = {**envelope, "envelope_ref": envelope_ref, "status": "pending"}
        return task_id

    def _result_descriptor(self, state, task_id):
        task, result = state["tasks"][task_id], state["results"][task_id]
        data = load_json(result["result_ref"]["path"])
        return {"task_id": task_id, "agent_name": task["agent_name"], "run_id": task["run_id"],
                "version": data["schema_version"], **result["result_ref"],
                "meeting_package_id": data.get("meeting_package_id")}

    def _validate_business(self, state, task, data, receipt):
        task_input = load_json(task["input_ref"]["path"])
        need(isinstance(data, dict), "result must be JSON object")
        for key in ("task_id", "run_id", "agent_name"):
            need(data.get(key) == task[key], f"result identity mismatch: {key}")
        need(data.get("status") in ("completed", "partial", "blocked", "failed"), "invalid result status")
        role = task["agent_name"]
        if role in EXTRACTORS:
            errors = validate_extraction(data, task_input)
            need(not errors, "four-route structure validation failed: " + "; ".join(errors))
        else:
            expected = {"read_adjust": "1.0", "base_rule": "1.0.0", "rule_judge": "1.3", "quality_review": "1.0"}[role]
            need(data.get("schema_version") == expected, "business schema version mismatch")
            need(data.get("input_snapshot") == task_input, "input_snapshot must retain exact original business input")
            need(isinstance(data.get("requests"), list), "requests array required")
            if role == "read_adjust":
                for field in ("files", "meeting_packages", "gaps"):
                    need(isinstance(data.get(field), list), f"read_adjust.{field} array required")
            if role == "base_rule":
                for field in ("source_coverage", "rule_candidates", "comparisons"):
                    need(isinstance(data.get(field), list), f"base_rule.{field} array required")
            if role == "rule_judge":
                self._validate_judge(state, task, task_input, data, receipt)
            if role == "quality_review":
                self._validate_review(state, task, task_input, data, receipt)
        return task_input

    def _validate_judge(self, state, task, task_input, data, receipt):
        need(data.get("rules_version") == task_input["rules"]["version"], "judge must use confirmed G2 snapshot version")
        checked_ref(task_input["rules"])
        rules = load_json(task_input["rules"]["path"])["rules"]
        rule_ids = {r["rule_id"] for r in rules}
        sources = {s["source_key"]: s for s in task_input["source_files"]}
        tables = {k: unique_rows(data.get(k), field, f"judge.{k}") for k, field in IDS.items() if k != "records"}
        allowed_records = {(state["effective"][u]["result_ref"]["run_id"], state["effective"][u]["result_ref"]["item_id"])
                           for u in task["dependencies"] if state["effective"][u]["result_ref"]["collection"] == "records"}
        records = {}
        subjects = set()
        for descriptor in task_input["extraction_results"]:
            raw = load_json(descriptor["path"])
            for record in raw["records"]:
                key = (descriptor["run_id"], record["record_id"])
                if key in allowed_records:
                    records[key] = record
                    subjects.add((descriptor["run_id"], record["subject_ref"]))
            # Document contexts with explicit effective coverage remain referable.
            covered = {state["effective"][u]["result_ref"]["item_id"] for u in task["dependencies"]
                       if state["effective"][u]["result_ref"]["collection"] == "coverage" and state["effective"][u]["result_ref"]["run_id"] == descriptor["run_id"]}
            subjects.update((descriptor["run_id"], s["subject_ref"]) for s in raw["subjects"] if s["file_id"] in covered)

        def record_ref(ref, item=False):
            key = (ref.get("run_id"), ref.get("record_id"))
            need(key in records, "judge references a non-effective extraction record")
            if item or "item_index" in ref:
                index = ref.get("item_index")
                need(type(index) is int and 0 <= index < len(records[key]["values"]["items"]), "judge item_index outside effective record")

        def subject_ref(ref):
            need((ref.get("run_id"), ref.get("subject_ref")) in subjects, "judge subject reference is not effective")

        for row in tables["links"].values():
            subject_ref(row.get("left_subject_ref", {})); subject_ref(row.get("right_subject_ref", {}))
            for ref in row.get("evidence_refs", []):
                record_ref(ref, True)
        for row in tables["matters"].values():
            for ref in row.get("subject_refs", []):
                subject_ref(ref)
            need(set(row.get("link_ids", [])) <= set(tables["links"]), "matter link_ids unknown")
        for row in tables["comparisons"].values():
            need(row.get("matter_id") in tables["matters"], "comparison matter_id unknown")
            need(set(row.get("link_ids", [])) <= set(tables["links"]), "comparison link_ids unknown")
            for ref in row.get("input_refs", []):
                record_ref(ref, True)
        for row in tables["decisions"].values():
            need(row.get("result") in ("符合", "初步偏差", "不适用", "证据不足", "规则待确认"), "unknown decision result")
            need(row.get("reason") and isinstance(row.get("source_checks"), list), "decision reasons/source_checks required")
            self._check_source_checks(row["source_checks"], sources)
            rid = row.get("rule_id")
            if row["result"] == "规则待确认":
                issues = receipt.get("specific_rule_issues", {})
                issue = issues.get(row["decision_id"])
                need(isinstance(issue, dict) and all(issue.get(k) for k in ("specific_issue_ref", "reason", "affected_scope")),
                     "rule pending requires specific_issue_ref/reason/affected_scope in receipt.specific_rule_issues, including null/catalog rule ids")
            if row["result"] in ("符合", "初步偏差", "不适用"):
                need(rid in rule_ids, "definite decision must cite an actually confirmed rule")
                confirmed = next(r for r in rules if r["rule_id"] == rid)
                basis = row.get("rule_basis", {})
                need(basis.get("rule_id") == rid and basis.get("version") == confirmed["version"] and basis.get("confirmation_ref") == task_input["rules"]["confirmation_ref"],
                     "definite rule_basis identity/version/confirmation_ref must match G2 snapshot")
                need(any(c.get("read_state") == "verified" and c.get("quote") and c.get("locator") for c in row["source_checks"]),
                     "definite conclusion requires verified original-source checks; missing original is not nonperformance")
            for ref in row.get("record_refs", []) + row.get("counter_record_refs", []):
                record_ref(ref)
            need(row.get("matter_id") in tables["matters"], "decision has unknown matter")
            need(set(row.get("comparison_ids", [])) <= set(tables["comparisons"]), "decision comparison_ids unknown")
        for row in tables["leads"].values():
            need(row.get("matter_id") in tables["matters"], "lead has unknown matter")
            for ref in row.get("record_refs", []):
                record_ref(ref)
            for ref in row.get("item_refs", []):
                record_ref(ref, True)
        for row in tables["coverage"].values():
            need(row.get("matter_id") in tables["matters"], "coverage has unknown matter")
            need(set(row.get("decision_ids", [])) <= set(tables["decisions"]), "coverage decision_ids unknown")
        for row in tables["lead_scan"].values():
            need(row.get("matter_id") in tables["matters"], "scan has unknown matter")
            need(isinstance(row.get("linked_decision_ids"), list), "scan linked_decision_ids required")
            need(isinstance(row.get("lead_ids"), list), "scan lead_ids required")
            for lid in row["lead_ids"]:
                need(lid in tables["leads"] and tables["leads"][lid]["matter_id"] == row["matter_id"], "scan lead reference mismatch")
            for ref in row.get("record_refs", []):
                record_ref(ref)
            for ref in row.get("item_refs", []):
                record_ref(ref, True)
            for did in row["linked_decision_ids"]:
                need(did in tables["decisions"] and tables["decisions"][did]["matter_id"] == row.get("matter_id"), "scan decision reference mismatch")

    def _check_source_checks(self, checks, sources):
        for check in checks:
            source = sources.get(check.get("source_key"))
            need(source and source.get("file_id") == check.get("file_id"), "source_check references unknown source identity")
            need(check.get("version") == source.get("version"), "source_check version mismatch")
            need(check.get("read_state") in ("verified", "not_read", "unreadable"), "invalid source read_state")
            if check["read_state"] == "verified":
                path = source.get("path", source.get("path_or_attachment_id"))
                need(path and Path(path).is_file() and source.get("availability") != "not_provided", "absent source cannot be verified")
                need(check.get("quote") and check.get("locator"), "verified source needs actual quote/locator")

    def _validate_review(self, state, task, task_input, data, receipt):
        need(data.get("rules_version") == task_input["rules"]["version"], "review rules version mismatch")
        need(data.get("review_mode") == task_input["review_mode"], "review scope cannot be reduced without human confirmation")
        need(set(data.get("target_run_ids", [])) == {u["result_ref"]["run_id"] for u in task["review_target_units"]}, "review target runs mismatch")
        expected = {(u["result_ref"]["run_id"], u["result_ref"]["collection"], u["result_ref"]["item_id"])
                    for u in task["review_target_units"] if u["result_ref"]["collection"] in ("decisions", "leads")}
        actual = set()
        reviews = []
        sources = {s["source_key"]: s for s in task_input["source_files"]}
        for collection, source_collection, ref_key, id_key in (("decision_reviews", "decisions", "decision_ref", "decision_id"),
                                                              ("lead_reviews", "leads", "lead_ref", "lead_id")):
            unique_rows(data.get(collection), "review_id", collection)
            for row in data[collection]:
                ref = row.get(ref_key, {})
                key = (ref.get("run_id"), source_collection, ref.get(id_key))
                need(key not in actual, "duplicate item review")
                actual.add(key)
                need(row.get("review_result") in ("accepted", "revise", "limited", "not_reviewed"), "invalid review_result")
                need(row.get("note"), "review note required")
                self._check_source_checks(row.get("source_checks", []), sources)
                if row["review_result"] == "accepted":
                    need(any(c.get("read_state") == "verified" and c.get("quote") for c in row.get("source_checks", [])), "accepted review requires actual source-check record")
                    if collection == "decision_reviews":
                        dims = unique_rows(row.get("dimensions"), "dimension", "review dimensions")
                        need(set(dims) == DIMENSIONS, "all seven review dimensions required")
                        need(all(d.get("state") in ("checked", "not_applicable") and d.get("basis") for d in dims.values()), "accepted review has incomplete/problem dimensions")
                reviews.append(row)
        need(actual == expected, "review must enumerate every assigned decision and lead, including not_reviewed")
        scopes = unique_rows(data.get("scope_coverage"), "scope_id", "scope_coverage")
        need(set(scopes) == {s["scope_id"] for s in task_input["review_scope"]}, "review scan/coverage scope missing")
        for scope in scopes.values():
            need(scope.get("omission_state") in ("checked", "issue", "limited", "not_reviewed") and scope.get("note"), "explicit omission/scan coverage check required")
            self._check_source_checks(scope.get("source_checks", []), sources)
        expected_scans = {(u["result_ref"]["run_id"], u["result_ref"]["item_id"])
                          for u in task["review_target_units"] if u["result_ref"]["collection"] == "lead_scan"}
        scans = receipt.get("scan_reviews", [])
        actual_scans = {(r.get("run_id"), r.get("scan_id")) for r in scans}
        need(actual_scans == expected_scans and len(scans) == len(expected_scans), "receipt.scan_reviews must enumerate each assigned lead_scan exactly once")
        need(all(r.get("review_result") in ("accepted", "revise", "limited", "not_reviewed") and r.get("note") for r in scans), "scan review result/note required")
        unique_rows(data.get("findings"), "finding_id", "findings")
        if data.get("review_disposition") == "pass":
            need(all(r["review_result"] == "accepted" for r in reviews + scans) and all(s["omission_state"] == "checked" for s in scopes.values()), "pass cannot include unreviewed/limited/revised scope")

    def _submit(self, state, payload, event_id):
        tid = payload.get("task_id")
        task = state["tasks"].get(tid)
        need(task and task["status"] in ("pending", "returned"), "task missing, stale, or already submitted")
        result_ref = checked_ref(payload["result_ref"])
        receipt = payload["receipt"]
        for key in ("task_id", "run_id", "agent_name"):
            need(receipt.get(key) == task[key], f"host receipt identity mismatch: {key}")
        need(receipt.get("input_sha256") == task["input_ref"]["sha256"], "receipt input hash mismatch")
        need(receipt.get("result_sha256") == result_ref["sha256"], "receipt result hash mismatch")
        need(receipt.get("history_inheritance") is False and receipt.get("executed") is True,
             "receipt must record actual execution in a fresh context")
        if task["runtime"]["mode"] == "windows_appcontainer":
            from sandbox_adapter import validate_sandbox_receipt, SandboxViolation
            try:
                validate_sandbox_receipt(self.project, task, receipt, result_ref)
            except (SandboxViolation, OSError, KeyError, ValueError) as exc:
                raise RuntimeViolation("sandbox receipt rejected: " + str(exc)) from exc
        else:
            need(receipt.get("executor") == "codex-collaboration" and receipt.get("context_id"), "actual Codex context receipt required")
        need(receipt.get("context_id"), "actual independent model context required")
        need(not any(r["context_id"] == receipt["context_id"] for r in state["results"].values()), "context_id reused across independent roles/tasks")
        for ref in task["source_refs"]:
            checked_source(ref)
        for unit_id in task["dependencies"]:
            need(state["effective"].get(unit_id, {}).get("status") == "effective", "task depends on a stale/replaced unit")
            expected = next((u for u in load_json(task["input_ref"]["path"]).get("effective_results", []) if u["unit_id"] == unit_id), None)
            if expected:
                need(expected["result_ref"] == state["effective"][unit_id]["result_ref"], "task dependency version changed")
        data = load_json(result_ref["path"])
        archived_result = write_once(self.project / "submissions" / event_id / "original-result.json", Path(result_ref["path"]).read_bytes())
        archived_receipt = write_once(self.project / "submissions" / event_id / "host-receipt.json", receipt)
        try:
            task_input = self._validate_business(state, task, data, receipt)
        except RuntimeViolation as exc:
            # Business validation returns a local repair task without losing raw evidence.
            task["status"] = "returned"
            state["returns"].append({"task_id": tid, "event_id": event_id, "kind": "structure_return",
                                     "reason": str(exc), "result_ref": archived_result, "receipt_ref": archived_receipt,
                                     "affected_scope": task["input_ref"], "business_review_performed": False})
            return
        state["results"][tid] = {"result_ref": archived_result, "receipt_ref": archived_receipt,
                                  "context_id": receipt["context_id"], "business_status": data["status"]}
        task["status"] = "completed" if data["status"] in ("completed", "partial") else "blocked"
        task["business_status"] = data["status"]
        task["structural_validation"] = "passed"
        task["business_review_performed_by_runtime"] = False
        if task["status"] == "blocked":
            return
        if task["agent_name"] in (*EXTRACTORS, "rule_judge"):
            self._adopt(state, task, data, archived_result, event_id)
        if task["agent_name"] == "rule_judge":
            self._auto_review(state, task, task_input, event_id)
        elif task["agent_name"] == "quality_review":
            self._apply_review(state, task, data, archived_result, receipt)

    def _adopt(self, state, task, data, result_ref, event_id):
        role = task["agent_name"]
        fields = {"records": "record_id", "coverage": "file_id"} if role in EXTRACTORS else {k: v for k, v in IDS.items() if k != "records"}
        available = {f"{collection}:{row[field]}": (collection, row[field]) for collection, field in fields.items() for row in data[collection]}
        replaces = task["replaces"]
        if replaces:
            need(set(available) == set(replaces), "revision must return exactly explicitly mapped local items; no silent whole-file replacement")
            self._invalidate(state, list(replaces.values()), "explicit local revision", event_id)
        for local_id, (collection, item_id) in available.items():
            unit_id = replaces.get(local_id, f"{task['batch_id']}:{role}:{local_id}")
            old = state["effective"].get(unit_id)
            need(not old or local_id in replaces, "effective unit collision; explicit revision required")
            deps = list(task["item_dependencies"].get(local_id, task["dependencies"]))
            if role == "rule_judge":
                row = next(r for r in data[collection] if r[fields[collection]] == item_id)
                internal = []
                if row.get("matter_id") and collection != "matters":
                    internal.append("matters:" + row["matter_id"])
                internal.extend("links:" + value for value in row.get("link_ids", []))
                internal.extend("comparisons:" + value for value in row.get("comparison_ids", []))
                internal.extend("decisions:" + value for value in row.get("decision_ids", []) + row.get("linked_decision_ids", []))
                internal.extend("leads:" + value for value in row.get("lead_ids", []))
                # Missing comparison_ids cannot preserve a pass when an intermediate
                # comparison for the same matter changes. This is conservative.
                if collection in ("decisions", "leads", "lead_scan", "coverage"):
                    internal.extend("comparisons:" + r["comparison_id"] for r in data["comparisons"] if r.get("matter_id") == row.get("matter_id"))
                for internal_id in internal:
                    uid = replaces.get(internal_id, f"{task['batch_id']}:{role}:{internal_id}")
                    need(internal_id in available or uid in state["effective"], "internal dependency cannot be resolved")
                    if uid != unit_id and uid not in deps:
                        deps.append(uid)
            unit_gate_refs = copy.deepcopy(task["gate_refs"])
            if role == "rule_judge":
                for gate_ref in list(unit_gate_refs):
                    if gate_ref["gate_id"] != "G2":
                        continue
                    # Fact links/matters and evidence leads carry their upstream
                    # dependencies. They do not acquire every formal rule merely
                    # because the judge received a multi-rule snapshot.
                    if collection in ("matters", "links", "leads", "lead_scan"):
                        unit_gate_refs.remove(gate_ref)
                    elif collection in ("decisions", "coverage"):
                        gate = next((g for g in state.get("gate_history", {}).get("G2", []) if g["version"] == gate_ref["version"]), state["gates"].get("G2"))
                        matching = [i["item_id"] for i in gate["manifest"]["items"] if i["item_id"] in gate_ref["item_ids"] and i["payload"].get("rule_id") == row.get("rule_id")]
                        if matching:
                            gate_ref["item_ids"] = matching
                    # Comparisons without an explicit rule identity conservatively
                    # retain selected G2 dependencies; professional review must
                    # resolve ambiguity before claiming they are unaffected.
            unit = {"unit_id": unit_id, "batch_id": task["batch_id"], "agent_name": role,
                    "status": "effective", "review_status": "pending" if role == "rule_judge" else "not_applicable",
                    "result_ref": {**result_ref, "task_id": task["task_id"], "run_id": task["run_id"],
                                   "collection": collection, "item_id": item_id},
                    "dependencies": deps, "gate_ids": [r["gate_id"] for r in unit_gate_refs],
                    "gate_item_refs": unit_gate_refs,
                    "review_refs": [], "replaced_refs": ([old["result_ref"]] + old.get("replaced_refs", [])) if old else []}
            state["effective"][unit_id] = unit

    def _invalidate(self, state, unit_ids, reason, event_id):
        affected = set(unit_ids)
        while True:
            more = {u["unit_id"] for u in state["effective"].values() if set(u["dependencies"]) & affected}
            if more <= affected:
                break
            affected |= more
        for uid in affected:
            if uid in state["effective"]:
                state["effective"][uid]["status"] = "stale"
                if state["effective"][uid]["review_status"] != "not_applicable":
                    state["effective"][uid]["review_status"] = "stale"
        carry_forward = []
        for task in list(state["tasks"].values()):
            if task["status"] in ("pending", "returned") and set(task["dependencies"]) & affected:
                task["status"] = "stale"
                if task["agent_name"] == "quality_review":
                    remaining = [copy.deepcopy(state["effective"][u["unit_id"]]) for u in task["review_target_units"]
                                 if state["effective"][u["unit_id"]]["status"] == "effective"
                                 and state["effective"][u["unit_id"]]["result_ref"] == u["result_ref"]]
                    if remaining:
                        carry_forward.append((task, remaining))
        state["invalidation_log"].append({"event_id": event_id, "affected_unit_ids": sorted(affected), "reason": reason})
        final = state.get("final_human_confirmation")
        if final and set(final["unit_ids"]) & affected:
            final["status"] = "stale"
        # Status previews may mark drift but must not create uncheckpointed tasks.
        if event_id != "status-live-source-check":
            for task, remaining in carry_forward:
                self._requeue_unaffected_review(state, task, remaining, affected, reason, event_id)

    def _requeue_unaffected_review(self, state, old, targets, affected, reason, event_id):
        """Continue every unaffected pending item; this is a partition, not sampling."""
        task_input = load_json(old["input_ref"]["path"])
        task_input["effective_results"] = targets
        task_input["invalidation_log"] = copy.deepcopy(state["invalidation_log"])
        scopes = []
        for scope in task_input["review_scope"]:
            same_run = [u for u in targets if u["result_ref"]["run_id"] == scope["judge_run_id"]]
            if not same_run:
                continue
            scope["decision_ids"] = [u["result_ref"]["item_id"] for u in same_run if u["result_ref"]["collection"] == "decisions"]
            scope["lead_ids"] = [u["result_ref"]["item_id"] for u in same_run if u["result_ref"]["collection"] == "leads"]
            scopes.append(scope)
        task_input["review_scope"] = scopes
        gate_index = {}
        for unit in targets:
            for ref in unit.get("gate_item_refs", []):
                key = (ref["gate_id"], ref["version"])
                gate_index.setdefault(key, set()).update(ref["item_ids"])
        gate_refs = [{"gate_id": gid, "version": version, "item_ids": sorted(ids)} for (gid, version), ids in gate_index.items()]
        partition = {"original_review_task_id": old["task_id"], "original_mode": task_input["review_mode"],
                     "original_target_unit_ids": [u["unit_id"] for u in old["review_target_units"]],
                     "carried_forward_unit_ids": [u["unit_id"] for u in targets],
                     "invalidated_unit_ids": sorted(set(old["dependencies"]) & affected),
                     "reason": reason, "scope_change": "all unaffected pending items retained; invalidated items require correction and separate review"}
        suffix = hashlib.sha256(old["task_id"].encode()).hexdigest()[:12]
        self._enqueue(state, {"agent_name": "quality_review", "batch_id": old["batch_id"], "input": task_input,
                              "gate_refs": gate_refs, "dependencies": [u["unit_id"] for u in targets],
                              "source_refs": old["source_refs"], "basis_refs": old["basis_refs"],
                              "review_target_units": targets, "review_partition": partition},
                      event_id + "-carry-" + suffix, automatic=True)

    def _auto_review(self, state, judge, judge_input, event_id):
        targets = [copy.deepcopy(u) for u in state["effective"].values() if u["result_ref"]["task_id"] == judge["task_id"]]
        source_files = []
        for source in judge_input.get("source_files", []):
            source = copy.deepcopy(source)
            source["path_or_attachment_id"] = source.pop("path")
            source["allowed_scope"] = source.pop("assigned_scope")
            source["judge_refs"] = [{"run_id": judge["run_id"], "source_key": source["source_key"]}]
            source.setdefault("origin_map", None)
            source.setdefault("extraction_refs", [])
            source.setdefault("document_type", None)
            source_files.append(source)
        def review_ref(ref):
            ref = copy.deepcopy(ref)
            ref["path_or_attachment_id"] = ref.pop("path")
            return ref
        review_rules = review_ref(judge_input["rules"])
        review_rules["confirmation_status"] = "confirmed"
        review_rules["applicable_entity_period"] = {"entity": judge_input.get("entity"), "period": judge_input.get("period")}
        review_input = {"entity": judge_input.get("entity"), "period": judge_input.get("period"),
                        "meeting_package_id": judge_input.get("meeting_package_id"),
                        "objective": "独立核验本批全部判定、线索、扫描覆盖及采用边界；最终认定由评价人员确认。",
                        "rules": review_rules, "review_mode": "full", "sample_basis": None,
                        "judge_results": [review_ref(self._result_descriptor(state, judge["task_id"]))],
                        "extract_results": [review_ref(r) for r in judge_input["extraction_results"]],
                        "allow_structure_evidence_only": False,
                        "context_declaration": {"fresh_context": True, "judge_internal_analysis_excluded": True,
                                                "expected_conclusions_excluded": True},
                        "source_files": source_files, "effective_results": targets,
                        "review_scope": [{"scope_id": f"scope-{judge['run_id']}", "assigned_scope": judge_input.get("scope", judge["batch_id"]),
                                          "judge_run_id": judge["run_id"], "decision_ids": "all", "lead_ids": "all"}],
                        "invalidation_log": copy.deepcopy(state["invalidation_log"])}
        for key in ("logic", "dictionary", "rule_catalog", "lead_scope"):
            if key in judge_input:
                review_input[key] = copy.deepcopy(judge_input[key])
        return self._enqueue(state, {"agent_name": "quality_review", "batch_id": judge["batch_id"],
                              "input": review_input, "gate_refs": judge["gate_refs"],
                              "dependencies": [u["unit_id"] for u in targets], "source_refs": judge["source_refs"],
                              "basis_refs": judge["basis_refs"],
                              "review_target_units": targets}, event_id + "-review", automatic=True)

    def _apply_review(self, state, task, data, result_ref, receipt):
        by_ref = {(u["result_ref"]["run_id"], u["result_ref"]["collection"], u["result_ref"]["item_id"]): u["unit_id"] for u in task["review_target_units"]}
        mapping = {}
        for collection, ref_name, target_collection, field in (("decision_reviews", "decision_ref", "decisions", "decision_id"),
                                                               ("lead_reviews", "lead_ref", "leads", "lead_id")):
            for row in data[collection]:
                r = row[ref_name]
                mapping[by_ref[(r["run_id"], target_collection, r[field])]] = row["review_result"]
        for row in receipt.get("scan_reviews", []):
            mapping[by_ref[(row["run_id"], "lead_scan", row["scan_id"])]] = row["review_result"]
        omission = [s["omission_state"] for s in data["scope_coverage"]]
        for target in task["review_target_units"]:
            unit = state["effective"][target["unit_id"]]
            review_status = mapping.get(unit["unit_id"])
            if review_status is None:
                review_status = "accepted" if all(x == "checked" for x in omission) else "limited"
            unit["review_status"] = review_status
            unit["review_refs"].append({**result_ref, "run_id": task["run_id"], "task_id": task["task_id"]})
            if review_status == "revise":
                state["returns"].append({"kind": "business_return", "unit_id": unit["unit_id"],
                                         "review_ref": result_ref, "findings": data["findings"],
                                         "requires_fresh_independent_review": True})

    def _revise(self, state, request, event_id):
        need(request.get("reason") and request.get("professional_basis_ref"), "local revision needs specific reason and professional basis reference")
        checked_ref(request["professional_basis_ref"])
        spec = copy.deepcopy(request["spec"])
        replaces = spec.get("replaces")
        need(isinstance(replaces, dict) and replaces and len(set(replaces.values())) == len(replaces), "revision requires explicit new collection:id -> old unit_id mapping")
        for uid in replaces.values():
            unit = state["effective"].get(uid)
            need(unit and unit["agent_name"] == spec.get("agent_name") and unit["batch_id"] == spec.get("batch_id"), "revision unit role/batch mismatch")
        # Register invalidation as soon as a professional correction is requested.
        self._invalidate(state, list(replaces.values()), request["reason"], event_id)
        self._enqueue(state, spec, event_id)

    def _scope_review(self, state, request, event_id):
        old = state["tasks"].get(request.get("task_id"))
        need(old and old["agent_name"] == "quality_review" and old["status"] == "pending", "pending review task required")
        gate_id = f"REVIEW:{old['task_id']}"
        items, confirmation = self._gate_items(state, request.get("gate_refs", []), gate_id)
        need(len(items) == 1, "review scope needs one concrete approved plan")
        plan = items[0]["payload"]
        selected = plan.get("unit_ids")
        target_map = {u["unit_id"]: u for u in old["review_target_units"]}
        need(isinstance(selected, list) and selected and set(selected) <= set(target_map), "review sample units outside population")
        need(plan.get("selection_basis") and plan.get("limitations"), "review reduction needs selection basis and impact limitations")
        task_input = load_json(old["input_ref"]["path"])
        task_input["review_mode"] = "sample"
        task_input["sample_basis"] = {**plan, "confirmation_ref": confirmation["record_ref"]}
        targets = [target_map[uid] for uid in selected]
        for scope in task_input["review_scope"]:
            scope["decision_ids"] = [u["result_ref"]["item_id"] for u in targets if u["result_ref"]["collection"] == "decisions"]
            scope["lead_ids"] = [u["result_ref"]["item_id"] for u in targets if u["result_ref"]["collection"] == "leads"]
        task_input["effective_results"] = targets
        old["status"] = "superseded_scope"
        self._enqueue(state, {"agent_name": "quality_review", "batch_id": old["batch_id"], "input": task_input,
                              "gate_refs": old["gate_refs"] + request["gate_refs"], "dependencies": selected,
                              "source_refs": old["source_refs"], "basis_refs": old["basis_refs"],
                              "review_target_units": targets}, event_id, automatic=True)


def doctor():
    packages = {}
    for package in ("langgraph", "langgraph-checkpoint-sqlite", "langchain-openai"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {"ok": bool(packages["langgraph"] and packages["langgraph-checkpoint-sqlite"]),
            "protocol_version": PROTOCOL, "packages": packages,
            "default_executor": "windows_appcontainer", "api_key_required": False,
            "native_codex_invocation_from_python": False,
            "sandbox_backend": "builtin-windows-appcontainer", "backend_installation_required": False,
            "sandbox_adapter_available": (Path(__file__).with_name("sandbox_executor.py").is_file() and os.name == "nt"),
            "sandbox_verified_by_doctor": False,
            "verification_scope": "control flow and structural validation; no business accuracy certification"}
