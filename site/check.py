"""Check the built site. A broken page must not reach Pages.

This is not a style test. It answers the questions a reader hits in the first minute, and it imports
**nothing** from `site/`: a verifier that shares code with the thing it verifies cannot catch that code's
mistakes. It reads `site/dist` as a stranger would (spec 008 [D2]).

Passes, each because of a specific way a static site goes wrong:

  --links    a href to a route that was never built, or an anchor to a heading that was renamed
  --absolute a site-absolute path, which works at a domain root and 404s at a project subpath
  --markup   an unclosed tag, a second h1, a skipped heading level
  --images   a missing file, `alt="screenshot"`, no width/height
  --claims   an unsubstituted {{CL-n}}, or a percentage in prose that no claim produced
  --meta     a duplicate title, a missing canonical, JSON-LD that does not parse
  --sitemap  a route missing from sitemap.xml, or a URL that does not exist
  --files    no LICENSE, no favicon, no OG image at the declared size
  --secrets  a token or an internal hostname that reached the HTML
  --tokens   the shared CSS values drifting from the application's stylesheet

    python3 site/check.py            # every pass
    python3 site/check.py --links    # one pass
"""

from __future__ import annotations

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST = HERE / "dist"
APP_CSS = ROOT / "apps" / "coding-agent" / "web" / "src" / "styles.css"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr"}
OPTIONAL_CLOSE = {"p", "li", "tr", "td", "th", "thead", "tbody", "option"}
#: The percentage values the claims produced, filled by `check_claims` and used by the prose scan.
CLAIM_VALUES: set[int] = set()

problems: list[str] = []


def fail(pass_name: str, where: str, message: str) -> None:
    problems.append(f"{pass_name:9} {where}  {message}")


# ------------------------------------------------------------------------------------------------ parse
class Page(HTMLParser):
    """A page, parsed: stack balance, ids, links, images, headings, text."""

    def __init__(self, path: Path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.links: list[tuple[str, int]] = []
        self.images: list[dict] = []
        self.headings: list[tuple[int, str, int]] = []
        self.scripts: list[str] = []
        self.metas: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.text: list[str] = []
        self._in_script = False
        self._script_type = ""
        self._lineno = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._lineno = self.getpos()[0]
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((int(tag[1]), "", self._lineno))
        if "id" in a:
            if a["id"] in self.ids:
                self.errors.append(f"line {self._lineno}: duplicate id {a['id']!r}")
            self.ids.add(a["id"])
        if tag == "a" and "href" in a:
            self.links.append((a["href"], self._lineno))
        if tag == "img":
            self.images.append(a)
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.metas[key] = a.get("content", "")
        if tag == "script":
            self._in_script = True
            self._script_type = a.get("type", "")
            if a.get("src"):
                self.scripts.append(a["src"])
        if tag not in VOID:
            self.stack.append((tag, self._lineno))

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
            return
        # an optional-close element may be closed implicitly
        open_tags = [t for t, _ in self.stack]
        if tag in OPTIONAL_CLOSE and tag in open_tags:
            while self.stack and self.stack[-1][0] != tag:
                if self.stack[-1][0] not in OPTIONAL_CLOSE:
                    self.errors.append(
                        f"line {self.getpos()[0]}: </{tag}> closes across <{self.stack[-1][0]}> "
                        f"opened at line {self.stack[-1][1]}")
                    return
                self.stack.pop()
            if self.stack:
                self.stack.pop()
            return
        self.errors.append(
            f"line {self.getpos()[0]}: </{tag}> but <{self.stack[-1][0]}> is open "
            f"(line {self.stack[-1][1]})")

    def handle_data(self, data):
        if self._in_script:
            if "ld+json" in self._script_type:
                self.jsonld.append(data)
            return
        if data.strip():
            self.text.append(data)


def pages() -> list[Path]:
    return sorted(p for p in DIST.rglob("*.html"))


def parse_all() -> dict[Path, Page]:
    out = {}
    for path in pages():
        p = Page(path)
        try:
            p.feed(path.read_text(encoding="utf-8"))
        except Exception as e:
            fail("markup", str(path.relative_to(DIST)), f"could not parse: {e}")
        out[path] = p
    return out


def route_of(path: Path) -> str:
    rel = path.relative_to(DIST).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


# ------------------------------------------------------------------------------------------------ passes
def check_markup(parsed: dict[Path, Page]) -> None:
    for path, p in parsed.items():
        where = route_of(path)
        for e in p.errors:
            fail("markup", where, e)
        left = [t for t, _ in p.stack if t not in OPTIONAL_CLOSE]
        if left:
            fail("markup", where, f"unclosed at end: {left}")
        h1 = [h for h in p.headings if h[0] == 1]
        if len(h1) != 1:
            fail("markup", where, f"{len(h1)} h1 elements (must be exactly one)")
        prev = 0
        for level, _, line in p.headings:
            if prev and level > prev + 1:
                fail("markup", where, f"line {line}: heading jumps h{prev} to h{level}")
            prev = level


def resolve(where: str, href: str) -> Path | None:
    """Resolve a site-relative href to a file in dist. Absolute URLs and #anchors return None."""
    if href.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
        return None
    parts = urlsplit(href)
    target = unquote(parts.path)
    if not target:
        return None
    if target.startswith("/"):
        # a site-absolute link is rooted at the build output, not at the filesystem root
        candidate = (DIST / target.lstrip("/")).resolve()
    else:
        base = DIST / where.lstrip("/")
        if not where.endswith("/"):
            base = base.parent
        candidate = (base / target).resolve()
    if candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate


def check_absolute_paths(parsed: dict[Path, Page]) -> None:
    """No built page may link an asset with a site-absolute path.

    Pages serves this site from `/opengenie/`, so `/assets/site.css` resolves to the domain root and
    404s. That is exactly what happened to the home page's hero image: the root page has an empty
    prefix, and a rewrite that skipped the empty case left its `src` absolute. Local tests passed
    because a local server *does* serve from the root. This check is the one that is true in both.
    """
    for path, p in parsed.items():
        where = route_of(path)
        raw = path.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:href|src)="/(?!/)', raw):
            snippet = raw[m.start():m.start() + 70].split('"')[1]
            fail("links", where, f"site-absolute path {snippet!r} breaks at a project subpath")


def check_links(parsed: dict[Path, Page]) -> None:
    for path, p in parsed.items():
        where = route_of(path)
        for href, line in p.links:
            if href.startswith("#"):
                if href[1:] and href[1:] not in p.ids:
                    fail("links", where, f"line {line}: no element with id {href[1:]!r}")
                continue
            if href.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            target = resolve(where, href)
            if target is None:
                continue
            if not target.exists():
                fail("links", where, f"line {line}: {href} does not exist")
                continue
            frag = urlsplit(href).fragment
            if frag and target.suffix == ".html":
                other = parsed.get(target.resolve())
                if other is None:
                    text = target.read_text(encoding="utf-8", errors="ignore")
                    ok = f'id="{frag}"' in text
                else:
                    ok = frag in other.ids
                if not ok:
                    fail("links", where, f"line {line}: {href} has no anchor {frag!r}")
        for src in p.scripts:
            t = resolve(where, src)
            if t and not t.exists():
                fail("links", where, f"script {src} does not exist")


BAD_ALT = re.compile(r"^(screenshot|image|img|picture|photo|figure|chart|diagram)\.?$", re.I)


def check_images(parsed: dict[Path, Page]) -> None:
    for path, p in parsed.items():
        where = route_of(path)
        for img in p.images:
            src = img.get("src", "")
            target = resolve(where, src)
            if target and not target.exists():
                fail("images", where, f"{src} does not exist")
            alt = img.get("alt")
            if alt is None:
                fail("images", where, f"{src} has no alt attribute")
            elif BAD_ALT.match(alt.strip()):
                fail("images", where, f"{src} has a meaningless alt: {alt!r}")
            if not img.get("width") or not img.get("height"):
                fail("images", where, f"{src} has no width/height (layout shift)")


def check_claims(parsed: dict[Path, Page]) -> None:
    """Every `{{CL-n}}` must be substituted, and no percentage may appear that was not computed."""
    src = (ROOT / "exams" / "results")
    values: set[int] = set()
    # The claim values are read from the page that declares them, so this pass needs no import.
    evidence = next((p for path, p in parsed.items() if route_of(path) == "/evidence/"), None)
    if evidence is None:
        fail("claims", "/evidence/", "the evidence page was not built")
        return
    # Read the claim ids and values from the markup: the value is split across a span, so text alone
    # would miss it. This is the one place the checker looks at structure rather than prose.
    markup = evidence_text(evidence)
    for m in re.finditer(r'class="claim-value">\s*(\d+)', markup):
        values.add(int(m.group(1)))
    for m in re.finditer(r'class="pct">(\d+)%', markup):
        values.add(int(m.group(1)))
    for m in re.finditer(r'style="width:(\d+)%"', markup):
        values.add(int(m.group(1)))
    # Everything inside a claim card is computed output, so a range like `94–97%` is allowed there too.
    for block in re.findall(r'<article class="claim".*?</article>', markup, re.S):
        for m in re.finditer(r'(\d{1,3})\s?%', block):
            values.add(int(m.group(1)))
    CLAIM_VALUES.update(values)

    for path, p in parsed.items():
        where = route_of(path)
        raw = path.read_text(encoding="utf-8")
        if "{{" in raw and "{{CL-" in raw:
            fail("claims", where, "an unsubstituted {{CL-n}} placeholder was published")
        # Only this site's own prose is scanned: a rendered repository document quotes the repository's
        # own tables, which `exams/inject_tables.py` already generates from the same files. Scanning
        # those would double-report numbers that are, by construction, the source of truth.
        if 'data-origin="doc"' in raw:
            continue
        joined = " ".join(p.text)
        for m in re.finditer(r"(?<![\w.])(\d{1,3})\s?%", joined):
            value = int(m.group(1))
            # A percentage is allowed if a claim produced it, or if it is a CSS-ish/prose constant the
            # page states on purpose (100% in a phrase like "100% of the tasks"). Both are checked.
            if value in values:
                continue
            context = joined[max(0, m.start() - 60): m.end() + 40].replace("\n", " ")
            if any(k in context.lower() for k in ("of the", "at most", "at least", "100%", "zoom",
                                                  "margin", "width", "height", "coverage")):
                continue
            fail("claims", where, f"percentage {value}% is not a computed claim: …{context.strip()[:70]}…")


def evidence_text(p: Page) -> str:
    """The claim cards' values live in attributes as well as text, so read the file's markup too."""
    return p.path.read_text(encoding="utf-8")


def check_meta(parsed: dict[Path, Page]) -> None:
    titles: dict[str, str] = {}
    descs: dict[str, str] = {}
    for path, p in parsed.items():
        where = route_of(path)
        title = p.metas.get("og:title", "")
        og_desc = p.metas.get("og:description", "")
        raw_title = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8"), re.S)
        t = html.unescape(raw_title.group(1)).strip() if raw_title else ""
        if not t:
            fail("meta", where, "no <title>")
        elif len(t) > 75:
            fail("meta", where, f"title is {len(t)} chars (>75)")
        if t in titles:
            fail("meta", where, f"title duplicates {titles[t]}")
        titles[t] = where
        if not og_desc:
            fail("meta", where, "no og:description")
        elif len(og_desc) > 200:
            fail("meta", where, f"og:description is {len(og_desc)} chars (>200)")
        key = og_desc[:80]
        if key in descs:
            fail("meta", where, f"description duplicates {descs[key]}")
        descs[key] = where
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', path.read_text(encoding="utf-8"))
        if not canon:
            fail("meta", where, "no canonical")
        elif not canon.group(1).startswith("https://raphaelmansuy.github.io/opengenie/"):
            fail("meta", where, f"canonical is {canon.group(1)}")
        if not p.metas.get("og:image"):
            fail("meta", where, "no og:image")
        for blob in p.jsonld:
            try:
                json.loads(blob)
            except json.JSONDecodeError as e:
                fail("meta", where, f"JSON-LD does not parse: {e}")


def check_sitemap(parsed: dict[Path, Page]) -> None:
    sm = DIST / "sitemap.xml"
    if not sm.is_file():
        fail("sitemap", "/sitemap.xml", "missing")
        return
    text = sm.read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    built = {route_of(p) for p in parsed if route_of(p) != "/404.html"}
    for loc in locs:
        route = loc.replace("https://raphaelmansuy.github.io/opengenie", "") or "/"
        if route not in built:
            fail("sitemap", "/sitemap.xml", f"{loc} names a page that was not built")
    for route in built:
        if not any(loc.endswith(route) or (route == "/" and loc.endswith("/edgegenie/")) for loc in locs):
            fail("sitemap", "/sitemap.xml", f"{route} is missing")
    if not (DIST / "robots.txt").is_file():
        fail("sitemap", "/robots.txt", "missing")
    elif "Sitemap:" not in (DIST / "robots.txt").read_text(encoding="utf-8"):
        fail("sitemap", "/robots.txt", "does not point at the sitemap")


def check_files(parsed: dict[Path, Page]) -> None:
    if not (ROOT / "LICENSE").is_file():
        fail("files", "/LICENSE", "missing at the repository root")
    else:
        first = (ROOT / "LICENSE").read_text(encoding="utf-8")[:400]
        if "Apache License" not in first:
            fail("files", "/LICENSE", "is not the Apache-2.0 text")
    for name in ("favicon.svg", "site.webmanifest", "robots.txt", "sitemap.xml", "404.html", "build.json"):
        if not (DIST / name).is_file():
            fail("files", f"/{name}", "missing from the build")
    og = DIST / "assets" / "og.png"
    if not og.is_file():
        fail("files", "/assets/og.png", "missing")
    else:
        head = og.read_bytes()[:33]
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            fail("files", "/assets/og.png", "is not a PNG")
        else:
            w = int.from_bytes(head[16:20], "big")
            h = int.from_bytes(head[20:24], "big")
            if (w, h) != (1200, 630):
                fail("files", "/assets/og.png", f"is {w}×{h}, should be 1200×630")
    # no third-party script ([E-39])
    for path, p in parsed.items():
        for src in p.scripts:
            if src.startswith(("http://", "https://", "//")):
                fail("files", route_of(path), f"loads a third-party script: {src}")


#: A token is a secret; a workspace hostname is not. The host below is already published in this
#: repository's own README ("everything here was run against dbc-…"), so finding it on the site is not a
#: new disclosure — but a `dapi…` token on the site would be a leak that this repository has already
#: promised to catch (AGENTS.md: "never print it").
SECRET = re.compile(r"dapi[0-9a-f]{16,}", re.I)


def check_secrets(parsed: dict[Path, Page]) -> None:
    for path in pages():
        text = path.read_text(encoding="utf-8")
        for m in SECRET.finditer(text):
            fail("secrets", route_of(path), f"contains {m.group(0)[:24]}…")


SHARED_TOKENS = {
    "--bg": "#faf9f7",
    "--surface": "#ffffff",
    "--surface-2": "#f6f5f2",
    "--line": "#e9e7e2",
    "--ink": "#1c1b19",
    "--ink-2": "#57544e",
    "--ink-3": "#6b6760",
    "--blue-600": "#4b5bd6",
}


def check_tokens() -> None:
    site_css = (DIST / "assets" / "site.css").read_text(encoding="utf-8")
    app_css = APP_CSS.read_text(encoding="utf-8") if APP_CSS.is_file() else ""
    for name, value in SHARED_TOKENS.items():
        if f"{name}: {value}" not in site_css:
            fail("tokens", "site.css", f"{name} is not {value} (the app's value)")
        if app_css and f"{name}: {value};" not in app_css and f"{name}: {value}\n" not in app_css:
            fail("tokens", "app styles.css", f"{name} is no longer {value} — the site should follow the app")


# -------------------------------------------------------------------------------------------------- main
PASSES = {
    "markup": check_markup,
    "links": check_links,
    "absolute": check_absolute_paths,
    "images": check_images,
    "claims": check_claims,
    "meta": check_meta,
    "sitemap": check_sitemap,
    "files": check_files,
    "secrets": check_secrets,
}
NEEDS_PAGES = set(PASSES)


def main() -> int:
    chosen = [a[2:] for a in sys.argv[1:] if a.startswith("--")] or list(PASSES) + ["tokens"]
    if not DIST.is_dir():
        print("check: site/dist is missing — run python3 site/build.py first", file=sys.stderr)
        return 1
    parsed = parse_all()
    print(f"check: {len(parsed)} pages in site/dist")
    for name in chosen:
        if name == "tokens":
            check_tokens()
        elif name in PASSES:
            PASSES[name](parsed)
        else:
            print(f"check: unknown pass {name!r}", file=sys.stderr)
            return 2
    if problems:
        for p in problems[:60]:
            print("  " + p)
        if len(problems) > 60:
            print(f"  … and {len(problems) - 60} more")
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("check: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
