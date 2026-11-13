"""Build the static site into `site/dist`.

This is the composition root: the only file that imports the other modules and the only file that writes
HTML. Everything it needs is resolved before it writes a byte, so a missing screenshot or a missing
document is a build failure with the path named — never a page with a hole in it (spec 008 [PF-7]).

    python3 site/build.py                 # rewrite site/dist
    python3 site/build.py --no-stamp      # reproducibility check (same output twice)

No network, no framework, no node_modules. Pygments is the only third-party import, and it is used for
syntax colouring; without it the build still succeeds and code blocks render uncoloured.
"""

from __future__ import annotations

import argparse
import ast
import html
import re
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "dist"
STATIC = HERE / "static"
sys.path.insert(0, str(HERE))

import author  # noqa: E402
import claims as claims_mod  # noqa: E402
import mdrender  # noqa: E402
import pages  # noqa: E402

SITE_NAME = "OpenGenie"
SITE_URL = "https://raphaelmansuy.github.io/opengenie/"
REPO = "https://github.com/raphaelmansuy/opengenie"
LICENCE = "Apache-2.0"

#: The app's version, read from the file the deployed app reads. One source: if the site and the app
#: disagreed about which release this is, one of them would be describing code it does not serve.
VERSION_FILE = HERE.parent / "apps" / "coding-agent" / "VERSION"

#: Screenshots the content references, by source path. Copied, never committed twice: 286 PNGs already
#: exist in this repository and a second copy would be a second thing to keep in step ([D1]).
SHOTS: dict[str, str] = {
    "app-1440": "specs/006-databricks/e2e/home/deployed-1440-home.png",
    "app-1440-tree": "specs/006-databricks/e2e/home/deployed-1440-tree.png",
    "notebook-1440": "specs/006-databricks/e2e/improve-parity-databricks/01-notebook-toolbar.png",
    "notebook-dark": "specs/006-databricks/e2e/improve-parity-databricks/12-dark-cell-prompt.png",
    "run-all-1440": "specs/006-databricks/e2e/improve-parity-databricks/03-run-all-failed.png",
    "cell-prompt-1440": "specs/006-databricks/e2e/improve-parity-databricks/04-cell-prompt.png",
    "prompt-sent": "specs/006-databricks/e2e/improve-parity-databricks/05-prompt-sent.png",
    "follow-ups": "specs/006-databricks/e2e/improve-parity-databricks/06-follow-ups.png",
    "slash-1440": "specs/006-databricks/e2e/improve-parity-databricks/11-slash-commands.png",
    "plot-1440": "specs/007-ux-ui-improve/e2e/screenshot/71-plot-done.png",
    "run-map-1440": "specs/010-notebook/e2e/screenshots/03-map-open-1440.png",
    "attach-answer": "specs/009-attach-file-clipboard-support/e2e/screenshots/S2-answer-with-evidence.png",
    "attach-refused": "specs/009-attach-file-clipboard-support/e2e/screenshots/S3-refused-no-vision.png",
    "mission-achieved": "specs/011-ux-coding-mission/e2e/iteration-03/05-achieved-desktop.png",
    "mission-evidence": "specs/011-ux-coding-mission/e2e/iteration-03/06-evidence-source.png",
    "mission-approval": "specs/011-ux-coding-mission/e2e/iteration-03/07-approval.png",
    "mission-mobile": "specs/011-ux-coding-mission/e2e/iteration-03/11-mobile-light.png",
    "durable-restart": "specs/010-long-running/e2e/screenshots/09-server-restarted.png",
    "durable-return": "specs/010-long-running/e2e/screenshots/04-return-after-page-close.png",
    "model-picker": "specs/005-llm-models/e2e/01-picker-open.png",
    "fence-copy": "specs/003-improve-dev-ux-ui/e2e/screenshots/07-fence-outside.png",
    "drawer-800": "specs/007-ux-ui-improve/e2e/screenshot/14-800-drawer.png",
    "mission-dark": "specs/011-ux-coding-mission/e2e/iteration-03/09-wide-dark.png",
}


APP = ROOT / "apps" / "coding-agent"
SEED = APP / "seed" / "llm_models.yaml"
TOOL_SERVER = APP / "tools" / "databricks_notebook_mcp.py"
SKILLS = APP / "tools" / "skills"


# ========================================================================================== facts
def facts() -> dict[str, int]:
    """Counts the prose quotes about the application, read from the files that define them.

    The site once said "16 models" while the catalogue held 13. A count typed into prose drifts the day
    someone edits the catalogue, so prose writes `{{models}}` and the build fills it in from source. The core count is read from the pure shared catalogue rather than a duplicated set in the tool server.
    """
    section, providers, models = "", 0, 0
    for line in SEED.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[a-z_]+:", line):
            section = line.split(":", 1)[0]
        elif re.match(r"^  - id:\s*\S", line):
            providers += section == "providers"
            models += section == "models"
    source = TOOL_SERVER.read_text(encoding="utf-8")
    tools = len(re.findall(r"^@tool\(\)\s*\n(?:async\s+)?def dbx_\w+", source, re.M))
    catalogue = ast.parse((TOOL_SERVER.parents[1] / "api/domain/tool_catalogue.py").read_text())
    value = next(n.value for n in catalogue.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "CORE_TOOLS" for t in n.targets))
    core = len(ast.literal_eval(value.args[0]))
    skills = len(list(SKILLS.glob("*.md"))) if SKILLS.is_dir() else 0
    out = {"models": models, "providers": providers, "tools": tools, "core_tools": core, "skills": skills}
    empty = [k for k, v in out.items() if not v]
    if empty:
        raise SystemExit(f"build: could not count {', '.join(empty)} from the application source")
    return out


def fill_facts(text: str, values: dict[str, int], where: str) -> str:
    """Replace `{{name}}` with a fact; an unknown name is a build failure, never a published brace."""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise SystemExit(f"build: {where} uses {{{{{key}}}}}, which is not a known fact")
        return str(values[key])
    return re.sub(r"\{\{([a-z_]+)\}\}", sub, text)


# ========================================================================================== helpers
def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def image_size(path: Path) -> tuple[int, int] | None:
    """Pixel dimensions from the file header. No Pillow, no decode: PNG and JPEG only, which is all the
    site uses. Declared dimensions are what stop the page shifting as images arrive (`[PF-2]`)."""
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if head[:2] == b"\xff\xd8":
        # walk the JPEG markers to the first start-of-frame
        data = path.read_bytes()
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            seg = int.from_bytes(data[i + 2:i + 4], "big")
            i += 2 + seg
    return None


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


MARK = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">'
    '<path d="M18.93 8A8 8 0 1 1 16 5.07" stroke="currentColor" stroke-width="2.15" '
    'stroke-linecap="round"/>'
    '<path d="M18.9 2.1l.82 2.18 2.18.82-2.18.82-.82 2.18-.82-2.18L15.9 5.1l2.18-.82z" '
    'fill="currentColor"/></svg>'
)

ICON_MENU = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" '
             'stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>')
ICON_CLOSE = ('<svg class="icon-close" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" '
              'stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>')
ICON_GH = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
           '<path d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 '
           '0-.24-.01-.87-.01-1.71-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.49-1.11-1.49-.91-.63'
           '.07-.62.07-.62 1 .07 1.53 1.05 1.53 1.05.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37'
           '-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.7 0 0 .84-.28 '
           '2.75 1.05a9.4 9.4 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.4.2 2.44.1 2.7.64.72 1.03 '
           '1.63 1.03 2.75 0 3.93-2.35 4.8-4.58 5.05.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 '
           '.27.18.6.69.49A10.03 10.03 0 0 0 22 12.25C22 6.58 17.52 2 12 2z"/></svg>')
ICON_SUN = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.2" '
            'stroke="currentColor" stroke-width="1.8"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 '
            '12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6" '
            'stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>')
ICON_MOON = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 0 1 '
             '9.5 4a8.5 8.5 0 1 0 10.5 10.5z" stroke="currentColor" stroke-width="1.8" '
             'stroke-linejoin="round"/></svg>')
ICON_AUTO = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.4" '
             'stroke="currentColor" stroke-width="1.8"/><path d="M12 3.6v16.8" stroke="currentColor" '
             'stroke-width="1.8"/><path d="M12 3.6a8.4 8.4 0 0 1 0 16.8z" fill="currentColor"/>'
             '</svg>')


#: Pages serves `404.html` at whatever path was missing (`/opengenie/a/b/`), so the relative links every
#: other page uses would resolve against that path and lose the stylesheet. The 404 page alone pins its
#: base to the project root; `check.py --absolute` allows exactly this one tag.
BASE_404 = f'<base href="{urlsplit(SITE_URL).path}" />\n'


def prefix_for(route: str) -> str:
    """Relative path back to the site root. Every link is relative so a subpath deploy works ([NAV-1])."""
    if route in ("", "/", "404"):
        # `404.html` sits at the build root, like `index.html`, so it needs no prefix.
        return ""
    depth = route.rstrip("/").count("/") + 1
    return "../" * depth


def head(*, route: str, title: str, description: str, canonical_route: str, jsonld: dict | None,
         prefix: str, choice: str) -> str:
    canonical = SITE_URL + ("" if canonical_route in ("", "/") else canonical_route)
    og_image = f"{SITE_URL}assets/og.png"
    structured = (
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        if jsonld else ""
    )
    return f"""<!doctype html>
<html lang="en" data-root="{prefix}">
<head>
<meta charset="utf-8" />
{BASE_404 if route == "404" else ""}<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}" />
<link rel="canonical" href="{esc(canonical)}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<meta name="author" content="Raphael Mansuy" />
<meta name="color-scheme" content="light dark" />
<meta name="theme-color" content="#faf9f7" media="(prefers-color-scheme: light)" />
<meta name="theme-color" content="#131211" media="(prefers-color-scheme: dark)" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="{SITE_NAME}" />
<meta property="og:locale" content="en_US" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(description)}" />
<meta property="og:url" content="{esc(canonical)}" />
<meta property="og:image" content="{og_image}" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="OpenGenie: a Databricks coding agent with the model you choose." />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(title)}" />
<meta name="twitter:description" content="{esc(description)}" />
<meta name="twitter:image" content="{og_image}" />
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="{prefix}assets/icon-192.png" />
<link rel="manifest" href="{prefix}site.webmanifest" />
<link rel="stylesheet" href="{prefix}assets/site.css" />
<script>/* before first paint: no theme flash ([NAV-3]) */
(function(){{try{{var c=localStorage.getItem('opengenie-theme')||'system';
var d=c==='dark'||(c==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);
document.documentElement.setAttribute('data-theme',d?'dark':'light');
document.documentElement.setAttribute('data-theme-choice',c);}}catch(e){{}}}})();
</script>
{structured}
</head>"""


def header(route: str, *, prefix: str, nav_key: str) -> str:
    items = [(r.nav, r.label, r.path) for r in pages.ROUTES]
    links = []
    for key, label, path in items:
        current = ' aria-current="page"' if key == nav_key and path == route else ""
        if key == nav_key and path != route:
            # a reference sub-page belongs to the Reference item; mark it but do not link to itself
            current = ' aria-current="page"'
        links.append(f'<a href="{prefix}{esc(path)}"{current}>{esc(label)}</a>')
    nav = "".join(links)
    return f"""<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
  <a class="brand" href="{prefix or './'}" aria-label="OpenGenie home">
    <span class="mark">{MARK}</span>
    <span><span class="wordmark-a">Open</span><span class="wordmark-b">Genie</span></span>
  </a>
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav" data-nav-toggle>
    {ICON_MENU}{ICON_CLOSE}<span>Menu</span>
  </button>
  <nav id="site-nav" class="site-nav" aria-label="Main">{nav}
    <a class="nav-gh" href="{REPO}" target="_blank" rel="noopener noreferrer">Repository on GitHub</a>
  </nav>
  <div class="head-tools">
    <div class="theme-switch" role="group" aria-label="Colour theme">
      <button type="button" data-theme-choice-btn="system" aria-pressed="true" title="Follow the system">
        {ICON_AUTO}<span class="sr">System theme</span></button>
      <button type="button" data-theme-choice-btn="light" aria-pressed="false" title="Light">
        {ICON_SUN}<span class="sr">Light theme</span></button>
      <button type="button" data-theme-choice-btn="dark" aria-pressed="false" title="Dark">
        {ICON_MOON}<span class="sr">Dark theme</span></button>
    </div>
    <a class="gh-link" href="{REPO}" target="_blank" rel="noopener noreferrer">
      {ICON_GH}<span class="sr">Repository on GitHub</span></a>
  </div>
</header>"""


def app_version() -> str:
    """`1.0.0`, or `unknown`. Never a guess: a site that invents a release number is a site that lies."""
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return text if re.match(r"^\d+\.\d+\.\d+", text) else "unknown"


def footer(*, prefix: str, commit: str, built: str) -> str:
    pages_links = "".join(f'<a href="{prefix}{esc(r.path)}">{esc(r.label)}</a>' for r in pages.ROUTES)
    return f"""<footer class="site-foot">
  <div class="foot-inner">
    <div>
      <div class="foot-brand"><span class="mark">{MARK}</span><strong>OpenGenie</strong></div>
      <p>A Databricks App that hosts a coding agent: the model you choose, writes fenced to a folder you
      name, and proof before it says done.</p>
      <p>{LICENCE} · <a href="{REPO}/releases/tag/v{esc(app_version())}">v{esc(app_version())}</a>
      · built {esc(built)} from <code>{esc(commit)}</code></p>
    </div>
    <div><p class="foot-title">Pages</p>{pages_links}</div>
    <div>
      <p class="foot-title">Source</p>
      <a href="{REPO}" target="_blank" rel="noopener noreferrer">Repository</a>
      <a href="{REPO}/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">Licence</a>
      <a href="{REPO}/tree/main/docs" target="_blank" rel="noopener noreferrer">Documentation</a>
      <a href="{REPO}/tree/main/specs" target="_blank" rel="noopener noreferrer">Specifications</a>
      <a href="{REPO}/tree/main/exams/results" target="_blank" rel="noopener noreferrer">Every saved run</a>
    </div>
    <div>
      <p class="foot-title">Elsewhere</p>
      <a href="{author.LINKEDIN}" target="_blank" rel="noopener noreferrer">LinkedIn</a>
      <a href="{author.GITHUB_PROFILE}" target="_blank" rel="noopener noreferrer">GitHub</a>
      <a href="https://raphaelmansuy.github.io/edgepii/" target="_blank" rel="noopener noreferrer">EdgePii</a>
      <a href="https://edgequake.com/" target="_blank" rel="noopener noreferrer">EdgeQuake</a>
      <a href="{author.BOOK}" target="_blank" rel="noopener noreferrer">The book</a>
    </div>
  </div>
</footer>"""


def toc_html(toc: list[tuple[int, str, str]]) -> str:
    rows = [r for r in toc if 1 < r[0] <= 3]
    if len(rows) < 3:
        return ""
    items = "".join(
        f'<li class="toc-l{level}"><a href="#{anchor}">{esc(text)}</a></li>'
        for level, anchor, text in rows
    )
    return (f'<aside class="toc" aria-label="On this page">'
            f'<p class="toc-title">On this page</p><ul>{items}</ul></aside>')


def toc_inline(toc: list[tuple[int, str, str]]) -> str:
    """The same contents as the rail, collapsed, for the widths where the rail is hidden (CSS decides)."""
    rows = [r for r in toc if 1 < r[0] <= 3]
    if len(rows) < 3:
        return ""
    items = "".join(
        f'<li class="toc-l{level}"><a href="#{anchor}">{esc(text)}</a></li>'
        for level, anchor, text in rows
    )
    return f'<details class="toc-inline"><summary>On this page</summary><ul>{items}</ul></details>'


def pager(route: str, routes: list[pages.Route], *, prefix: str) -> str:
    order = [r.path for r in routes]
    if route not in order:
        return ""
    i = order.index(route)
    prev = routes[i - 1] if i > 0 else None
    nxt = routes[i + 1] if i + 1 < len(routes) else None
    parts = ['<nav class="pager" aria-label="Previous and next">']
    if prev:
        parts.append(f'<a class="prev" href="{prefix}{esc(prev.path)}">'
                     f'<span><span class="dir">Previous</span>{esc(prev.label)}</span></a>')
    if nxt:
        parts.append(f'<a class="next" href="{prefix}{esc(nxt.path)}">'
                     f'<span><span class="dir">Next</span>{esc(nxt.label)}</span></a>')
    parts.append("</nav>")
    return "".join(parts)


def zoomable(body: str) -> str:
    """Every screenshot opens at full size, and its provenance chips sit on their own line.

    A 1440 px capture on a 390 px phone is a quarter of its size, so the frame becomes a link to the
    image itself. The chips are grouped so the caption's sentence starts on a line of its own instead of
    wrapping one word after the last chip (both seen in tests/sites/e2e/screenshots).
    """
    body = re.sub(
        r'<div class="frame">(\s*<img [^>]*?src="([^"]+)"[^>]*>\s*)</div>',
        r'<a class="frame" href="\2" title="Open the full-size screenshot">\1</a>', body)
    # a picture on its own in a rendered document (the tutorial's terminal captures) opens the same way
    body = re.sub(r'<p>(<img [^>]*?src="([^"]+)"[^>]*>)</p>',
                  r'<p><a class="zoom" href="\2" title="Open the full-size image">\1</a></p>', body)
    return re.sub(r'((?:<span class="shot-meta">[^<]*</span>\s*)+)',
                  r'<span class="shot-metas">\1</span>', body)


def localise(body: str, prefix: str) -> str:
    """Turn every site-absolute link in a rendered body into a relative one.

    The site may be served from a project subpath (`/edgegenie/`) or from a root, and the same build has
    to work in both (`[NAV-1]`). Authors therefore write `href="/tour/"`, which is unambiguous to read,
    and this function makes it work at whatever depth the page sits. It runs on the **rendered** body,
    so it catches links in markdown, in this site's trusted HTML, and in a rendered repository document
    alike — the one place all three pass through.
    """
    # At the site root the prefix is empty, and `/assets/x.png` must become `assets/x.png`: the site never
    # knows its own mount point, so an absolute path is correct at a domain root and broken at a project
    # subpath. That was a real defect — the home page 404'd its hero image on Pages while every other
    # page worked, because those had a prefix and this one did not.
    return re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{prefix}', body)


def page(*, route: str, routes: list[pages.Route], title: str, description: str,
         body: str, nav_key: str, toc: list[tuple[int, str, str]], hero: bool,
         commit: str, built: str, source: str = "", h1: str = "", origin: str = "content") -> str:
    prefix = prefix_for(route)
    body = localise(zoomable(body), prefix)
    rail = "" if hero else toc_html(toc)
    shell_class = "shell" if rail else ("shell no-rail is-home" if hero else "shell no-rail")
    # One h1, exactly: the body may supply its own (the home hero, the author page), and if it does not,
    # the route's own heading is emitted here. `check.py` fails on any page with zero or two ([AX-2]).
    heading = "" if re.search(r"<h1[\s>]", body) else f'<h1 class="page-title">{esc(h1 or title.split(" — ")[0])}</h1>'
    jsonld = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": SITE_NAME,
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Databricks",
        "description": description,
        "url": SITE_URL + route,
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "codeRepository": REPO,
        "author": {"@type": "Person", "name": "Raphael Mansuy", "url": author.GITHUB_PROFILE},
        "isAccessibleForFree": True,
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL},
        ] + ([] if not route else [
            {"@type": "ListItem", "position": 2, "name": title.split(" — ")[0],
             "item": SITE_URL + route},
        ]),
    }
    return f"""{head(route=route, title=title, description=description, canonical_route=route,
        jsonld=jsonld, prefix=prefix, choice="system")}
<body class="{'page-home' if hero else 'page-doc'} layout-{'rail' if rail else ('home' if hero else 'narrow')}" data-origin="{origin}">
{header(route, prefix=prefix, nav_key=nav_key)}
<div class="{shell_class}">
  {rail}
  <main id="main" class="main">
{heading}
{toc_inline(toc) if rail else ""}
{body}
{pager(route, routes, prefix=prefix)}
  </main>
</div>
{footer(prefix=prefix, commit=commit, built=built)}
<script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
<script src="{prefix}assets/site.js" defer></script>
</body>
</html>
"""


def claim_cards(claim_list: list) -> str:
    """The claim card, rendered from the model. The caveat is inside the card, not after it ([CPT-2])."""
    out = []
    for c in claim_list:
        bars = ""
        if c.id == "CL-3":
            bars = (
                '<div class="claim-bars">'
                f'<div class="claim-bar"><span class="label">gpt-oss-120b</span>'
                f'<span class="track"><span class="fill is-weak" style="width:{c.extra["weak"]}%"></span></span>'
                f'<span class="pct">{c.extra["weak"]}%</span></div>'
                f'<div class="claim-bar"><span class="label">Gemini 3.8 Flash</span>'
                f'<span class="track"><span class="fill" style="width:{c.extra["strong"]}%"></span></span>'
                f'<span class="pct">{c.extra["strong"]}%</span></div>'
                "</div>"
            )
        elif c.id == "CL-4":
            bars = (
                '<div class="claim-bars">'
                f'<div class="claim-bar"><span class="label">bare shell (V0)</span>'
                f'<span class="track"><span class="fill is-weak" style="width:{c.extra["from"]}%"></span></span>'
                f'<span class="pct">{c.extra["from"]}%</span></div>'
                f'<div class="claim-bar"><span class="label">scoped (V4)</span>'
                f'<span class="track"><span class="fill" style="width:{c.value}%"></span></span>'
                f'<span class="pct">{c.value}%</span></div>'
                "</div>"
            )
        elif c.id == "CL-6":
            bars = (
                '<div class="claim-bars">'
                f'<div class="claim-bar"><span class="label">{c.extra["trials"]} runs</span>'
                f'<span class="track"><span class="fill" style="width:{c.value}%"></span></span>'
                f'<span class="pct">{c.extra["low"]}–{c.extra["high"]}%</span></div>'
                "</div>"
            )

        if c.kind.value == "percent":
            value_html = f'{c.value}%<span class="of">{c.fraction}</span>'
        elif c.kind.value == "tokens":
            value_html = (f'{c.extra["strong_k"]}k<span class="of">tokens per task, against '
                          f'{c.extra["weak_k"]}k</span>')
        else:
            # the harness calls them missions; the page calls them what a reader knows: tasks
            unit = "graded tasks" if c.unit == "missions" else c.unit
            value_html = f'{c.value}<span class="of">{esc(unit)}</span>'

        sources = " · ".join(f"<code>{esc(s)}</code>" for s in c.sources)
        out.append(f"""<article class="claim" id="{esc(c.id.lower())}">
  <div class="claim-head">
    <span class="claim-id">{esc(c.id)}</span>
    <span class="claim-value">{value_html}</span>
  </div>
  <p class="claim-statement">{esc(c.statement)}</p>
  {bars}
  <dl class="claim-meta">
    <dt>how it was measured</dt><dd>{esc(c.tasks)} &middot; {c.runs} graded run{'s' if c.runs != 1 else ''}</dd>
    <dt>what it does not prove</dt><dd>{esc(c.caveat)}</dd>
    <dt>source</dt><dd>{sources}</dd>
    <dt>regenerate</dt><dd><code>python3 site/claims.py</code></dd>
  </dl>
</article>""")
    return "\n".join(out)


# ============================================================================================ build
def copy_assets(dist: Path) -> dict:
    """Copy the stylesheet, script, icons and vendored Mermaid, then the screenshots content needs."""
    assets = dist / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("site.css", "site.js"):
        shutil.copy2(STATIC / name, assets / name)
    shutil.copy2(HERE / "vendor" / "mermaid.min.js", assets / "mermaid.min.js")
    (dist / "favicon.svg").write_text((STATIC / "favicon.svg").read_text(encoding="utf-8"), encoding="utf-8")

    for rel in ("author", "projects", "book"):
        src = STATIC / rel
        dst = assets / rel
        dst.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)

    # og image: a card, generated at build time from the same tokens the page uses
    make_og(assets / "og.png")

    shots_dir = assets / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    missing = []
    copied = 0
    for name, rel in SHOTS.items():
        src = ROOT / rel
        if not src.is_file():
            missing.append(rel)
            continue
        shutil.copy2(src, shots_dir / f"{name}.png")
        size = image_size(src)
        if size:
            mdrender.DIMS[f"assets/shots/{name}.png"] = f' width="{size[0]}" height="{size[1]}"'
            mdrender.DIMS[f"/assets/shots/{name}.png"] = mdrender.DIMS[f"assets/shots/{name}.png"]
        copied += 1
    if missing:
        raise SystemExit(
            "build: the content references screenshots that do not exist:\n  " + "\n  ".join(missing)
        )

    # The tutorial's own screenshots: the doc references them relatively, and the site publishes them
    # rather than hot-linking GitHub, so a reader on a slow connection gets them from the same origin.
    tut_src = ROOT / "docs" / "e2e" / "screenshots" / "tutorial"
    tut_dst = assets / "tutorial"
    if tut_src.is_dir():
        tut_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(tut_src.glob("*.png")):
            shutil.copy2(f, tut_dst / f.name)
            size = image_size(f)
            if size:
                mdrender.DIMS[f"assets/tutorial/{f.name}"] = f' width="{size[0]}" height="{size[1]}"'
                mdrender.DIMS[f"/assets/tutorial/{f.name}"] = mdrender.DIMS[f"assets/tutorial/{f.name}"]

    # icons for the manifest and the iOS home screen, derived from the one mark
    for size in (192, 512):
        make_icon(assets / f"icon-{size}.png", size)

    return {"shots": copied}


def make_og(path: Path) -> None:
    """A 1200×630 card. Drawn with Pillow when it is available; a committed PNG otherwise."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        fallback = STATIC / "og.png"
        if fallback.is_file():
            shutil.copy2(fallback, path)
            return
        raise SystemExit(
            "build: cannot produce assets/og.png — install Pillow, or commit the fallback at "
            f"{fallback.relative_to(ROOT)}"
        )
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#faf9f7")
    d = ImageDraw.Draw(img)
    # the app's warm paper, one accent band, and the mark as a filled circle with a gap
    d.rectangle([0, 0, W, 6], fill="#4b5bd6")
    d.ellipse([72, 84, 132, 144], outline="#4b5bd6", width=9)
    d.polygon([(150, 84), (159, 105), (180, 114), (159, 123), (150, 144), (141, 123), (120, 114), (141, 105)],
              fill="#4b5bd6")
    sans = None
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).is_file():
            try:
                sans = ImageFont.truetype(candidate, 78)
                break
            except Exception:
                continue
    if sans is None:
        sans = ImageFont.load_default()

    def text(xy, s, font, fill):
        d.text(xy, s, font=font, fill=fill)

    text((72, 190), "OpenGenie", sans, "#1c1b19")
    small = ImageFont.truetype(sans.path, 40) if hasattr(sans, "path") else sans
    text((72, 300), "A Databricks coding agent", small, "#57544e")
    text((72, 356), "with the model you choose.", small, "#57544e")
    tiny = ImageFont.truetype(sans.path, 28) if hasattr(sans, "path") else sans
    text((72, 470), "Your model · a write fence · proof before it says done", tiny, "#6b6760")
    text((72, 540), "Apache-2.0 · raphaelmansuy.github.io/opengenie", tiny, "#6b6760")
    img.save(path, "PNG", optimize=True)


def make_icon(path: Path, size: int) -> None:
    """Draw the app icon, or copy the committed one.

    The site must build with `python3` alone (`[D3]`), so neither of these images may depend on Pillow
    being installed. When it is, the icon is drawn from the same mark the header uses; when it is not,
    the PNG committed beside this script is used. Either way the file exists, so `check.py`'s
    `--files` pass means what it says on a machine with no optional dependency.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        fallback = STATIC / f"icon-{size}.png"
        if fallback.is_file():
            shutil.copy2(fallback, path)
        return
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill="#4b5bd6")
    # the ring, open at the top right, and the spark in the gap — the app's mark, at one size
    pad = int(s * 0.26)
    d.arc([pad, pad, s - pad, s - pad], start=300, end=215, fill="#ffffff", width=int(s * 0.055))
    cx, cy = int(s * 0.72), int(s * 0.24)
    r = int(s * 0.09)
    d.polygon([(cx, cy - r), (cx + r * 0.38, cy - r * 0.38), (cx + r, cy),
               (cx + r * 0.38, cy + r * 0.38), (cx, cy + r), (cx - r * 0.38, cy + r * 0.38),
               (cx - r, cy), (cx - r * 0.38, cy - r * 0.38)], fill="#ffffff")
    img.resize((size, size), Image.LANCZOS).save(path, "PNG", optimize=True)


def build(*, stamp: bool = True) -> dict:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    commit = git_commit() if stamp else "0000000"
    built = datetime.now(timezone.utc).strftime("%-d %B %Y") if stamp else "1 January 2026"

    FACTS = facts()
    claim_list, excluded = claims_mod.compute()
    missing = [(c.id, m) for c in claim_list for m in claims_mod.missing(c)]
    if missing:
        raise SystemExit("build: claims cite paths that do not exist: " + repr(missing))

    info = copy_assets(OUT)

    def identity(target: str) -> str:
        """The site's own prose uses routes, not repository paths, so it needs no rewriting."""
        return target

    ctx = {
        "rewrite": identity,
        "claim_cards": claim_cards(claim_list),
        "author_html": "",
        "repo": REPO,
        "facts": FACTS,
        "fill": fill_facts,
    }

    def doc_rewrite(source_rel: str):
        """Rewrite a relative link inside a rendered document.

        Three cases, in order:
          1. another repository document → the route the site publishes it at, keeping its anchor;
          2. a file in the repository → the GitHub blob URL, because it is not published here;
          3. a site route (`/tour/`) → left alone.
        Getting this wrong is what produces a dead link in a reference section nobody proof-reads.
        """
        from urllib.parse import urlsplit
        source_dir = (ROOT / source_rel).parent

        def rewrite_image(target: str) -> str:
            """A doc's own screenshots become same-origin assets.

            The tutorial's images live in `docs/e2e/screenshots/tutorial/`, which the build copies to
            `assets/tutorial/`. Serving them from this origin is faster and works offline; hot-linking
            GitHub would make every tutorial page depend on github.com's availability.
            """
            name = target.rsplit("/", 1)[-1]
            if name in {p.name for p in (ROOT / "docs" / "e2e" / "screenshots" / "tutorial").glob("*.png")}:
                return f"/assets/tutorial/{name}"
            return rewrite(target)

        def rewrite(target: str) -> str:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                return target
            if target.startswith("/"):
                return target
            parts = urlsplit(target)
            path_part, frag = parts.path, (f"#{parts.fragment}" if parts.fragment else "")

            # 1. another doc in the same site
            route = pages.pages_doc_target(path_part, source_dir)
            if route:
                return route + frag

            # 2. anything else that exists in the repository
            resolved = (source_dir / path_part).resolve()
            try:
                rel = resolved.relative_to(ROOT).as_posix()
            except ValueError:
                rel = path_part.lstrip("./")
            return f"{ctx['repo']}/blob/main/{rel}{frag}"

        return rewrite, rewrite_image

    ctx["doc_rewrite"] = doc_rewrite

    routes = pages.all_routes()
    written: list[str] = []

    for r in routes:
        prefix = prefix_for(r.path)
        if r.nav == "about":
            ctx["author_html"] = author.section(prefix, commit=commit, built=built)
        title, description, body, toc = r.body(ctx)
        final_title = title or r.title
        final_desc = description or r.description
        html_text = page(
            route=r.path, routes=routes, title=final_title, description=final_desc,
            body=body or "", nav_key=r.nav, toc=toc, hero=r.hero,
            commit=commit, built=built, source=r.source, h1=r.h1,
            # a page rendered from a repository document quotes that document's numbers, which are the
            # source of truth and are checked by exams/inject_tables.py, not by this site
            origin="doc" if r.source else "content",
        )
        target = OUT / (r.path or "") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_text, encoding="utf-8")
        written.append("/" + r.path)

    # 404, sitemap, robots, manifest
    (OUT / "404.html").write_text(page(
        route="404", routes=routes, title="Page not found — OpenGenie",
        description="That page is not here. The seven routes of the OpenGenie site.",
        body=NOT_FOUND, nav_key="", toc=[], hero=False, commit=commit, built=built, origin="content",
    ), encoding="utf-8")
    written.append("/404.html")

    urls = "".join(
        f"  <url><loc>{SITE_URL}{r.path}</loc><changefreq>weekly</changefreq>"
        f"<priority>{'1.0' if not r.path else '0.7'}</priority></url>\n"
        for r in routes
    )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")
    (OUT / "site.webmanifest").write_text(json.dumps({
        "name": "OpenGenie", "short_name": "OpenGenie",
        "description": "A Databricks coding agent with the model you choose.",
        "start_url": "./", "display": "standalone",
        "background_color": "#faf9f7", "theme_color": "#4b5bd6",
        "icons": [
            {"src": "assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, indent=2), encoding="utf-8")

    manifest = {
        "commit": commit,
        "built": built,
        "routes": written,
        "claims": len(claim_list),
        "excluded_batches": excluded,
        "screenshots": info["shots"],
    }
    (OUT / "build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


NOT_FOUND = """<section class="wide">
  <h1>404</h1>
  <p class="lede">That page is not here. Nothing was lost; the link was wrong.</p>
  <div class="cta-row"><a class="btn primary" href="./">Back to the home page</a></div>
  <div class="grid-3">
    <a class="card" href="tour/"><p class="card-title">Tour</p><p>Real screenshots of every screen.</p></a>
    <a class="card" href="tutorial/"><p class="card-title">Tutorial</p><p>The 30-minute setup.</p></a>
    <a class="card" href="evidence/"><p class="card-title">Evidence</p><p>Every score, with its denominator.</p></a>
    <a class="card" href="install/"><p class="card-title">Install</p><p>Deploy it to your workspace.</p></a>
    <a class="card" href="reference/"><p class="card-title">Reference</p><p>The docs and the specifications.</p></a>
    <a class="card" href="about/"><p class="card-title">About</p><p>Who built it, and why.</p></a>
  </div>
</section>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-stamp", action="store_true", help="freeze the commit and date (reproducibility)")
    args = ap.parse_args()
    m = build(stamp=not args.no_stamp)
    print(f"built {len(m['routes'])} routes into {OUT.relative_to(ROOT)}")
    print(f"  commit {m['commit']}, {m['built']}")
    print(f"  {m['claims']} claims, {m['screenshots']} screenshots")
    print(f"  {len(m['excluded_batches'])} batches excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
