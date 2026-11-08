# 05. Diagrams (Mermaid)

[Index](README.md) · prev: [04 Wireframes](04-wireframes.md) · next: [06 Lenses](06-lenses.md)

Mermaid for the things that change over time or have cardinality: build order, states, data model,
sequences. ASCII for geometry, in [04](04-wireframes.md). That split is deliberate — a sequence diagram
drawn in ASCII is unreadable, and a pixel grid drawn in Mermaid is wrong.

Every diagram below is parsed by the repository's own verifier before it ships:

```bash
NODE_PATH=/tmp/mmd/node_modules node apps/coding-agent/web/scripts/verify-spec-mermaid.mjs \
  specs/008-github-page
```

---

## 1. The build pipeline, in order

The order is the requirement: nothing is rendered before its inputs are resolved, and nothing is
deployed before it passes the checker.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','clusterBkg':'#F8FAFC','clusterBorder':'#CBD5E1'}}}%%
flowchart TD
    subgraph INPUT["Inputs, all in this repository"]
        RES["exams/results/*.json<br/>174 run files"]:::blue
        DOC["docs/*.md + specs/*/README.md<br/>109 documents"]:::blue
        PNG["286 screenshot PNGs"]:::blue
        SEED["site/content/*.md<br/>seven pages of prose"]:::blue
    end
    subgraph DERIVE["Derivation, no I/O"]
        CL["claims.py<br/>aggregate + round once"]:::yellow
        MD["mdrender.py<br/>markdown to HTML"]:::yellow
        TX["author.py<br/>the about section"]:::yellow
    end
    subgraph EMIT["Emit"]
        BL["build.py<br/>one HTML file per route"]:::green
        AS["static assets + shots<br/>copied, never duplicated"]:::green
    end
    subgraph GATE["Gate, blocks the deploy"]
        CK["check.py<br/>links · anchors · alt · claims · markup"]:::pink
        SH["shots.py<br/>Playwright, every route, four widths"]:::pink
    end
    OUT["site/dist → GitHub Pages"]:::purple

    RES --> CL
    DOC --> MD
    SEED --> MD
    CL --> BL
    MD --> BL
    TX --> BL
    PNG --> AS
    BL --> AS
    AS --> CK
    CK --> SH
    SH --> OUT
    CK -.->|"fails: nothing is published"| OUT
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
```

---

## 2. What a claim is made of, and where each part comes from

The data model of the one entity that matters (`[CPT-1]`).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
erDiagram
    CLAIM ||--o{ RUN : "is computed from"
    CLAIM ||--|| CAVEAT : "carries exactly one"
    CLAIM ||--o{ SOURCE_PATH : "cites"
    RUN ||--o{ MISSION_SCORE : "contains"
    RUN {
        string batch "v4_gptoss"
        string variant "V0 to V6"
        string model "gemini-3.8-flash"
        string agent "opencode or copilot"
        int total "sum of mission scores"
        int tokens "measured, never priced"
    }
    MISSION_SCORE {
        string mission "M1 to M8 or X1 to X3"
        int score "points earned"
        int of "points achievable"
    }
    CLAIM {
        string id "CL-1 to CL-8"
        string statement "one sentence, falsifiable"
        int value "percent, rounded once"
        int numerator
        int denominator
        int runs "how many runs back it"
    }
    CAVEAT {
        string text "what it does not prove"
        string limit "sample size or spread"
    }
    SOURCE_PATH {
        string path "exams/results/v5_gemini/X1...json"
    }
```

---

## 3. The claim's lifecycle, from result file to rendered card

This is a state machine over *the build*, not over the page: a claim that cannot be derived must not
reach the HTML (`[CPT-4]`).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    [*] --> Discovered: glob exams/results/*/*.json
    Discovered --> Excluded: batch starts with "_" or is in SKIP
    Discovered --> Aggregated: run is a first trial
    Aggregated --> Rounded: value = round(100 * earned / achievable)
    Rounded --> Rendered: every declared source path exists
    Rounded --> Broken: a declared source path is missing
    Broken --> [*]: check.py fails the build, path named
    Rendered --> Checked: prose contains no unclaimed percentage
    Checked --> Published
    Checked --> Rejected: an unclaimed percentage was found
    Rejected --> [*]: build stops
    Published --> [*]
    Excluded --> [*]
```

---

## 4. A reader's first ninety seconds

The journey the page is designed around ([01](01-five-whys.md)). Every arrow must be one click.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','actorBkg':'#E8F0FE','actorBorder':'#A8C0E8','noteBkgColor':'#E6F4EA','noteBorderColor':'#A8D5B5'}}}%%
sequenceDiagram
    autonumber
    participant R as Reader
    participant H as Home
    participant T as Tour
    participant E as Evidence
    participant G as GitHub

    R->>H: "Genie Code is expensive" — arrives from a link
    H-->>R: "16 models, your choice. Writes only where you say."
    H-->>R: one screenshot at 1440 px, captioned
    alt convinced, wants to see it work
        R->>T: read the tour
        T-->>R: 17 screenshots, four widths, both themes
        R->>G: clone, read INSTALL
    else sceptical, wants the proof
        R->>E: read the evidence
        E-->>R: every claim with denominator, caveat and command
        R->>G: re-run exams/make_tables.py
    end
    Note over R,G: the same numbers appear in both paths,<br/>because one function produced them
```

---

## 5. The navigation state machine

`[NAV-3]`, `[NAV-4]`. Two independent machines that must not interfere: the menu is about width, the
theme is about preference.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    direction LR
    state "Navigation" as NAV {
        [*] --> Wide
        Wide --> Wide: viewport ≥ 860px
        Wide --> Collapsed: viewport < 860px
        Collapsed --> Open: Enter or Space on the button
        Open --> Collapsed: Escape, focus back to the button
        Open --> Collapsed: click outside, focus stays
        Open --> Collapsed: choose an item, navigates
        Collapsed --> Wide: viewport ≥ 860px, closes silently
    }
    state "Theme" as TH {
        [*] --> System
        System --> Light: press
        Light --> Dark: press
        Dark --> System: press
        System --> System: OS scheme changes
    }
    note right of NAV
        The menu never opens by itself:
        a resize closes it and moves nothing.
    end note
    note right of TH
        data-theme is written to html before
        first paint, so there is no flash.
    end note
```

---

## 6. A page render, in sequence

Where a broken link is caught, and why it is caught at build time rather than by a reader.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','actorBkg':'#E8F0FE','actorBorder':'#A8C0E8'}}}%%
sequenceDiagram
    participant B as build.py
    participant C as claims.py
    participant M as mdrender.py
    participant F as site/dist
    participant K as check.py

    B->>C: claims()
    C-->>B: {CL-1..CL-8} with value, n, of, runs, caveat
    B->>M: render(docs/tutorial.md)
    M-->>B: html + {heading -> slug} map
    B->>B: page(route, title, description, body, toc)
    B->>F: write index.html, tour/index.html, …
    B->>F: write sitemap.xml, robots.txt, 404.html
    K->>F: read every file
    K->>K: parse markup, resolve every href and src on disk
    K->>K: one h1, alt text, canonical, JSON-LD parses
    K->>K: every {{CL-n}} resolved, no bare percentage in prose
    alt a problem
        K-->>B: exit 1 with file and reason
    else clean
        K-->>B: exit 0, deploy proceeds
    end
```

---

## 7. The screenshot inspection loop

`[PG-14]`, and the reason [11](11-outcome.md) can say a picture was looked at.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart LR
    A["shots.py<br/>7 routes × 4 widths × 2 themes"]:::blue --> B["write specs/008-github-page/e2e/<scene>/*.png"]:::green
    B --> C{"open every image<br/>and look at it"}:::yellow
    C -->|"defect"| D["name it, fix the CSS or the copy,<br/>re-run only that scene"]:::pink
    D --> B
    C -->|"correct"| E["keep the audit JSON:<br/>widths, CLS, contrast, overflow"]:::purple
    E --> F["11 records what the pictures found<br/>that the assertions did not"]:::purple
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
```

---

## 8. Deployment, and what happens when it is wrong

`[NAV-1]` is the reason the same artefact can be served from three places.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart TD
    P["push to main"]:::blue --> W["workflow: site.yml"]
    W --> I["python 3.12<br/>pip install pygments"]:::yellow
    I --> BLD["python site/build.py"]:::yellow
    BLD --> CHK{"python site/check.py"}:::pink
    CHK -->|"fail"| STOP["job fails, Pages keeps the previous version"]:::pink
    CHK -->|"pass"| UP["upload-pages-artifact"]:::green
    UP --> DEP["deploy-pages"]:::green
    DEP --> URL["raphaelmansuy.github.io/opengenie/"]:::purple
    URL --> Q{"served from a subpath:<br/>do relative links still resolve?"}:::yellow
    Q -->|"yes, all links are relative"| OK["done"]:::green
    Q -->|"no"| FIX["the rule in check.py that resolves<br/>every href on disk, added"]:::pink
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
```

---

## 9. Module dependencies, and why there is no cycle

The SOLID rule for a static site is the same as for an app: dependencies point one way, and the domain
knows nothing about the output (`[D2](07-architecture.md#d2-dependencies-point-one-way)`).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart BT
    build["build.py<br/>composition root"]:::purple
    pages["pages.py<br/>route table"]:::green
    claims["claims.py<br/>pure"]:::green
    mdrender["mdrender.py<br/>pure"]:::green
    author["author.py<br/>pure"]:::green
    check["check.py<br/>independent verifier"]:::pink

    build --> pages
    build --> claims
    build --> mdrender
    build --> author
    pages --> claims
    pages --> mdrender
    check -.->|"reads only site/dist, imports nothing"| build
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
```

`check.py` deliberately imports nothing from the build: a verifier that shares code with the thing it
verifies cannot catch that code's mistakes.
