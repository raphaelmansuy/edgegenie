"""Documentation search with citations. I/O over the repo's own docs. `[R-20]`.

Genie Code *"searches Databricks documentation to answer your questions"* and shows a **Searched
documentation** step; this product had no corpus and no citation rendering, so an answer about how the
product works could not be checked.

The corpus is this repository's own `docs/` and `specs/`, which is the right first corpus for three reasons:
it is the documentation a user of *this* app needs, it is already written, and it is versioned with the code
it describes. A citation therefore points at a file whose content the same commit guarantees.

**Why the ranking is a pure function elsewhere.** `domain/extension.rank_docs` decides order and limit;
this module reads files. The split is the same one `domain/instructions` / `services/instructions` uses, and
for the same reason: the *rule* is testable without a corpus.

**Bounded, and it says so.** A search reads at most `MAX_FILES` documents and returns at most `limit` hits.
The index is built once per process and cached, because re-reading 60 markdown files per query is work with
no benefit on a filesystem that does not change under a running app.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..domain.extension import DocHit, cite, rank_docs

log = logging.getLogger("app.docsearch")

#: The corpus. Read once, cached for the process.
ROOTS = ("docs", "specs")
#: How many files a search will consider. Beyond this a query is not a search, it is a scan.
MAX_FILES = 400
#: Characters of context around a match.
CONTEXT = 120
#: The public site, so a citation is a link and not a path. Configurable for a fork.
BASE_URL = ""

_INDEX: list[dict] | None = None


def _root() -> Path:
    """The repository root: the nearest ancestor that HAS a `docs` directory.

    Not a fixed `parents[n]`: this file's depth changes when the app is vendored, and an off-by-one
    silently indexed nothing — measured, `parents[3]` was `apps/` and every search returned zero hits while
    reporting success. A directory that exists is a better test than a counted hop.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs").is_dir() and (parent / "specs").is_dir():
            return parent
    return here.parents[-1]


def build(force: bool = False) -> list[dict]:
    """Every markdown document in the corpus, with its title and text. Cached."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    root = _root()
    docs: list[dict] = []
    for group in ROOTS:
        base = root / group
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if len(docs) >= MAX_FILES:
                break
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            docs.append(_doc(path, text, root))
    _INDEX = docs
    log.info("docsearch: %d documents indexed", len(docs))
    return docs


def _doc(path: Path, text: str, root: Path) -> dict:
    """One document: its title (first heading), its relative path, and its text."""
    title = ""
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.lstrip("# ").strip()
            break
    rel = path.relative_to(root).as_posix()
    slug = rel.removesuffix(".md").replace("/", "-")
    url = f"{BASE_URL.rstrip('/')}/{group_of(rel)}/{slug}/" if BASE_URL else rel
    return {"path": rel, "title": title or path.stem, "text": text, "url": url}


def group_of(rel: str) -> str:
    return rel.split("/", 1)[0]


def _excerpt(text: str, at: int, length: int) -> str:
    start = max(0, at - CONTEXT // 2)
    end = min(len(text), at + length + CONTEXT // 2)
    body = " ".join(text[start:end].split())
    return ("…" if start else "") + body + ("…" if end < len(text) else "")


def search(query: str, *, limit: int = 5) -> list[DocHit]:
    """Documents containing every word of the query, best first.

    AND across words, like the journal search: `fence schema` should find the page that explains both, not
    every page that mentions a fence. A title match scores higher than a body match, because a page whose
    title is the query is almost always the page the user wants.
    """
    words = [w.lower() for w in re.split(r"\W+", query) if len(w) > 1]
    if not words:
        return []
    hits: list[DocHit] = []
    for doc in build():
        text = doc["text"].lower()
        if not all(w in text for w in words):
            continue
        title = doc["title"].lower()
        score = sum(3 for w in words if w in title) + sum(1 for w in words if w in text)
        at = text.find(words[0])
        hits.append(DocHit(doc["path"], doc["title"], doc["url"], score,
                           _excerpt(doc["text"], max(0, at), len(words[0]))))
    return rank_docs(hits, limit=limit)


def cite_all(query: str, *, limit: int = 3) -> list[str]:
    """The query's citations, as markdown lines ready to render. Empty when nothing matched."""
    return [cite(hit, matched=query).line() for hit in search(query, limit=limit)]
