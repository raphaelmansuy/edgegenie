"""Benchmark denominator includes graded work only, never harness/setup failure."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[3]


def exam(monkeypatch):
    monkeypatch.setenv("EXAM_DATABRICKS_TOKEN", "synthetic-exam-token")
    for path in (ROOT / "exams", ROOT / "experiments"):
        monkeypatch.syspath_prepend(str(path))
    spec = importlib.util.spec_from_file_location("exam_validity", ROOT / "exams/run_exam.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure_at", ["identity", "setup", "grade"])
def test_ungraded_failures_never_count_as_zero_score_missions(tmp_path, monkeypatch, failure_at):
    module = exam(monkeypatch)
    import lib

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic qualification failure")

    monkeypatch.setattr(lib, "verify_identity", fail if failure_at == "identity" else lambda: None)
    mission = SimpleNamespace(
        title="Synthetic",
        uses_schema=False,
        max_minutes=0,
        setup=fail if failure_at == "setup" else lambda ctx: None,
        prompt=lambda ctx: "Synthetic",
        cleanup=lambda ctx: None,
        grade=fail if failure_at == "grade" else lambda *args: [],
    )
    monkeypatch.setattr(module, "all_missions", lambda: {"M1": mission})
    monkeypatch.setattr(module, "delete_path", lambda *args: None)
    monkeypatch.setattr(module, "sbx_run", lambda *args: "")
    monkeypatch.setattr(module, "sbx_detached", lambda *args: "")
    monkeypatch.setattr(module, "sbx_fetch", lambda *args: "")
    row = module.run_one("M1", "V1", "gpt-oss-120b", "synthetic", tmp_path)
    assert row["valid"] is False and row["score"] == 0 and row["total"] == 0 and row["pct"] is None
