#!/usr/bin/env python3
"""Validate spec coverage and printable ASCII boxes; no application behavior is tested."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
errors: list[str] = []


def rows(filename: str, prefix: str) -> dict[str, str]:
    text = (ROOT / filename).read_text()
    found = re.findall(rf"^\| ({prefix}\d+) \| (.*)$", text, flags=re.M)
    result = dict(found)
    if len(result) != len(found):
        errors.append(f"Duplicate {prefix} definition in {filename}")
    return result


requirements = rows("03-requirements.md", "MD-")
risks = rows("09-edge-cases.md", "E")
tests = rows("11-tests-traceability.md", "T")
for collection, expected, label in [
    (requirements, {f"MD-{i:02}" for i in range(1, 19)}, "requirements"),
    (risks, {f"E{i:02}" for i in range(1, 49)}, "risks"),
    (tests, {f"T{i:02}" for i in range(1, 21)}, "test groups"),
]:
    if set(collection) != expected:
        errors.append(f"Wrong {label}: missing={expected-set(collection)}, extra={set(collection)-expected}")

for kind, collection in [("requirement", requirements), ("risk", risks)]:
    for item, row in collection.items():
        test_refs = set(re.findall(r"\bT\d{2}\b", row))
        if not test_refs:
            errors.append(f"Uncovered {kind}: {item}")
        for ref in test_refs - tests.keys():
            errors.append(f"{item} references undefined test {ref}")
        if kind == "risk":
            req_refs = set(re.findall(r"\bMD-\d{2}\b", row))
            if not req_refs:
                errors.append(f"Risk {item} has no requirement")
            for ref in req_refs - requirements.keys():
                errors.append(f"{item} references undefined requirement {ref}")

for item, row in tests.items():
    for ref in set(re.findall(r"\bMD-\d{2}\b", row)) - requirements.keys():
        errors.append(f"{item} references undefined requirement {ref}")
    if not any(item in re.findall(r"\bT\d{2}\b", row) for row in risks.values()):
        # T20 is the aggregate release smoke, not an individual-input risk test.
        if item != "T20":
            errors.append(f"Test group {item} covers no registered risk")

ascii_blocks = 0
mermaid_blocks = 0
for file in sorted(ROOT.glob("*.md")):
    text = file.read_text()
    if not text.endswith("\n") or any(line.rstrip() != line for line in text.splitlines()):
        errors.append(f"Missing final newline or trailing whitespace: {file.name}")
    if file.name != "VALIDATION.md" and "[Index](README.md)" not in text and file.name != "README.md":
        errors.append(f"Missing index link: {file.name}")
    for block in re.findall(r"```ascii\n([\s\S]*?)```", text):
        ascii_blocks += 1
        lines = block.rstrip().splitlines()
        if not block.isascii() or "\t" in block:
            errors.append(f"Non-printable ASCII or tab: {file.name}")
        if any(ord(c) < 32 and c != "\n" for c in block):
            errors.append(f"Control character in ASCII: {file.name}")
        if len(set(map(len, lines))) != 1:
            errors.append(f"Unequal box widths: {file.name}")
        if not lines or lines[0] != lines[-1] or not re.fullmatch(r"\+-+\+", lines[0]):
            errors.append(f"Invalid ASCII box boundary: {file.name}")
        if any(not (line.startswith("| ") and line.endswith(" |")) for line in lines[1:-1]):
            errors.append(f"Invalid ASCII box side: {file.name}")
    for block in re.findall(r"```mermaid\n([\s\S]*?)```", text):
        mermaid_blocks += 1
        if "%%{init:" not in block or '"theme":"base"' not in block or "#E7EEFF" not in block:
            errors.append(f"Missing pastel Mermaid theme: {file.name}")

print(f"{len(requirements)} requirements; {len(risks)} risks; {len(tests)} test groups")
print(f"{ascii_blocks} ASCII boxes; {mermaid_blocks} pastel Mermaid diagrams")
for error in errors:
    print("FAIL", error)
print(f"{len(errors)} problem(s); documentation coverage only, not product test results")
raise SystemExit(bool(errors))

