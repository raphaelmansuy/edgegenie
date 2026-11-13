#!/usr/bin/env python3
"""Check spec traceability and simple ASCII grids; no third-party dependencies.

This validates documentation structure, not product behavior or test execution.
Use the repository's link and Mermaid parsers alongside this checker.
"""

from pathlib import Path
import hashlib
import json
import re


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


requirements = (ROOT / "03-requirements.md").read_text()
edges = (ROOT / "09-edge-cases.md").read_text()
tests = (ROOT / "11-test-e2e-plan.md").read_text()
req_ids = set(re.findall(r"^\| (SQ-\d+) \|", requirements, re.M))
mapped_ids = set(re.findall(r"^\| (SQ-\d+) \|", tests, re.M))
test_ids = set(re.findall(r"^\| (T\d+) \|", tests, re.M))
edge_rows = re.findall(r"^\| (EC-\d+) \|(.+)$", edges, re.M)
edge_ids = {edge for edge, _ in edge_rows}
require(req_ids == {f"SQ-{i:02d}" for i in range(1, 25)}, "Requirement inventory mismatch")
require(mapped_ids == req_ids, "Requirement traceability mismatch")
require(test_ids == {f"T{i:02d}" for i in range(1, 19)}, "Test scenario inventory mismatch")
require(edge_ids == {f"EC-{i:02d}" for i in range(1, 65)}, "Edge inventory mismatch")
require(len(edge_rows) == len(edge_ids), "Duplicate edge ID")
for edge, row in edge_rows:
    references = set(re.findall(r"\bT\d+\b", row))
    require(bool(references), f"{edge} has no planned test")
    require(references <= test_ids, f"{edge} refers to unknown planned test")
for req, row in re.findall(r"^\| (SQ-\d+) \|(.+)$", tests, re.M):
    references = set(re.findall(r"\bT\d+\b", row))
    require(bool(references) and references <= test_ids, f"{req} lacks valid test mapping")

ascii_count = 0
mermaid_count = 0
for path in sorted(ROOT.glob("*.md")):
    text = path.read_text()
    require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace in {path.name}")
    require("<!--" not in text, f"Unfilled placeholder in {path.name}")
    require(len(re.findall(r"^```", text, re.M)) % 2 == 0, f"Unclosed fence in {path.name}")
    for block in re.findall(r"```ascii\n([\s\S]*?)```", text):
        ascii_count += 1
        rows = block.rstrip("\n").splitlines()
        require(all(row.isascii() for row in rows), f"Non-ASCII wireframe in {path.name}")
        require(len({len(row) for row in rows}) == 1, f"Unequal grid widths in {path.name}")
        require(rows[0] == rows[-1], f"Unclosed grid in {path.name}")
        columns = [i for i, ch in enumerate(rows[0]) if ch == "+"]
        for row in rows:
            require(all(row[i] in "+|" for i in columns), f"Misaligned border in {path.name}")
    for block in re.findall(r"```mermaid\n([\s\S]*?)```", text):
        mermaid_count += 1
        require("themeVariables" in block, f"Missing pastel theme in {path.name}")

require(ascii_count == 6, "Expected six ASCII navigation/screen diagrams")
require(mermaid_count == 11, "Expected eleven Mermaid architecture/ER/sequence/state/plan diagrams")
for name in ("databricks-sql-editor-reference.png", "databricks-queries-reference.png"):
    require((ROOT / "assets" / name).stat().st_size > 0, f"Missing reference image {name}")

print(f"{len(req_ids)} requirements mapped; {len(edge_ids)} edges mapped to {len(test_ids)} planned scenarios")
print(f"{ascii_count} ASCII grids aligned; {mermaid_count} Mermaid blocks themed; 2 reference images present")
print("Documentation structure passed. See 14-implementation-outcome.md for actual product test evidence; this checker does not execute those tests.")

# Images may only be retained as reviewed evidence while their bytes match the review manifest.
report_path = ROOT / "e2e/report.json"
manifest_path = ROOT / "e2e/screenshots-manifest.json"
if report_path.exists() and manifest_path.exists():
    report = json.loads(report_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    require(report["success"] and not report["browserErrors"], "Browser evidence reports a failure")
    require(len(report["assertions"]) == 16, "Browser check inventory changed; review the evidence record")
    require(len(manifest["images"]) == 18, "Screenshot review inventory mismatch")
    require(
        {Path(path).name for path in report["screenshots"]}
        == {Path(row["file"]).name for row in manifest["images"]},
        "Browser screenshot and review inventories differ",
    )
    for row in manifest["images"]:
        path = ROOT / "e2e" / row["file"]
        require(row["visuallyInspected"], f"Missing inspection record: {path.name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"],
                f"Screenshot changed since visual review: {path.name}")
    print("18 screenshot hashes match the manual review ledger; 16 browser checks report success.")

deployed_manifest_path = ROOT / "e2e/deployed-screenshots-manifest.json"
if deployed_manifest_path.exists():
    deployed = json.loads((ROOT / "e2e/deployed-report.json").read_text())
    manifest = json.loads(deployed_manifest_path.read_text())
    deployment = json.loads((ROOT / "e2e/deployment.json").read_text())
    if manifest.get("version") != deployment.get("version"):
        deployment = json.loads((ROOT / f"e2e/releases/v{manifest['version']}-deployment.json").read_text())
    expected_checks = 17 if manifest.get("version") == "1.2.0-rc.2" else 10
    expected_images = 11 if expected_checks == 17 else 4
    require(deployed["success"] and len(deployed["checks"]) == expected_checks,
            "Live deployment smoke failed or its inventory changed")
    require(not deployed["browserErrors"] and not deployed["transportErrors"],
            "Live browser or transport errors")
    require(deployed["gitCommit"] == manifest["sourceRevision"] == deployment["gitCommit"],
            "Live screenshot revision differs from the deployed revision")
    require(deployed["deploymentId"] == deployment["deploymentId"], "Live deployment ID mismatch")
    require(len(manifest["images"]) == expected_images, "Live screenshot inspection inventory mismatch")
    require({row["file"] for row in deployed["screenshots"]}
            == {row["file"] for row in manifest["images"]}, "Live screenshot inventory mismatch")
    for row in manifest["images"]:
        path = ROOT / "e2e" / row["file"]
        require(row["visuallyInspected"], f"Live image not reviewed: {path.name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"],
                f"Live screenshot changed since inspection: {path.name}")
    if expected_checks == 17:
        require(deployed["coldStartVerified"], "Cold serverless start was not verified")
        require(deployed["restartRecovery"]["verified"] and deployed["restartRecovery"]["resubmissions"] == 0,
                "Actual server restart recovery is unqualified")
        require(deployed["capabilities"]["run"] and deployed["capabilities"]["durable"],
                "SQL execution or durability is disabled")
    print(f"{expected_images} live screenshot hashes match manual review; {expected_checks} deployed checks report success.")

historical = ROOT / "e2e/releases/v1.2.0-rc.1-deployed-screenshots-manifest.json"
if historical.exists():
    manifest = json.loads(historical.read_text())
    for row in manifest["images"]:
        path = ROOT / "e2e" / row["file"]
        require(row["visuallyInspected"] and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"],
                f"Historical deployed image changed or lacks review: {path.name}")
    print("4 historical rc.1 deployed screenshot hashes still match manual review.")

agent_manifest = ROOT / "e2e/agent-screenshots-manifest.json"
if agent_manifest.exists():
    report = json.loads((ROOT / "e2e/agent-report.json").read_text())
    manifest = json.loads(agent_manifest.read_text())
    deployment = json.loads((ROOT / "e2e/deployment.json").read_text())
    if manifest.get("version") != deployment.get("version"):
        deployment = json.loads((ROOT / f"e2e/releases/v{manifest['version']}-deployment.json").read_text())
    require(report["success"] and len(report["checks"]) == 7, "Actual-model query checks failed")
    require(not report["browserErrors"] and not report["transportErrors"], "Actual-model browser errors")
    require(report["gitCommit"] == manifest["sourceRevision"] == deployment["gitCommit"], "AI source revision mismatch")
    require(report["deploymentId"] == manifest["deploymentId"] == deployment["deploymentId"], "AI deployment mismatch")
    require(len(report["cases"]) == 4 and all(c["status"] == "completed" for c in report["cases"]), "Actual-model missions incomplete")
    require(len(manifest["images"]) == 9, "AI screenshot inventory mismatch")
    require({r["file"] for r in report["screenshots"]} == {r["file"] for r in manifest["images"]}, "AI image/report mismatch")
    for row in manifest["images"]:
        path = ROOT / "e2e" / row["file"]
        require(row["visuallyInspected"] and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], f"AI image changed or not reviewed: {path.name}")
    print("9 individually reviewed AI query images match; 4 actual-model missions and 7 live checks passed.")

for prefix in ("cte", "merge"):
    cte_manifest_path = ROOT / f"e2e/{prefix}-screenshots-manifest.json"
    if not cte_manifest_path.exists():
        continue
    report = json.loads((ROOT / f"e2e/{prefix}-report.json").read_text())
    manifest = json.loads(cte_manifest_path.read_text())
    deployment = json.loads((ROOT / "e2e/deployment.json").read_text())
    if manifest["deploymentId"] != deployment["deploymentId"]:
        deployment = json.loads((ROOT / f"e2e/releases/v{manifest['version']}-deployment.json").read_text())
    require(report["success"] and len(report["checks"]) == 8, "CTE live checks failed")
    require(report["gitCommit"] == manifest["sourceRevision"] == deployment["gitCommit"], "CTE source mismatch")
    require(report["deploymentId"] == manifest["deploymentId"] == deployment["deploymentId"], "CTE deployment mismatch")
    require(not report["browserErrors"] and not report["transportErrors"], "CTE browser errors")
    require(report["originalDraftUnchanged"] and report["agent"]["status"] == "completed", "CTE mission or original draft check failed")
    require(len(report["runs"]) == 2 and len({r["statementId"] for r in report["runs"]}) == 2, "CTE native statement inventory mismatch")
    require(len(manifest["images"]) == 7 and {r["file"] for r in manifest["images"]} == {r["file"] for r in report["screenshots"]}, "CTE screenshot inventory mismatch")
    for row in manifest["images"]:
        path = ROOT / "e2e" / row["file"]
        require(row["visuallyInspected"] and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], f"CTE image changed or unreviewed: {path.name}")
    print(f"{prefix}: 7 individually inspected CTE images match; 8 native/actual-model checks passed; original draft unchanged.")
