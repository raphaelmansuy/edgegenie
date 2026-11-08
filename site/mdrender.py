"""Markdown → HTML for the repository's own documents.

The site does not keep a second copy of the docs (`[D1]`). It renders `docs/*.md` and `specs/*/README.md`
at build time, so an edit to a doc appears on the site with no second edit — and, more importantly, a
number cannot be right in one place and wrong in the other.

The renderer is deliberately narrow. It knows the constructs these documents actually use:

  - ATX headings, with a GitHub-compatible slug (so a link that works on GitHub works here, `[NAV-8]`)
  - paragraphs, bold, italic, inline code, links, images
  - fenced code blocks (highlighted with Pygments; mermaid is passed through as a `<pre class="mermaid">`)
  - pipe tables with an alignment row
  - bullet and ordered lists, one level, with nested continuations
  - block quotes, horizontal rules, GitHub alerts (`> [!NOTE]`)
  - HTML comments (stripped: they mark a prose register in the source, not content for a reader)

Anything else is a build error rather than a best guess: an unknown construct that renders as raw text is
the defect this exists to prevent ([E-9](../specs/008-github-page/09-edge-cases.md)).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
except ImportError:  # pragma: no cover
    highlight = None


#: `src -> ' width="1200" height="800"'`, filled by the build from the real pixel size of each image it
#: copies. Declared dimensions are what keep the page from shifting as images arrive (`[PF-2]`).
DIMS: dict[str, str] = {}

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_HR = re.compile(r"^\s*(-{3,}|\*{3,})\s*$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
_UL = re.compile(r"^(\s*)[-*]\s+(.*)$")
_OL = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_COMMENT = re.compile(r"^\s*<!--.*-->\s*$")
_ALERT = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")


# ------------------------------------------------------------------------------------------------ slugs
def slugify(text: str) -> str:
    """GitHub's heading slug, exactly: lowercase, strip inline markup, drop punctuation, and replace
    **each** space with a hyphen.

    The last rule is the one that catches people out. GitHub does not collapse a run of spaces, so
    `Step 4 · Point the agent at a model` becomes `step-4--point-the-agent-at-a-model` with two hyphens,
    because the `·` was removed and left two spaces behind. Collapsing them (the obvious implementation)
    produces `step-4-point-…`, which does not match the anchor a document already links to — and every
    cross-reference in `docs/` is written against GitHub's rule, so the site has to agree with it
    (`[NAV-8]`).
    """
    plain = re.sub(r"<[^>]+>", "", text)
    plain = plain.replace("`", "")
    plain = re.sub(r"[^\w\s-]", "", plain, flags=re.UNICODE)
    return plain.strip().lower().replace(" ", "-") or "section"


def headings(markdown: str, *, normalise: bool = False) -> list[tuple[int, str, str]]:
    """(level, id, text) for the table of contents, skipping fenced code."""
    out: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    ceiling = 1 if normalise else 0
    fenced = False
    for line in markdown.splitlines():
        if _FENCE.match(line.strip()):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _HEADING.match(line)
        if not m:
            continue
        level, text = len(m.group(1)), m.group(2).strip()
        base = slugify(text)
        # GitHub de-duplicates repeated headings with a numeric suffix, so a second "Notes" is
        # `notes-1`. Without this, two sections share an id and every link to the second is wrong.
        n = seen.get(base, 0)
        seen[base] = n + 1
        if ceiling:
            level = max(2, min(level, ceiling + 1))
            ceiling = level
        out.append((level, base if n == 0 else f"{base}-{n}", text))
    return out


def code_css() -> str:
    """One stylesheet for every highlighted block."""
    if highlight is None:
        return ""
    return HtmlFormatter(style="github-dark").get_style_defs(".code pre")


# ----------------------------------------------------------------------------------------- inline pass
def _inline(text: str, *, rewrite=None, rewrite_image=None) -> str:
    """Escape, then apply the inline constructs. Escaping first is what makes `<` in prose safe."""
    # Protect inline code spans before escaping, so their content is not touched.
    spans: list[str] = []
    _dims = DIMS

    def keep(m):
        spans.append(html.escape(m.group(1), quote=False))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep, text)
    text = html.escape(text, quote=False)

    # images before links: `![a](b)` also matches the link pattern
    def image(m):
        alt, src, title = m.group(1), m.group(2), m.group(3)
        if rewrite_image:
            src = rewrite_image(src)
        elif rewrite:
            src = rewrite(src)
        t = f' title="{html.escape(title)}"' if title else ""
        dims = _dims.get(src, "")
        return f'<img src="{src}" alt="{html.escape(alt)}"{dims} loading="lazy" decoding="async"{t} />'

    text = _IMG.sub(image, text)

    def link(m):
        label, href, title = m.group(1), m.group(2), m.group(3)
        if rewrite:
            href = rewrite(href)
        t = f' title="{html.escape(title, quote=True)}"' if title else ""
        ext = ' target="_blank" rel="noopener noreferrer"' if href.startswith(("http://", "https://")) else ""
        return f'<a href="{href}"{t}{ext}>{label}</a>'

    text = _LINK.sub(link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)

    def restore(m):
        return f"<code>{spans[int(m.group(1))]}</code>"

    return re.sub(r"\x00(\d+)\x00", restore, text)


# ----------------------------------------------------------------------------------------- block pass
@dataclass
class Rendered:
    html: str
    toc: list[tuple[int, str, str]]


def render(markdown: str, *, rewrite=None, rewrite_image=None, drop_first_h1: bool = True,
           trusted_html: bool = False, strip_lead_nav: bool = False,
           normalise_headings: bool = False) -> Rendered:
    """Render a document.

    `drop_first_h1` removes the source's own title, which the page supplies.
    `trusted_html` passes block-level HTML through instead of escaping it. It is for **this site's own**
    content files, which use it for cards and figures; a repository document is always escaped, because a
    doc is content, not markup, and a stray `<` there must not become a tag (`[E-9]`).
    `strip_lead_nav` drops the breadcrumb paragraph the repo docs start with, which a site page already
    renders as its header.
    `normalise_headings` shifts every heading so the shallowest present becomes h2. The page supplies the
    h1, so a document whose second line is an `###` subtitle would otherwise jump h1 to h3, and a reader
    using a screen reader's heading list would hear a level that does not exist (`[AX-2]`).
    """
    toc = headings(markdown, normalise=normalise_headings)
    # The page supplies the h1. Every heading after it may be at most one level deeper than the previous
    # one, which is what makes the output's outline valid whatever the source's shape was.
    ceiling = 1 if normalise_headings else 0
    extra_anchors: list[str] = []
    lines = markdown.split("\n")
    out: list[str] = []
    i = 0
    first_h1_seen = False
    seen_content = False

    def flush_paragraph(buf: list[str]) -> None:
        if buf:
            joined = " ".join(buf)
            if strip_lead_nav and not seen_content and _looks_like_nav(joined):
                buf.clear()
                return
            out.append(f"<p>{_inline(joined, rewrite=rewrite, rewrite_image=rewrite_image)}</p>")
            buf.clear()

    para: list[str] = []

    while i < len(lines):
        line = lines[i]

        # -- fenced code ------------------------------------------------------------------------
        m = _FENCE.match(line.strip())
        if m:
            flush_paragraph(para)
            lang = m.group(1)
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            code = "\n".join(body)
            if lang == "mermaid":
                # A diagram is never the only way to read the content: its source is the fallback.
                out.append(
                    '<figure class="diagram">'
                    f'<pre class="mermaid">{html.escape(code)}</pre>'
                    '<noscript><pre class="diagram-source">'
                    f"{html.escape(code)}</pre></noscript>"
                    "</figure>"
                )
            else:
                out.append(_code_block(code, lang))
            seen_content = True
            continue

        # -- blank -----------------------------------------------------------------------------
        if not line.strip():
            flush_paragraph(para)
            i += 1
            continue

        # -- html comment ----------------------------------------------------------------------
        if _COMMENT.match(line):
            i += 1
            continue

        # -- raw html block --------------------------------------------------------------------
        if trusted_html and re.match(r"^\s*<[a-zA-Z]", line):
            flush_paragraph(para)
            block: list[str] = []
            tag = re.match(r"^\s*<([a-zA-Z][\w-]*)", line).group(1).lower()
            void = tag in {"img", "br", "hr", "input", "meta", "link", "source"}
            depth = 0
            while i < len(lines):
                block.append(lines[i])
                depth += len(re.findall(rf"<{tag}[\s>]", lines[i]))
                depth -= len(re.findall(rf"</{tag}>", lines[i]))
                i += 1
                if void:
                    break
                # The block ends only when this tag's own nesting returns to zero. Counting is what
                # makes `<div class="card">…<div>…</div></div>` one block instead of two and a half,
                # which is the defect the first version of this parser produced.
                if depth <= 0:
                    break
            out.append("\n".join(block))
            seen_content = True
            continue

        # -- heading ---------------------------------------------------------------------------
        hm = _HEADING.match(line)
        if hm:
            flush_paragraph(para)
            level, text = len(hm.group(1)), hm.group(2).strip()
            if level == 1 and drop_first_h1 and not first_h1_seen:
                first_h1_seen = True
                # The page supplies the h1, but a document links to its own title (`#01-the-big-picture`).
                # Keeping the anchor on the page's heading is what stops that link from dying ([E-8]).
                if normalise_headings:
                    extra_anchors.append(slugify(text))
                i += 1
                continue
            first_h1_seen = True
            slug = slugify(text)
            if ceiling:
                level = max(2, min(level, ceiling + 1))
                ceiling = level
            out.append(f'<h{level} id="{slug}">{_inline(text, rewrite=rewrite, rewrite_image=rewrite_image)}</h{level}>')
            seen_content = True
            i += 1
            continue

        # -- horizontal rule -------------------------------------------------------------------
        if _HR.match(line):
            flush_paragraph(para)
            out.append("<hr />")
            i += 1
            continue

        # -- table -----------------------------------------------------------------------------
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
            flush_paragraph(para)
            rows: list[list[str]] = []
            header = _split_row(line)
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            out.append(_table(header, rows, rewrite, rewrite_image))
            seen_content = True
            continue

        # -- block quote / alert ---------------------------------------------------------------
        if line.lstrip().startswith(">"):
            flush_paragraph(para)
            quoted: list[str] = []
            kind = ""
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                inner = lines[i].lstrip()[1:].lstrip()
                am = _ALERT.match(lines[i].lstrip())
                if am:
                    kind = am.group(1).lower()
                    if am.group(2):
                        quoted.append(am.group(2))
                else:
                    quoted.append(inner)
                i += 1
            body_text = _inline(" ".join(quoted), rewrite=rewrite)
            if kind:
                out.append(f'<div class="callout callout-{kind}"><p>{body_text}</p></div>')
            else:
                out.append(f"<blockquote><p>{body_text}</p></blockquote>")
            seen_content = True
            continue

        # -- list ------------------------------------------------------------------------------
        um, om = _UL.match(line), _OL.match(line)
        if um or om:
            flush_paragraph(para)
            tag = "ul" if um else "ol"
            items: list[str] = []
            while i < len(lines):
                um2, om2 = _UL.match(lines[i]), _OL.match(lines[i])
                m2 = um2 or om2
                if not m2:
                    # a continuation line belongs to the previous item if it is indented
                    if lines[i].startswith("  ") and lines[i].strip() and items:
                        items[-1] += " " + lines[i].strip()
                        i += 1
                        continue
                    break
                content = (um2.group(2) if um2 else om2.group(3))
                items.append(content)
                i += 1
            out.append(f"<{tag}>" + "".join(
                f"<li>{_inline(it, rewrite=rewrite, rewrite_image=rewrite_image)}</li>" for it in items
            ) + f"</{tag}>")
            seen_content = True
            continue

        para.append(line.strip())
        i += 1

    flush_paragraph(para)
    if extra_anchors:
        # Emitted as empty anchors at the top of the body: invisible, and they make the doc's own
        # self-links resolve.
        out.insert(0, "".join(f'<span id="{a}" class="anchor-alias"></span>' for a in extra_anchors))
    return Rendered("\n".join(out), toc)


_NAV = re.compile(r"^\s*(\[[^\]]+\]\([^)]+\)[^[]*·\s*){3,}")


def _looks_like_nav(text: str) -> bool:
    """The breadcrumb line the repo docs open with. It is a link run joined by middle dots."""
    return bool(_NAV.match(text)) or text.startswith("[Index](")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _table(header: list[str], rows: list[list[str]], rewrite, rewrite_image=None) -> str:
    head = "".join(f"<th>{_inline(c, rewrite=rewrite, rewrite_image=rewrite_image)}</th>" for c in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(c, rewrite=rewrite, rewrite_image=rewrite_image)}</td>" for c in r) + "</tr>"
        for r in rows
    )
    # A wide table scrolls inside its own wrapper; the page never scrolls sideways ([E-19]).
    return (f'<div class="table-wrap" tabindex="0" role="group" aria-label="Table">'
            f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _code_block(code: str, lang: str) -> str:
    if highlight is None or not lang:
        return f'<div class="code"><pre><code>{html.escape(code)}</code></pre></div>'
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        return f'<div class="code"><pre><code>{html.escape(code)}</code></pre></div>'
    return f'<div class="code">{highlight(code, lexer, HtmlFormatter(nowrap=False))}</div>'
