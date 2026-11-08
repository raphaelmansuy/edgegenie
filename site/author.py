"""The author section: who built this, why, and where to reach him.

The project is one person's work, so the page says so. The shape follows the author block on
https://raphaelmansuy.github.io/edgepii/ — a portrait, a role, the reason the project exists, a book, the
other projects, and one call to action — because a reader who lands on `/about/` has the same question
here as there.

Every claim in this file is checkable: a public URL, a publisher's page, or a fact visible in this
repository. Nothing about the person is asserted that a reader cannot open in another tab ([E-30]).
"""

from __future__ import annotations

import html

LINKEDIN = "https://www.linkedin.com/in/raphaelmansuy/"
GITHUB_PROFILE = "https://github.com/raphaelmansuy"
REPO = "https://github.com/raphaelmansuy/opengenie"
BOOK = "https://www.oreilly.com/library/view/the-definitive-guide/9781837631919/"
FAVIKON = "https://www.favikon.com/blog/top-ai-experts-france"


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


PROJECTS = [
    {
        "name": "EdgeQuake",
        "url": "https://edgequake.com/",
        "image": "edgequake.jpg",
        "alt": "EdgeQuake knowledge graph view: 200 nodes and 840 edges over an AI research corpus.",
        "body": (
            "Graph-RAG in Rust: one binary, one Postgres, any LLM. It reads PDFs and text, builds a "
            "knowledge graph in PostgreSQL, and answers questions with sources."
        ),
    },
    {
        "name": "EdgeCrab",
        "url": "https://www.edgecrab.com/",
        "image": "edgecrab.jpg",
        "alt": "EdgeCrab illustration: a comic battle between EdgeCrab and a crab-like rival.",
        "body": (
            "A personal and coding agent in one native Rust binary, with a terminal interface and a "
            "reactive tool loop. It speaks to many model providers and messaging gateways."
        ),
    },
    {
        "name": "EdgeWhisper",
        "url": "https://edgewhisper.com/",
        "image": "edgewhisper.jpg",
        "alt": "EdgeWhisper banner: voice dictation, on-device AI for macOS.",
        "body": (
            "Voice dictation for macOS, powered by Voxtral from Mistral AI. It runs fully on the "
            "device, with no cloud round trip and no data collection."
        ),
    },
]


def section(prefix: str, *, commit: str, built: str) -> str:
    """The author page block. `prefix` is the relative path back to the site root."""

    projects = "".join(
        f"""<article class="project">
      <a class="project-media" href="{esc(p['url'])}" target="_blank" rel="noopener noreferrer" tabindex="-1">
        <img src="{prefix}assets/projects/{esc(p['image'])}" alt="{esc(p['alt'])}"
             width="800" height="500" loading="lazy" decoding="async" />
      </a>
      <h3><a href="{esc(p['url'])}" target="_blank" rel="noopener noreferrer">{esc(p['name'])}</a></h3>
      <p>{esc(p['body'])}</p>
    </article>"""
        for p in PROJECTS
    )

    return f"""<section class="author-section" aria-labelledby="author-name">
  <div class="author-card">
    <img class="portrait" src="{prefix}assets/author/raphael-mansuy.jpg"
         alt="Portrait of Raphael Mansuy, author of OpenGenie."
         width="132" height="132" loading="eager" decoding="async" />
    <div class="author-body">
      <p class="eyebrow">About the author</p>
      <h2 id="author-name">Raphael Mansuy</h2>
      <p class="author-meta">Author of OpenGenie &middot; data engineering and AI strategist</p>
      <p>
        Raphael has more than 20 years of global technology leadership experience. He works on
        democratising data management and AI, and helps organisations build data platforms that
        survive contact with production. His work covers resilient data infrastructure, machine
        learning systems, and coaching teams on practice. He leads a startup studio in Hong Kong and
        writes about AI and data strategy.
      </p>
      <p>
        <strong>Why OpenGenie exists.</strong> Databricks Genie Code is good, and it is metered and
        pinned to whatever model the workspace is allowed to use. The question here was narrow and
        testable: if the model is the largest lever on whether an agent finishes the work, who should
        choose it? He measured that question on eleven graded tasks in a live workspace, published
        every run, and then built the application the measurements implied &mdash; a Databricks App
        where the model is a control, the writes are fenced to a folder you name, and a claim of
        &ldquo;done&rdquo; is checked against the workspace rather than believed.
      </p>
      <p class="author-links">
        <a class="btn primary" href="{LINKEDIN}" target="_blank" rel="noopener noreferrer">Connect on LinkedIn</a>
        <a class="btn" href="{GITHUB_PROFILE}" target="_blank" rel="noopener noreferrer">GitHub profile</a>
        <a class="btn" href="{REPO}" target="_blank" rel="noopener noreferrer">Repository</a>
      </p>
    </div>
  </div>

  <div class="author-grid">
    <article class="author-panel">
      <h3 class="panel-title">Recognition</h3>
      <p>
        Favikon lists Raphael among the
        <a href="{FAVIKON}" target="_blank" rel="noopener noreferrer">Top 20 AI Experts in France</a>,
        citing his data and AI leadership, his work on scalable data platforms, and the startup studio
        he leads in Hong Kong.
      </p>
      <p class="source">Source: Favikon, <em>Top AI Experts in France</em>.</p>
    </article>

    <article class="author-panel book-panel">
      <a href="{BOOK}" target="_blank" rel="noopener noreferrer" tabindex="-1">
        <img src="{prefix}assets/book/definitive-guide-data-integration.jpg"
             alt="Cover of The Definitive Guide to Data Integration, co-authored by Raphael Mansuy."
             width="120" height="148" loading="lazy" decoding="async" />
      </a>
      <div>
        <h3 class="panel-title">The Definitive Guide to Data Integration</h3>
        <p class="author-meta">Packt, 2024</p>
        <p>
          <em>Unlock the power of data integration to efficiently manage, transform, and analyze
          data.</em> Co-authored with Pierre-Yves Bonnefoy, Emeric Chaize, Mehdi Tazi and Stephane
          Heckel.
        </p>
        <p class="author-links">
          <a class="btn" href="{BOOK}" target="_blank" rel="noopener noreferrer">Read it on O&rsquo;Reilly</a>
        </p>
      </div>
    </article>
  </div>

  <h3 class="author-projects-title">Other projects by Raphael</h3>
  <div class="project-grid">
    {projects}
  </div>

  <div class="cta-band">
    <p><strong>Running a Databricks estate?</strong> Tell him what Genie Code costs you, and what you
    would want a coding agent to prove before you trusted it.</p>
    <a class="btn primary" href="{LINKEDIN}" target="_blank" rel="noopener noreferrer">Connect on LinkedIn</a>
  </div>

  <p class="foot-note">This page was built from commit <code>{esc(commit)}</code> on {esc(built)}.
  The project is Apache-2.0 licensed.</p>
</section>"""


def jsonld() -> dict:
    """The author graph, so a crawler ties the software to a person."""
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Raphael Mansuy",
        "jobTitle": "Data engineering and AI strategist",
        "url": GITHUB_PROFILE,
        "sameAs": [LINKEDIN, GITHUB_PROFILE, REPO],
        "knowsAbout": [
            "Data engineering",
            "Data integration",
            "Artificial intelligence",
            "Databricks",
            "AI agents",
        ],
    }
