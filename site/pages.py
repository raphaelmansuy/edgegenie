"""The route table: the site's structure, declared once.

Adding a page is one `Route` here plus one content file. Nothing else changes — no `build.py` edit, no
`<head>`, no navigation list. That is what `[D7]`'s open/closed rule buys in practice, and
`[10 S6](../specs/008-github-page/10-e2e-plan.md)` asserts it by adding a route in a test.

The order of `ROUTES` is the reading order, and it drives three things at once: the header navigation,
the footer, and each page's previous/next links (`[NAV-7]`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SPECS = ROOT / "specs"


@dataclass(frozen=True)
class Route:
    """One page. `body` receives the build context and returns `(title, description, html, toc)`."""

    path: str  # "" for the home page, "tour/", ...
    nav: str  # the nav key, used for `aria-current` and the header label
    label: str
    title: str
    description: str
    body: Callable[[dict], tuple[str, str, str | None, list[tuple[int, str, str]]]]
    #: The visible page heading. Emitted by `page()` unless the body already contains one, so a page
    #: never has two and never has none — the defect the first build of this site produced (`[AX-2]`).
    h1: str = ""
    hero: bool = False
    #: A page that renders a repository document, with the source path for the "read it on GitHub" link.
    source: str = ""


def _content(name: str):
    """A body function that renders a content file, which may be prose or a claim template."""
    def body(ctx: dict):
        from mdrender import render

        path = ROOT / "site" / "content" / name
        text = path.read_text(encoding="utf-8")
        if "{{claims}}" in text:
            text = text.replace("{{claims}}", ctx["claim_cards"])
        if "fill" in ctx:
            text = ctx["fill"](text, ctx["facts"], f"site/content/{name}")
        # This site's own prose, so its HTML is trusted: the pages use cards and figures on purpose.
        r = render(text, rewrite=ctx["rewrite"], drop_first_h1=True, trusted_html=True)
        return "", "", r.html, r.toc

    return body


def _doc(rel: str, *, title_override: str = "", drop_first_h1: bool = True):
    """A body function that renders a repository document verbatim.

    A document that is not in this checkout (a partial clone, a build from a tarball, or a spec set whose
    screenshots are too heavy to commit) does not crash the build. It becomes a page that says exactly
    which file is missing and links to it on GitHub, because a missing page is a fact a reader can use
    and a 500 is not (spec 008 [E-5], [PF-7]).
    """
    def body(ctx: dict):
        from mdrender import render

        path = ROOT / rel
        if not path.is_file():
            return "", "", _missing_doc(rel, ctx), []
        text = path.read_text(encoding="utf-8")
        # A repository document is content, never markup: its HTML is escaped ([E-9]). Its relative links
        # are rewritten to the built route for that document, because the .md files are not published as
        # files here — they are published as pages ([D1]).
        rewrite, rewrite_image = ctx["doc_rewrite"](rel)
        r = render(text, rewrite=rewrite, rewrite_image=rewrite_image, drop_first_h1=drop_first_h1,
                   strip_lead_nav=True, normalise_headings=True)
        return title_override, "", r.html, r.toc

    return body


def _missing_doc(rel: str, ctx: dict) -> str:
    """The page for a document this checkout does not contain."""
    url = f"{ctx['repo']}/blob/main/{rel}"
    return (
        '<div class="callout callout-warning"><p><strong>This document is not in this checkout.</strong> '
        f'The site renders <code>{rel}</code> at build time, and that file is not present here — most '
        "often because a clone is partial, or because the document's screenshots are too heavy to commit."
        "</p></div>"
        f'<p>The document lives in the repository: <a href="{url}" target="_blank" '
        f'rel="noopener noreferrer">{rel}</a>.</p>'
        '<p>Every other page on this site is unaffected. The evidence, the tour and the tutorial do not '
        "depend on this file.</p>"
    )


def _reference(ctx: dict):
    """The reference index: the docs and the five specification READMEs, with their first lines."""
    from mdrender import render

    items: list[tuple[str, str, str, str]] = []
    listing = [
        ("docs/tutorial.md", "Tutorial", "docs-tutorial", "the 30-minute setup, with screenshots"),
        ("docs/01-big-picture.md", "The big picture", "doc-big-picture", "the problem in plain words"),
        ("docs/02-setup-in-the-databricks-shell.md", "Setup in the Databricks shell", "doc-setup", "the reference setup"),
        ("docs/03-toolbox-cli-skills-mcp.md", "Tools, skills and MCP", "doc-toolbox", "what the agent can use"),
        ("docs/04-safety-and-governance.md", "Safety and governance", "doc-safety", "the fence, and its hole"),
        ("docs/05-exam-suite.md", "The exam suite", "doc-exams", "how the score is produced"),
        ("docs/06-results-and-lessons.md", "Results and lessons", "doc-results", "every number, and its caveat"),
        ("docs/07-decision-guide.md", "Decision guide", "doc-decide", "should you, and how"),
        ("docs/08-architecture.md", "Architecture", "doc-architecture", "context, containers, deployment, and why"),
        ("docs/09-security.md", "Security", "doc-security", "authentication, authorisation, the fence, the gaps"),
        ("docs/10-data-model.md", "The data model", "doc-data-model", "two schemas, nine tables, three kinds of file"),
        ("docs/glossary.md", "Glossary", "doc-glossary", "plain-words definitions"),
        ("docs/genie-code-replacement-spec.md", "The original specification", "doc-original", "the deeper study, 1,060 lines"),
        ("specs/001-databricks-coding-agents/README.md", "001 · The application", "spec-001", "React + FastAPI + ACP"),
        ("specs/005-llm-models/README.md", "005 · Every model, one picker", "spec-005", "the catalogue and the vault"),
        ("specs/006-databricks/README.md", "006 · On par with Genie Code", "spec-006", "the assistant dock"),
        ("specs/007-ux-ui-improve/README.md", "007 · The shell and the keys", "spec-007", "zones, focus, scrolling"),
        ("specs/008-github-page/README.md", "008 · This site", "spec-008", "the page you are reading"),
        ("specs/009-attach-file-clipboard-support/README.md", "009 · Files and screenshots", "spec-009", "attach, drop, paste, and who can see"),
        ("specs/010-long-running/README.md", "010-long-running · Durable sessions", "spec-010-long", "work that survives a closed tab and a restart"),
        ("specs/010-notebook/README.md", "010-notebook · The notebook", "spec-010-notebook", "run ranges, skip, the run map"),
        ("specs/011-ux-coding-mission/README.md", "011 · The mission view", "spec-011", "objective, plan, outputs, proof"),
    ]
    for rel, label, slug, blurb in listing:
        items.append((rel, label, f"/reference/{slug}/", blurb))

    def row(rel: str, label: str, href: str, blurb: str) -> str:
        here = (ROOT / rel).is_file()
        state = "" if here else ' <span class="ref-absent">in the repository, not in this checkout</span>'
        return (
            f'<li><a href="{href}"><strong>{label}</strong></a>'
            f'<span class="ref-blurb">{blurb}{state}</span>'
            f'<a class="ref-source" href="{ctx["repo"]}/blob/main/{rel}" target="_blank" '
            f'rel="noopener noreferrer">source</a></li>'
        )

    rows = "".join(row(rel, label, href, blurb) for rel, label, href, blurb in items)
    body = (
        '<p class="lede">Every document below is rendered from the repository itself, so what you read '
        'here is what the repository says. Each one links to its source file.</p>'
        '<p>Specifications are numbered by their folder in <code>specs/</code>. Only the ones that describe '
        'what ships are listed; the other folders record earlier iterations.</p>'
        f'<ul class="ref-list">{rows}</ul>'
    )
    return "", "", body, []


ROUTES: list[Route] = [
    Route(
        path="", nav="home", label="Home", h1="OpenGenie",
        title="OpenGenie — the Databricks coding agent that runs on the model you choose",
        description=(
            "An open-source Databricks App: a coding agent with Unity Catalog, warehouse, notebook and "
            "job context, on the model you choose, fenced writes, and proof before it says done."
        ),
        body=_content("home.md"),
        hero=True,
    ),
    Route(
        path="tour/", nav="tour", label="Tour", h1="Tour",
        title="Tour — what OpenGenie looks like",
        description=(
            "Real screenshots of the app: the notebook, the assistant bound to it, the mission view "
            "with its evidence, approvals, recovery after a restart, and the model picker."
        ),
        body=_content("tour.md"),
    ),
    Route(
        path="tutorial/", nav="tutorial", label="Tutorial", h1="Tutorial",
        title="Tutorial — set it up in about 30 minutes",
        description=(
            "From a notebook in Databricks to an agent that runs real SQL, builds a notebook and "
            "proves it works. No local shell."
        ),
        body=_doc("docs/tutorial.md"),
        source="docs/tutorial.md",
    ),
    Route(
        path="evidence/", nav="evidence", label="Evidence", h1="Evidence",
        title="Evidence — every score, with its denominator",
        description=(
            "Eleven graded tasks in a live workspace, 174 saved runs. Each number here carries its "
            "fraction, its run count, and what it does not prove."
        ),
        body=_content("evidence.md"),
    ),
    Route(
        path="install/", nav="install", label="Install", h1="Install",
        title="Install — deploy OpenGenie to your workspace",
        description=(
            "Deploy it as a Databricks App, run it locally against your workspace, or try the "
            "shell-only setup from a notebook. What each path needs, and what to change first."
        ),
        body=_content("install.md"),
    ),
    Route(
        path="reference/", nav="reference", label="Reference", h1="Reference",
        title="Reference — the docs and the specifications",
        description=(
            "The documents and specifications, rendered from the repository. Every number traces to a "
            "file you can open."
        ),
        body=_reference,
    ),
    Route(
        path="about/", nav="about", label="About", h1="About",
        title="About — who built OpenGenie, and why",
        description=(
            "Raphael Mansuy on why a model choice is a product decision, and the evidence behind the "
            "page. Links to the repository, LinkedIn and the book."
        ),
        body=lambda ctx: ("", "", ctx["author_html"], []),
    ),
]

#: Pages that render a repository document, so `/reference/` can link to them.
DOC_PAGES: list[tuple[str, str, str]] = [
    ("docs/tutorial.md", "Tutorial", "/tutorial/"),
]

#: Extra pages rendered alongside the routes: a 404 and one page per reference document.
EXTRA: list[tuple[str, str]] = []  # (route, label) — filled by build.py from REFERENCE_PAGES

def pages_doc_target(path_part: str, source_dir: Path) -> str | None:
    """The built route for a document another document links to, or None.

    Resolution is by *file identity*, not by file name: `docs/01-big-picture.md` links to
    `02-setup-in-the-databricks-shell.md`, which lives beside it, while `specs/006/README.md` links to
    `05-data-model-lakebase.md`, which also lives beside it. Comparing resolved paths is the only way to
    tell those apart without a second table to keep in step.
    """
    resolved = (source_dir / path_part).resolve()
    for route in REFERENCE_PAGES:
        rel = ROOT / route[1]
        if rel.resolve() == resolved:
            return f"/reference/{route[0]}/"
    return None


REFERENCE_PAGES: list[tuple[str, str, str, str]] = [
    ("docs-tutorial", "docs/tutorial.md", "Tutorial", "The 30-minute setup"),
    ("doc-big-picture", "docs/01-big-picture.md", "The big picture", "The problem in plain words"),
    ("doc-setup", "docs/02-setup-in-the-databricks-shell.md", "Setup in the Databricks shell", "The reference setup"),
    ("doc-toolbox", "docs/03-toolbox-cli-skills-mcp.md", "Tools, skills and MCP", "What the agent can use"),
    ("doc-safety", "docs/04-safety-and-governance.md", "Safety and governance", "The fence, and its hole"),
    ("doc-exams", "docs/05-exam-suite.md", "The exam suite", "How the score is produced"),
    ("doc-results", "docs/06-results-and-lessons.md", "Results and lessons", "Every number, and its caveat"),
    ("doc-decide", "docs/07-decision-guide.md", "Decision guide", "Should you, and how"),
    ("doc-architecture", "docs/08-architecture.md", "Architecture", "Context, containers, deployment"),
    ("doc-security", "docs/09-security.md", "Security", "Authentication, authorisation, the fence"),
    ("doc-data-model", "docs/10-data-model.md", "The data model", "Two schemas, nine tables, three files"),
    ("doc-glossary", "docs/glossary.md", "Glossary", "Plain-words definitions"),
    ("doc-original", "docs/genie-code-replacement-spec.md", "The original specification", "The deeper study"),
    ("spec-001", "specs/001-databricks-coding-agents/README.md", "001 · The application", "React + FastAPI + ACP"),
    ("spec-005", "specs/005-llm-models/README.md", "005 · Every model, one picker", "The catalogue and the vault"),
    ("spec-006", "specs/006-databricks/README.md", "006 · On par with Genie Code", "The assistant dock"),
    ("spec-007", "specs/007-ux-ui-improve/README.md", "007 · The shell and the keys", "Zones, focus, scrolling"),
    ("spec-008", "specs/008-github-page/README.md", "008 · This site", "The page you are reading"),
    ("spec-009", "specs/009-attach-file-clipboard-support/README.md", "009 · Files and screenshots", "Attach, drop, paste"),
    ("spec-010-long", "specs/010-long-running/README.md", "010-long-running · Durable sessions", "Work that survives a restart"),
    ("spec-010-notebook", "specs/010-notebook/README.md", "010-notebook · The notebook", "Run ranges, skip, the run map"),
    ("spec-011", "specs/011-ux-coding-mission/README.md", "011 · The mission view", "Objective, plan, outputs, proof"),
]


def reference_routes() -> list[Route]:
    """One page per reference document. Generated, so a new document is one table row."""
    out: list[Route] = []
    for slug, rel, label, blurb in REFERENCE_PAGES:
        # A document the checkout does not contain still gets a page (the stub above), but it is marked
        # so the index can say "in the repository" rather than pretending it read it.
        out.append(Route(
            path=f"reference/{slug}/",
            nav="reference",
            label=label,
            h1=label,
            title=f"{label} — OpenGenie reference",
            description=blurb,
            body=_doc(rel),
            source=rel,
        ))
    return out


def all_routes() -> list[Route]:
    return ROUTES + reference_routes()


def is_site_route(href: str) -> bool:
    return href.startswith("/") or href.startswith("#")


def doc_target(href: str) -> str | None:
    """The built route for a repository document, from the link a doc uses to point at it.

    A doc links to `03-toolbox-cli-skills-mcp.md`; the site publishes that as
    `/reference/doc-toolbox/`. This table is the single place the two names are related, so a renamed
    document is one row here and one entry in `REFERENCE_PAGES`, and `check.py` fails on a link that
    resolves to neither.
    """
    name = href.split("#")[0]
    for _slug, rel, _label, _blurb in REFERENCE_PAGES:
        rel_name = rel.rsplit("/", 1)[-1]
        if name == rel_name or name == rel:
            slug = _slug
            return f"/reference/{slug}/"
    return None
