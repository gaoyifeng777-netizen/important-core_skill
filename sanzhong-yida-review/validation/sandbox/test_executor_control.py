import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import sandbox_executor
from langgraph_runtime import RuntimeViolation


def test_parallel_dispatch_retries_only_a_busy_control_lock(monkeypatch):
    class FakeRuntime:
        count = 0
        def status(self, full):
            self.count += 1
            if self.count < 3:
                raise RuntimeViolation("another runtime command holds the project lock")
            return {"tasks": {"T": {"status": "pending"}}}
    monkeypatch.setattr(sandbox_executor.time, "sleep", lambda value: None)
    runtime = FakeRuntime()
    assert sandbox_executor.read_dispatch_state(runtime)["tasks"]["T"]["status"] == "pending"
    assert runtime.count == 3


def test_source_failure_is_not_retried_as_lock_contention(monkeypatch):
    class FakeRuntime:
        def status(self, full):
            raise RuntimeViolation("sha256 mismatch: private source")
    with pytest.raises(RuntimeViolation, match="sha256"):
        sandbox_executor.read_dispatch_state(FakeRuntime())
