"""Keep the semantic evidence map honest when requirements or referenced tests change."""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "specs/014-improve-agent"


def test_every_requirement_has_existing_evidence_and_an_explicit_gap_assessment():
    requirements = set(re.findall(r"^### (AG-\d+)", (SPEC / "03-requirements.md").read_text(), re.M))
    rows = json.loads((SPEC / "e2e/requirement-evidence.json").read_text())["requirements"]
    assert set(rows) == requirements
    for requirement, row in rows.items():
        assert row["status"] and row["remaining"] and row["tests"], requirement
        for selector in row["tests"]:
            name, _, test = selector.partition("::")
            path = ROOT / name
            assert path.is_file(), (requirement, selector)
            if test:
                functions = {
                    n.name
                    for n in ast.walk(ast.parse(path.read_text()))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                assert test in functions, (requirement, selector)


def test_services_do_not_implement_asset_kind_specific_dispatch():
    trees = [ast.parse(path.read_text()) for path in (ROOT / "apps/coding-agent/api/services").glob("*.py")]
    for node in (node for tree in trees for node in ast.walk(tree)):
        if isinstance(node, ast.Compare):
            values = [node.left, *node.comparators]
            assert not (
                any(isinstance(v, ast.Attribute) and v.attr == "kind" for v in values)
                and any(isinstance(v, ast.Constant) and v.value in {"notebook", "file", "table", "query", "query-draft", "job", "pipeline", "app", "instance", "job_run", "pipeline_update"} for v in values)
            ), node.lineno
