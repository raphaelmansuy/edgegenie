/* The site's entire JavaScript. Four jobs, no dependencies:
     1. set the theme before first paint (inline, in <head>, so there is no flash)
     2. the theme control
     3. the navigation menu below 860 px
     4. render Mermaid diagrams, if the page has any
   Everything else is CSS. With this file blocked the page still reads, navigates and links correctly
   (spec 008 [AX-9]), which is why nothing structural lives here. */

(function () {
  "use strict";

  /* ---------------------------------------------------------------- theme, before paint */
  // Also inlined in <head>; this copy exists so the file works if the site is embedded elsewhere.
  var KEY = "opengenie-theme";
  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function prefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function apply(choice) {
    var root = document.documentElement;
    if (choice === "light" || choice === "dark") {
      root.setAttribute("data-theme", choice);
    } else {
      root.removeAttribute("data-theme");
      root.setAttribute("data-theme", prefersDark() ? "dark" : "light");
    }
    root.setAttribute("data-theme-choice", choice || "system");
    document.querySelectorAll("[data-theme-choice-btn]").forEach(function (b) {
      var on = b.getAttribute("data-theme-choice-btn") === (choice || "system");
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  /* ---------------------------------------------------------------- navigation menu */
  function initMenu() {
    var btn = document.querySelector("[data-nav-toggle]");
    var nav = document.getElementById("site-nav");
    if (!btn || !nav) return;

    function open() {
      nav.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
      var first = nav.querySelector("a");
      if (first) first.focus();
    }
    function close(moveFocus) {
      if (!nav.classList.contains("is-open")) return;
      nav.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
      if (moveFocus) btn.focus();
    }
    function isOpen() { return nav.classList.contains("is-open"); }

    btn.addEventListener("click", function () {
      if (isOpen()) close(false); else open();
    });

    // One ordered meaning for Escape, the same discipline the app uses ([NAV-4]).
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || !isOpen()) return;
      e.stopPropagation();
      close(true);
    });

    // Tab stays inside an open menu: it is the only thing on screen below the header.
    nav.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || !isOpen()) return;
      var items = [btn].concat(Array.prototype.slice.call(nav.querySelectorAll("a")));
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    document.addEventListener("click", function (e) {
      if (!isOpen()) return;
      if (nav.contains(e.target) || btn.contains(e.target)) return;
      close(false);
    });

    // Above the breakpoint the menu is inline, so the open state must not linger.
    var mq = window.matchMedia("(min-width: 861px)");
    var onChange = function () { if (mq.matches) close(false); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  /* ---------------------------------------------------------------- contents rail */
  // Marks the section being read. This is the one enhancement that is worth a scroll listener: the rail
  // is a map, and a map without "you are here" is decoration.
  function initToc() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".toc a[href^='#']"));
    if (!links.length || !("IntersectionObserver" in window)) return;
    var targets = links
      .map(function (a) {
        var id = decodeURIComponent(a.getAttribute("href").slice(1));
        return document.getElementById(id);
      })
      .filter(Boolean);
    if (!targets.length) return;
    var seen = new Map();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { seen.set(en.target.id, en.isIntersecting ? en.boundingClientRect.top : 1e9); });
      var bestId = null, best = Infinity;
      seen.forEach(function (top, id) {
        if (top < best && top > -80) { best = top; bestId = id; }
      });
      if (!bestId) return;
      links.forEach(function (a) {
        var on = a.getAttribute("href") === "#" + bestId;
        if (on) a.setAttribute("aria-current", "true");
        else a.removeAttribute("aria-current");
      });
    }, { rootMargin: "-80px 0px -70% 0px", threshold: [0, 1] });
    targets.forEach(function (t) { io.observe(t); });
  }

  /* ---------------------------------------------------------------- mermaid */
  var THEMES = {
    dark: {
      background: "#1a1917", primaryColor: "#232642", primaryTextColor: "#f2f0ec",
      primaryBorderColor: "#3d4485", lineColor: "#8f8a80", secondaryColor: "#2a2825",
      tertiaryColor: "#201f1c", noteBkgColor: "#232642", noteTextColor: "#f2f0ec",
      noteBorderColor: "#3d4485", actorBkg: "#232642", actorBorder: "#3d4485",
      actorTextColor: "#f2f0ec", signalColor: "#c3bfb7", signalTextColor: "#f2f0ec",
      labelBoxBkgColor: "#232642", labelBoxBorderColor: "#3d4485", labelTextColor: "#f2f0ec",
      loopTextColor: "#f2f0ec", activationBkgColor: "#2a2825", activationBorderColor: "#45423c",
      sequenceNumberColor: "#14131a",
      xyChart: { plotColorPalette: "#8e9bf5, #e8955a, #6cc28e", backgroundColor: "#1a1917",
                 titleColor: "#f2f0ec", xAxisLabelColor: "#c3bfb7", yAxisLabelColor: "#c3bfb7",
                 xAxisTitleColor: "#c3bfb7", yAxisTitleColor: "#c3bfb7", xAxisLineColor: "#45423c",
                 yAxisLineColor: "#45423c", xAxisTickColor: "#45423c", yAxisTickColor: "#45423c" },
    },
    light: {
      background: "#ffffff", primaryColor: "#e9ebfb", primaryTextColor: "#1c1b19",
      primaryBorderColor: "#b6bdf0", lineColor: "#6b6760", secondaryColor: "#f6f5f2",
      tertiaryColor: "#faf9f7", noteBkgColor: "#e9ebfb", noteTextColor: "#1c1b19",
      noteBorderColor: "#b6bdf0", actorBkg: "#e9ebfb", actorBorder: "#b6bdf0",
      actorTextColor: "#1c1b19", signalColor: "#57544e", signalTextColor: "#1c1b19",
      labelBoxBkgColor: "#f6f5f2", labelBoxBorderColor: "#e9e7e2", labelTextColor: "#1c1b19",
      loopTextColor: "#1c1b19", activationBkgColor: "#f6f5f2", activationBorderColor: "#d9d6cf",
      sequenceNumberColor: "#ffffff",
      // a chart's series must be told apart at a glance: the site's blue, an orange, a green
      xyChart: { plotColorPalette: "#4b5bd6, #e07a3f, #2f9e62", backgroundColor: "#ffffff" },
    },
  };

  var MIN_SCALE = 0.75;  // Mermaid draws 16 px text; below this it is smaller than 12 px

  /* Mermaid renders to static SVG with the colours baked in, so a theme change has to re-render. The
     source is kept in a data attribute the first time, so re-rendering is not destructive. */
  function initMermaid() {
    var blocks = Array.prototype.slice.call(document.querySelectorAll("pre.mermaid"));
    if (!blocks.length) return;
    blocks.forEach(function (b) {
      // A diagram in a repository document may carry its own `%%{init: …}%%` block with light-theme
      // colours. The site's theme has to win, or a dark page gets a white diagram, so the directive is
      // removed for rendering while the original source stays in the <pre> for a reader with JS off.
      var src = b.textContent.replace(/^\s*%%\{init:[\s\S]*?\}%%\s*\n?/, "");
      b.setAttribute("data-src", src);
    });
    var script = document.createElement("script");
    script.src = (document.documentElement.getAttribute("data-root") || "") + "assets/mermaid.min.js";
    script.onload = function () {
      if (!window.mermaid) return;
      window.__renderDiagrams = function () { return render(blocks); };
      render(blocks);
      // the right direction depends on the column's width, so a real resize draws them again
      var lastWidth = window.innerWidth, timer = 0;
      window.addEventListener("resize", function () {
        if (Math.abs(window.innerWidth - lastWidth) < 80) return;
        lastWidth = window.innerWidth;
        clearTimeout(timer);
        timer = setTimeout(window.__renderDiagrams, 200);
      });
    };
    script.onerror = function () {
      // Offline or blocked: the source stays in the <pre>, which is readable.
      blocks.forEach(function (b) { b.classList.add("diagram-failed"); });
    };
    document.head.appendChild(script);
  }

  function render(blocks) {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      fontFamily: getComputedStyle(document.body).fontFamily,
      themeVariables: dark ? THEMES.dark : THEMES.light,
      flowchart: { useMaxWidth: true, htmlLabels: true },
      sequence: { useMaxWidth: true },
    });
    /* One diagram at a time, each with a unique id. `mermaid.run` is asynchronous, and starting it for
       every block at once let two renders share Mermaid's scratch element: one diagram drew into
       another and a third came out empty (seen in tests/sites/e2e screenshots of /reference/doc-safety/). */
    var round = (window.__diagramRound = (window.__diagramRound || 0) + 1);
    var chain = Promise.resolve();
    blocks.forEach(function (block, i) {
      chain = chain.then(function () {
        var src = block.getAttribute("data-src");
        var id = "og-diagram-" + round + "-" + i;
        // A wide left-to-right flowchart fitted into a column is a strip of unreadable text. Draw it as
        // written; if it would land below a readable scale, draw the same graph top-to-bottom; and if
        // even that does not fit, keep the readable scale and let the frame scroll sideways.
        function scaleOf(svgText) {
          var m = /viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+)/.exec(svgText);
          return m ? block.clientWidth / parseFloat(m[1]) : 1;
        }
        return window.mermaid.render(id, src).then(function (out) {
          var vertical = src.replace(/^(\s*(?:flowchart|graph))\s+(LR|RL)\b/m, "$1 TD");
          if (scaleOf(out.svg) >= MIN_SCALE || vertical === src) return out;
          return window.mermaid.render(id + "-td", vertical).then(function (td) {
            return scaleOf(td.svg) > scaleOf(out.svg) ? td : out;
          });
        }).then(function (out) {
          block.innerHTML = out.svg;
          block.setAttribute("data-processed", "true");
          var svg = block.querySelector("svg");
          var vb = svg && svg.viewBox && svg.viewBox.baseVal;
          var figure = block.closest("figure.diagram");
          block.style.textAlign = "";
          if (figure) {
            figure.classList.remove("is-zoomable");
            var old = figure.querySelector(".diagram-open");
            if (old) old.remove();
          }
          if (dark && svg) readableLabels(svg);
          if (vb && vb.width && block.clientWidth / vb.width < MIN_SCALE) {
            if (window.innerWidth > 860) {
              // Room to scroll: keep the text readable and let the frame scroll sideways. A centred
              // child wider than its box overflows to the LEFT too, where no scroll can reach it.
              svg.style.maxWidth = "none";
              svg.style.width = Math.round(vb.width * MIN_SCALE) + "px";
              block.style.textAlign = "left";
            } else if (figure) {
              // On a phone a scroller shows a corner of the picture. Show all of it, and offer it
              // at full size on its own, the way the screenshots are offered.
              figure.classList.add("is-zoomable");
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "diagram-open";
              btn.textContent = "Open full size \u2197";
              btn.addEventListener("click", function () {
                var url = URL.createObjectURL(new Blob([svg.outerHTML], { type: "image/svg+xml" }));
                window.open(url, "_blank", "noopener");
              });
              figure.appendChild(btn);
            }
          }
          block.classList.remove("diagram-failed");
        }).catch(function () {
          block.textContent = src;
          block.classList.add("diagram-failed");
        });
      });
    });
    return chain.then(markScrollable);
  }

  /* A document's own classDef paints a node pastel; the dark theme paints its label near-white. Where
     the two meet, the label vanishes. Give any label on a light fill dark ink. */
  function readableLabels(svg) {
    svg.querySelectorAll("g.node, g.cluster").forEach(function (node) {
      var shape = node.querySelector("rect, polygon, circle, ellipse, path");
      if (!shape) return;
      var m = getComputedStyle(shape).fill.match(/[\d.]+/g);
      if (!m || m.length < 3) return;
      var lum = (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
      if (lum < 0.6) return;
      node.querySelectorAll(".nodeLabel, .cluster-label, text, span, p, div").forEach(function (el) {
        el.style.color = "#1c1b19";
        el.style.fill = "#1c1b19";
      });
    });
  }

  /* ---------------------------------------------------------------- overflow hints */
  // A shadow at the edge of a table or code block says "there is more"; it must only say so when true.
  function markScrollable() {
    document.querySelectorAll(".table-wrap, .code pre, figure.diagram").forEach(function (el) {
      el.classList.toggle("is-scrollable", el.scrollWidth > el.clientWidth + 1);
    });
  }

  /* ---------------------------------------------------------------- boot */
  function boot() {
    var choice = stored() || "system";
    apply(choice);
    document.querySelectorAll("[data-theme-choice-btn]").forEach(function (b) {
      b.addEventListener("click", function () {
        var next = b.getAttribute("data-theme-choice-btn");
        try { localStorage.setItem(KEY, next); } catch (e) {}
        apply(next);
        // A diagram's colours are baked into its SVG, so switching the theme has to re-render it.
        if (window.__renderDiagrams) window.__renderDiagrams();
      });
    });

    initMenu();
    initToc();
    initMermaid();
    markScrollable();
    var t = 0;
    window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(markScrollable, 120); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
