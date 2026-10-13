"""Executed inside the role sandbox; tests actual opens and output access."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys


def probe(config):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    rows = []
    for value in config["allowed"]:
        path = Path(value["path"])
        try:
            data = path.read_bytes()
            rows.append({"path": str(path), "kind": "allowed", "passed": hashlib.sha256(data).hexdigest() == value["sha256"], "observed": "read_success"})
        except OSError as exc:
            rows.append({"path": str(path), "kind": "allowed", "passed": False, "error": type(exc).__name__, "errno": exc.errno})
    for path in config["denied"]:
        handle = kernel.CreateFileW(path, 0x80000000, 3, None, 3, 0x80, None)
        error = ctypes.get_last_error()
        if handle == ctypes.c_void_p(-1).value:
            rows.append({"path": path, "kind": "denied", "passed": error == 5, "winerror": error})
        else:
            kernel.CloseHandle(handle)
            rows.append({"path": path, "kind": "denied", "passed": False, "observed": "read_success"})
    immutable = config["allowed"][0]["path"]
    handle = kernel.CreateFileW(immutable, 0x40000000, 3, None, 3, 0x80, None)
    error = ctypes.get_last_error()
    if handle == ctypes.c_void_p(-1).value:
        rows.append({"path": immutable, "kind": "input_write_denied", "passed": error == 5, "winerror": error})
    else:
        kernel.CloseHandle(handle)
        rows.append({"path": immutable, "kind": "input_write_denied", "passed": False})
    output = Path(config["output_dir"]) / "preflight_output.txt"
    try:
        output.write_text("synthetic boundary canary", encoding="utf-8")
        rows.append({"kind": "output_write", "passed": output.read_text(encoding="utf-8") == "synthetic boundary canary"})
    except OSError as exc:
        rows.append({"kind": "output_write", "passed": False, "errno": exc.errno})
    report = {"passed": bool(rows) and all(row["passed"] for row in rows), "checks": rows}
    Path(config["report_path"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 42


if __name__ == "__main__":
    raise SystemExit(probe(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))))
