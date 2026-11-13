#!/usr/bin/env python3
"""Kit entry point. The deployable app owns the sole tool/policy implementation.

bootstrap_sandbox.py ships the same source and policy package under /tmp/agentkit.
Legacy exam variants remain frozen in mcp/legacy for reproducible historical scores.
"""

from pathlib import Path

_here = Path(__file__).resolve()
_candidates = (
    _here.parents[1] / "apps/coding-agent/tools/databricks_notebook_mcp.py",
    _here.parent / "agentkit/tools/databricks_notebook_mcp.py",
)
_source = next((path for path in _candidates if path.is_file()), None)
if _source is None:
    raise RuntimeError(
        "Canonical tool source is missing; run exams/bootstrap_sandbox.py to package it."
    )
__file__ = str(_source)
exec(compile(_source.read_text(), str(_source), "exec"), globals())
