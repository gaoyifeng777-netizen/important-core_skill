"""CLI for the persistent three-major-one-large review control plane."""
import argparse
import json
from pathlib import Path
import sys

from langgraph_runtime import Runtime, RuntimeViolation, digest, doctor, load_json


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    for name in ("init", "status", "enqueue", "propose-gate", "confirm", "submit", "revise", "scope-review", "mark-ready", "close-partial", "resume", "execute", "execute-batch"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        if name == "init":
            p.add_argument("--config", required=True)
        elif name == "status":
            p.add_argument("--full", action="store_true")
        elif name in ("enqueue", "propose-gate", "confirm", "revise", "scope-review", "mark-ready"):
            p.add_argument({"enqueue": "--spec", "propose-gate": "--manifest", "confirm": "--record"}.get(name, "--request"), required=True)
        elif name == "submit":
            p.add_argument("--task", required=True)
            p.add_argument("--result", required=True)
            p.add_argument("--receipt", required=True)
        elif name in ("execute", "execute-batch"):
            p.add_argument("--task", required=True, nargs="+" if name == "execute-batch" else None)
            p.add_argument("--timeout", type=int, default=600)
            p.add_argument("--model")
            if name == "execute-batch":
                p.add_argument("--max-workers", type=int, default=4)
        elif name == "close-partial":
            p.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        else:
            runtime = Runtime(args.project)
            if args.command == "init":
                result = runtime.init(load_json(args.config))
            elif args.command == "status":
                result = runtime.status(args.full)
            elif args.command in ("execute", "execute-batch"):
                from sandbox_executor import execute_task
                import concurrent.futures
                task_ids = args.task if isinstance(args.task, list) else [args.task]
                workers = args.max_workers if args.command == "execute-batch" else 1
                if workers < 1 or workers > 4 or len(task_ids) != len(set(task_ids)):
                    raise RuntimeViolation("sandbox batch requires unique tasks and 1..4 workers")
                executions = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(execute_task, args.project, tid, model=args.model, timeout=args.timeout): tid for tid in task_ids}
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            outcome = future.result()
                        except Exception as exc:
                            outcome = {"ok": False, "task_id": futures[future], "error": str(exc), "fallback": None}
                        executions.append(outcome)
                # Graph adoption has a single writer; only role execution is parallel.
                for outcome in executions:
                    if outcome.get("ok"):
                        receipt = load_json(outcome["receipt_ref"]["path"])
                        runtime.event("submit", {"task_id": receipt["task_id"], "result_ref": outcome["result_ref"], "receipt": receipt})
                        adopted = runtime.status(True)["tasks"][receipt["task_id"]]
                        outcome["task_status"] = adopted["status"]
                        outcome["business_status"] = adopted.get("business_status")
                        outcome["handoff_passed"] = adopted["status"] == "completed"
                result = {"ok": all(x.get("ok") and x.get("handoff_passed") for x in executions), "executions": executions,
                          "fallback": None, "status": runtime.status()}
            elif args.command == "submit":
                p = Path(args.result).resolve()
                result = runtime.event("submit", {"task_id": args.task, "result_ref": {"path": str(p), "sha256": digest(p)}, "receipt": load_json(args.receipt)})
            elif args.command == "close-partial":
                result = runtime.event("close_partial", {"reason": args.reason})
            elif args.command == "resume":
                result = runtime.event("resume", {})
            else:
                field = {"enqueue": "spec", "propose-gate": "manifest", "confirm": "record", "revise": "request", "scope-review": "request", "mark-ready": "request"}[args.command]
                result = runtime.event(args.command.replace("-", "_"), load_json(getattr(args, field)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except (RuntimeViolation, OSError, ValueError, ImportError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
