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
    },
  };

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
      window.__renderDiagrams = function () { render(blocks); };
      render(blocks);
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
    blocks.forEach(function (block) {
      // restore the source, then let Mermaid replace it again
      block.removeAttribute("data-processed");
      block.innerHTML = block.getAttribute("data-src");
      try {
        window.mermaid.run({ nodes: [block] });
      } catch (e) {
        block.classList.add("diagram-failed");
      }
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
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
