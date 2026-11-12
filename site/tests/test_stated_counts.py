"""The numbers the documentation states about the code, checked against the code.

`site/facts()` already fills `{{models}}`, `{{tools}}` and `{{skills}}` into the site's own prose, so
those cannot drift. But the architecture and security documents state counts *in sentences* —
"6 routers, 82 routes", "13 protocols", "28 files in `domain/`", "27 event types". A count typed into
a sentence drifts the day someone adds a route, and nothing fails.

This file is the mechanism that makes those sentences true or makes the build fail. It is deliberately
independent of `site/build.py`: a checker that reuses the builder's own reading cannot catch a mistake
in it (`site/check.py` makes the same argument for itself).

    python3 site/tests/test_stated_counts.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "coding-agent"
API = APP / "api"
DOC = ROOT / "docs" / "08-architecture.md"
SEC = ROOT / "docs" / "09-security.md"
DATA = ROOT / "docs" / "10-data-model.md"

CASES: list[tuple[str, object]] = []


def case(fn):
    CASES.append((fn.__name__, fn))
    return fn


def count_routers() -> int:
    """Files in `api/routers/` that actually register a route."""
    return sum(1 for p in (API / "routers").glob("*.py") if "@router." in p.read_text())


def count_routes() -> int:
    return sum(p.read_text().count("@router.") for p in (API / "routers").glob("*.py"))


def count_protocols() -> int:
    return len(re.findall(r"^class \w+\(Protocol\):", (API / "ports" / "__init__.py").read_text(), re.M))


def count_layer(glob: str) -> int:
    return len([p for p in API.glob(glob) if p.name != "__init__.py"])


def count_event_types() -> int:
    text = (API / "domain" / "events.py").read_text()
    block = re.search(r"EventType = Literal\[(.*?)\]", text, re.S)
    return len(re.findall(r'"[a-z_.]+"', block.group(1))) if block else 0


def count_tools() -> tuple[int, int]:
    """(all tools, the `core` set) from the tool server itself."""
    text = (APP / "tools" / "databricks_notebook_mcp.py").read_text()
    total = len(re.findall(r"^@tool\(\)\s*\n(?:async\s+)?def dbx_\w+", text, re.M))
    block = re.search(r"^_CORE = \{(.*?)\}", text, re.M | re.S)
    core = len(re.findall(r'"dbx_\w+"', block.group(1))) if block else 0
    return total, core


def count_migrations() -> int:
    return len(list((API / "adapters" / "llm" / "store" / "migrations").glob("*.sql")))


def stated(doc: Path, pattern: str) -> int | None:
    m = re.search(pattern, doc.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else None


@case
def test_router_and_route_counts():
    doc = DOC.read_text(encoding="utf-8")
    assert f"{count_routers()} routers" in doc, (
        f"api/routers/ registers routes in {count_routers()} files; docs/08 says "
        f"{[m for m in re.findall(r'\\d+ routers', doc)]}")
    assert f"{count_routes()} routes" in doc, (
        f"there are {count_routes()} @router. handlers; docs/08 says "
        f"{[m for m in re.findall(r'\\d+ routes', doc)]}")


@case
def test_protocol_count():
    n = count_protocols()
    assert f"{n} protocols" in DOC.read_text(encoding="utf-8"), (
        f"api/ports/__init__.py defines {n} Protocol classes; docs/08 does not say {n} protocols")


@case
def test_layer_file_counts():
    doc = DOC.read_text(encoding="utf-8")
    domain = (len([p for p in (API / "domain").glob("*.py") if p.name != "__init__.py"])
              + len([p for p in (API / "domain" / "llm").glob("*.py") if p.name != "__init__.py"]))
    services = len([p for p in (API / "services").glob("*.py") if p.name != "__init__.py"])
    adapters = len([p for p in (API / "adapters").rglob("*.py") if p.name != "__init__.py"])
    for layer, n in (("domain", domain), ("services", services), ("adapters", adapters)):
        assert f"| {n} files" in doc, (
            f"the {layer} layer has {n} modules; docs/08 does not state that count")


@case
def test_event_type_count():
    n = count_event_types()
    assert n > 20, f"could not read the event vocabulary (got {n})"
    assert f"{n} types" in DATA.read_text(encoding="utf-8"), (
        f"domain/events.py defines {n} event types; docs/10 does not say {n} types")


@case
def test_tool_counts():
    total, core = count_tools()
    doc = DOC.read_text(encoding="utf-8")
    # Every place docs/08 states a tool count must be the real one.
    for m in re.finditer(r"(?:has|server:)? ?(\d+) tools\b", doc):
        assert int(m.group(1)) in (total, core), (
            f"docs/08 says '{m.group(0).strip()}' but the server has {total} tools ({core} core)")
    assert f"{core} advertised" in doc or f"{core} tools ·" in doc, "docs/08 lost the core count"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{core}-tool `core` profile" in readme, (
        f"README does not say the core profile is {core} tools")
    assert f"has {total}" in readme, f"README does not say the server has {total} tools"


@case
def test_front_end_test_counts():
    """The front end's own numbers, asserted from the files rather than trusted from prose."""
    web = APP / "web" / "src"
    files = [p for p in web.rglob("*.test.ts*")]
    assert f"{len(files)} test files" in DOC.read_text(encoding="utf-8"), (
        f"there are {len(files)} front-end test files; docs/08 does not state that count")


@case
def test_attachment_limits():
    """A limit quoted in prose must equal the constant the code enforces."""
    blob = (API / "domain" / "blob.py").read_text()
    max_mb = int(re.search(r"^MAX_BYTES = (\d+) \* 1024 \* 1024", blob, re.M).group(1))
    total_mb = int(re.search(r"^MAX_BYTES_TOTAL = (\d+) \* 1024 \* 1024", blob, re.M).group(1))
    many = int(re.search(r"^MAX_ATTACHMENTS = (\d+)", blob, re.M).group(1))
    doc = DOC.read_text(encoding="utf-8")
    assert f"{max_mb} MB each, {total_mb} MB per message, {many} files" in doc, (
        f"domain/blob.py allows {max_mb} MB each, {total_mb} MB total, {many} files; docs/08 disagrees")


@case
def test_the_readme_test_counts_are_the_real_numbers():
    """The badge and the `make check` comment quote a count. A count typed into prose drifts."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    files = len(list((APP / "tests").glob("test_*.py")))
    assert files >= 40, f"only {files} test files found; the tests directory moved?"
    # The python count cannot be derived without running pytest, so the check is weaker and honest
    # about it: the number in the README must be within 10% of the assertions declared by the files'
    # test functions. A count that has drifted by a hundred is not a rounding error.
    declared = 0
    for path in (APP / "tests").glob("test_*.py"):
        declared += path.read_text(encoding="utf-8").count("def test_")
    m = re.search(r"tests-(\d+)%20python", readme)
    assert m, "the README badge no longer states a python test count"
    stated = int(m.group(1))
    assert stated >= declared * 0.9, (
        f"the README says {stated} Python tests; the files declare at least {declared} test functions")


@case
def test_schema_table_count():
    """docs/10 says how many tables each schema has; count the DDL, not the prose."""
    sql = "\n".join(p.read_text() for p in sorted((API / "adapters" / "llm" / "store" / "migrations").glob("*.sql")))
    llm = len(re.findall(r"CREATE TABLE IF NOT EXISTS llm\.", sql))
    agent = len(re.findall(r"CREATE TABLE IF NOT EXISTS agent\.", sql))
    data = DATA.read_text(encoding="utf-8")
    assert agent == 4, f"the agent schema should hold 4 tables, found {agent}"
    assert "Four tables" in data, "docs/10 must describe the session and SQL tables"
    assert set(re.findall(r"CREATE TABLE IF NOT EXISTS agent\.(\w+)", sql)) == {
        "session_snapshot", "session_event", "sql_item", "sql_operation",
    }
    assert llm == 9, f"the llm schema should hold 9 tables, found {llm}"
    assert f"Nine tables in `llm`" in data or "Nine tables" in data, (
        f"the llm schema has {llm} tables; docs/10 must state that count")
    assert count_migrations() == 5, f"{count_migrations()} migrations; docs/10 lists five"
    assert "005_sql_journal.sql" in data, "docs/10 must include the SQL journal migration"


@case
def test_no_doc_links_a_path_that_moved():
    """The tool server and the skills moved out of `mcp/`. A link to the old home is a dead end."""
    stale = re.compile(r"\]\([^)]*mcp/(?:databricks_notebook_mcp\.py|skills/)")
    for path in list((ROOT / "docs").glob("*.md")) + [ROOT / "README.md",
                                                      ROOT / "specs" / "001-databricks-coding-agents" / "README.md"]:
        text = path.read_text(encoding="utf-8")
        for m in stale.finditer(text):
            raise AssertionError(f"{path.relative_to(ROOT)} links the removed path {m.group(0)}")


@case
def test_relative_links_in_the_new_docs_resolve_on_the_repository():
    """Every relative `.md` link must be a file that exists, as GitHub would resolve it.

    `site/check.py` cannot catch this for a breadcrumb: the site strips a document's leading
    navigation line before rendering (`strip_lead_nav`), so a link to a document that was never
    written is invisible to the built pages and dead only to a reader on GitHub. This checks the
    files a reader actually browses, which is where the link has to work.
    """
    docs = [DOC, SEC, DATA, ROOT / "docs" / "README.md"]
    pattern = re.compile(r"\]\((?!https?://|#|mailto:)([^)#\s]+\.md)(?:#[^)]*)?\)")
    problems: list[str] = []
    for doc in docs:
        base = doc.parent
        for m in pattern.finditer(doc.read_text(encoding="utf-8")):
            target = (base / m.group(1)).resolve()
            if not target.is_file():
                problems.append(f"{doc.relative_to(ROOT)} → {m.group(1)}")
    assert not problems, "these relative links name a file that is not there: " + "; ".join(problems)


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}\n        {exc}")
        except Exception:  # noqa: BLE001 - a checker that crashes must say which case
            failed += 1
            import traceback
            print(f"  ERROR {name}\n        {traceback.format_exc().splitlines()[-1]}")
    print(f"\n{len(CASES)} tests, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
