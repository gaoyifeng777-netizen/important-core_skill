"""Trusted host staging and receipt checks for whole-process role sandboxes.

This module does not claim that a native collaboration context is sandboxed.
The Windows executor is loaded only by the explicit execution command.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


class SandboxViolation(ValueError):
    pass


def require(value, message):
    if not value:
        raise SandboxViolation(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(path):
    return os.path.normcase(str(Path(path).resolve()))


def no_reparse(path):
    # Inspect the submitted spelling before resolve follows a junction.
    for part in [Path(path), *Path(path).parents]:
        if part.exists() or part.is_symlink():
            require(not part.is_symlink() and not (getattr(part.lstat(), "st_file_attributes", 0) & 0x400),
                    f"reparse directory/file rejected: {part}")


def frozen(ref):
    require(isinstance(ref, dict) and ref.get("path") and ref.get("sha256"), "file reference needs path/hash")
    p = Path(ref["path"])
    require(p.is_absolute() and p.is_file(), f"missing assigned file: {p}")
    no_reparse(p)
    require(sha(p) == ref["sha256"], f"assigned file hash changed: {p}")
    return ref


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"path": str(path.resolve()), "sha256": sha(path)}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def compile_contract(task):
    """Compile permission from explicit role contracts, never arbitrary input paths."""
    for key in ("task_id", "run_id", "agent_name"):
        require(task.get(key), f"missing task identity: {key}")
    frozen(task["input_ref"]); frozen(task["prompt_ref"])
    inp = read_json(task["input_ref"]["path"])
    rows, roots = {}, []

    def add(ref):
        if ref.get("availability") == "not_provided":
            require(ref.get("path") is None, "missing material cannot authorize a path")
            return
        frozen(ref)
        scope = ref.get("assigned_scope")
        if scope is not None:
            require(isinstance(scope, str) and scope.strip().lower() in ("all", "whole_file", "full", "全文", "全部", "整份"),
                    "non-whole-file assigned_scope requires a physically separated reading file before sandbox execution")
        key = norm(ref["path"])
        require(key not in rows or rows[key]["sha256"] == ref["sha256"], "conflicting source hashes")
        rows[key] = copy.deepcopy(ref)

    for ref in task.get("source_refs", []) + task.get("basis_refs", []):
        add(ref)
    if task["agent_name"] == "rule_judge":
        for ref in inp.get("extraction_results", []):
            add(ref)
    if task["agent_name"] == "quality_review":
        for key in ("judge_results", "extract_results"):
            for ref in inp.get(key, []):
                ref = copy.deepcopy(ref)
                if "path_or_attachment_id" in ref:
                    ref["path"] = ref.pop("path_or_attachment_id")
                add(ref)
        for key in ("rules", "logic", "dictionary", "rule_catalog"):
            if isinstance(inp.get(key), dict):
                ref = copy.deepcopy(inp[key])
                if "path_or_attachment_id" in ref:
                    ref["path"] = ref.pop("path_or_attachment_id")
                if ref.get("path"):
                    add(ref)
    if task["agent_name"] == "read_adjust":
        for value in inp.get("path", []):
            no_reparse(value)
            root = Path(value).resolve(strict=True)
            require(root.is_dir() and not root.is_symlink(), "read_adjust requires an actual authorized directory")
            roots.append(str(root))
            excluded = [Path(inp[k]).resolve() for k in ("output_path", "derived_output_dir") if inp.get(k)]
            for p in root.rglob("*"):
                no_reparse(p)
                if p.is_file() and not any(p == e or e in p.parents for e in excluded):
                    add({"path": str(p), "sha256": sha(p), "file_id": None, "assigned_scope": "all"})
        for row in inp.get("expected_items", []):
            ref = row.get("source_ref")
            if ref and ref.get("path"):
                # The collection request itself must already be host-registered.
                require(norm(ref["path"]) in rows, "expected-item source is unregistered; register source_refs explicitly")

    registered = set(rows) | {norm(p) for p in roots}
    outbound = {norm(task["output_path"])}
    for key in ("derived_output_dir",):
        if inp.get(key):
            outbound.add(norm(inp[key]))

    def check_paths(value, parent_key=""):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("path", "guide_path", "path_or_attachment_id") and isinstance(child, str) and Path(child).is_absolute():
                    require(norm(child) in registered or norm(child) in outbound,
                            f"unregistered executable input path: {child}")
                # Origin locators describe evidence; they never grant access.
                if key not in ("origin_map", "origin_source"):
                    check_paths(child, key)
        elif isinstance(value, list):
            for child in value:
                check_paths(child, parent_key)
    check_paths(inp)
    return {"version": "1.0", **{k: task[k] for k in ("task_id", "run_id", "agent_name")},
            "input_sha256": task["input_ref"]["sha256"], "prompt_sha256": task["prompt_ref"]["sha256"],
            "files": list(rows.values()), "authorized_directory_roots": roots,
            "enforcement": "whole-process-windows-appcontainer", "failure_fallback": "none"}


def project_values(value, mapping):
    if isinstance(value, dict):
        return {k: copy.deepcopy(v) if k in ("origin_map", "origin_source") else project_values(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [project_values(v, mapping) for v in value]
    if isinstance(value, str):
        if value in mapping:
            return mapping[value]
        if Path(value).is_absolute():
            matches = [(a, b) for a, b in mapping.items() if norm(value).startswith(norm(a).rstrip("\\/") + os.sep)]
            if matches:
                a, b = max(matches, key=lambda pair: len(pair[0]))
                return str(Path(b) / Path(value).relative_to(Path(a)))
    return value


def stage_task(task, attempt_root, *, role_root=None):
    contract = compile_contract(task)
    root = Path(attempt_root).resolve()
    require(not root.exists(), "attempt path must be fresh")
    role = Path(role_root).resolve() if role_root is not None else root / "role"
    require(not role.exists(), "role workspace must be fresh")
    input_dir, output_dir, host_dir = role / "input", role / "output", root / "host"
    input_dir.mkdir(parents=True); output_dir.mkdir(); host_dir.mkdir(parents=True)
    (root / ".sanzhong-appcontainer-stage").write_text("Trusted host owns this newly staged execution tree.\n", encoding="utf-8")
    (role / ".sanzhong-appcontainer-stage").write_text("Fresh private role workspace.\n", encoding="utf-8")
    mapping, copied = {}, []
    for idx, original_root in enumerate(contract["authorized_directory_roots"]):
        target_root = input_dir / "materials" / f"directory-{idx}"
        target_root.mkdir(parents=True)
        mapping[original_root] = str(target_root)
    for idx, ref in enumerate(contract["files"]):
        source = Path(ref["path"]).resolve()
        matching = [Path(p) for p in contract["authorized_directory_roots"] if Path(p) in source.parents]
        if matching:
            original_root = max(matching, key=lambda p: len(str(p)))
            root_index = contract["authorized_directory_roots"].index(str(original_root))
            target = input_dir / "materials" / f"directory-{root_index}" / source.relative_to(original_root)
            mapping[str(original_root)] = str(input_dir / "materials" / f"directory-{root_index}")
        else:
            target = input_dir / "materials" / f"{idx:04d}" / source.name
        if len(str(target)) > 220:
            # Preserve the source locator in the host map, while keeping the
            # physical reader path short for Office/PDF native dependencies.
            short_parent = input_dir / "materials" / f"directory-{root_index}" if matching else input_dir / "materials"
            target = short_parent / f"material-{idx:04d}{source.suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        require(sha(target) == ref["sha256"], "copied material hash mismatch")
        mapping[str(source)] = str(target)
        if ref["path"] != str(source):
            mapping[ref["path"]] = str(target)
        copied.append({"original_path": ref["path"], "staged_path": str(target), "sha256": ref["sha256"],
                       "provenance": {"kind": "agent_report" if ref.get("agent_name") else "source_quote",
                                      "speaker_id": (f"worker:{ref['agent_name']}:{ref.get('run_id')}" if ref.get("agent_name")
                                                     else f"source:{ref.get('file_id') or idx}"),
                                      "speaker_role": "worker" if ref.get("agent_name") else "source",
                                      "trusted_user_authorization": False}})
    original_input = read_json(task["input_ref"]["path"])
    mapping[task["output_path"]] = str(output_dir / "role_output.json")
    if original_input.get("derived_output_dir"):
        mapping[original_input["derived_output_dir"]] = str(output_dir / "derived")
    staged_input = project_values(original_input, mapping)
    staged_ref = write_json(input_dir / "task_input.json", staged_input)
    shutil.copyfile(task["prompt_ref"]["path"], input_dir / "role_prompt.md")
    frozen_map = {"contract": contract, "path_map": mapping, "copied_files": copied,
                  "staged_input_ref": staged_ref, "original_input_ref": task["input_ref"]}
    map_ref = write_json(host_dir / "stage_map.json", frozen_map)
    return {"root": str(root), "role_root": str(role), "input_dir": str(input_dir), "output_dir": str(output_dir), "host_dir": str(host_dir),
            "contract": contract, "original_input": original_input, "staged_input": staged_input,
            "path_map": mapping, "map_ref": map_ref, "copied_files": copied}


def validate_sandbox_receipt(project, task, receipt, result_ref):
    require(receipt.get("executor") == "appcontainer-python-agent", "sandbox executor receipt required")
    attempt_id = receipt.get("attempt_id")
    require(isinstance(attempt_id, str) and attempt_id and all(c in "0123456789abcdef" for c in attempt_id), "trusted sandbox attempt required")
    attempt_root = Path(project).resolve() / "sandbox_runs" / task["task_id"] / attempt_id
    saved = attempt_root / "host" / "execution_receipt.json"
    require(saved.is_file(), "host-registered sandbox attempt is missing")
    require(read_json(saved) == receipt, "receipt differs from trusted host attempt")
    proof = receipt.get("sandbox", {})
    require(proof.get("backend") == "windows-appcontainer" and proof.get("token", {}).get("is_appcontainer") == 1,
            "actual AppContainer token proof required")
    require(proof.get("sid") == proof.get("token", {}).get("appcontainer_sid"), "sandbox token SID mismatch")
    require(proof.get("preflight_passed") is True and proof.get("exit_code") == 0, "sandbox execution/preflight did not pass")
    require(receipt.get("history_inheritance") is False and receipt.get("executed") is True, "fresh actual model execution required")
    for key in ("task_id", "run_id", "agent_name"):
        require(receipt.get(key) == task[key], "sandbox attempt task identity mismatch")
    require(receipt.get("input_sha256") == task["input_ref"]["sha256"], "sandbox input hash mismatch")
    expected_result = attempt_root / "host" / "normalized_result.json"
    require(norm(result_ref["path"]) == norm(expected_result), "sandbox result must come from the adopted attempt output")
    require(sha(expected_result) == result_ref["sha256"] == receipt.get("result_sha256"), "sandbox result hash mismatch")
    frozen(proof["audit_ref"])
    audit = read_json(proof["audit_ref"]["path"])
    require(audit["task_id"] == task["task_id"] and audit["attempt_id"] == attempt_id, "sandbox audit task mismatch")
    require(audit["model_process"]["token"] == proof["token"], "sandbox audit token mismatch")
    frozen(audit["stage_map_ref"])
    require(read_json(audit["stage_map_ref"]["path"])["contract"]["input_sha256"] == task["input_ref"]["sha256"], "frozen sandbox contract mismatch")
    require(audit.get("preflight", {}).get("passed") is True, "sandbox boundary preflight missing")
    require(audit.get("host_operations") == ["remote_model_inference"] and audit.get("role_network") == "disabled",
            "host must not expose filesystem/command/network tools to the role")
    require(audit.get("inference_verification") == "authenticated_remote_model" and audit.get("inference_requests", 0) > 0,
            "scripted fixture inference cannot be adopted as actual model execution")
    cleanup = read_json(attempt_root / "host" / "cleanup.json")
    require(cleanup.get("profile_deleted") is True and cleanup.get("credentials_copied") is False and cleanup.get("proxy_exception_added") is False,
            "sandbox lifecycle cleanup missing or credentials exposed")
    return receipt
