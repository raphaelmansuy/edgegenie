/** App shell: navigator, mission/document work area and assistant dock.
 * Spec 011 projects the active session into a mission overview when no document is selected.
 * The existing stream owns state; the dock and selected-turn Activity reuse the conversation.
 * One Focus binds open documents and attached context. Generated results refresh open documents
 * and remain one explicit click away without replacing the mission the reader is reviewing.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type CatalogueResponse, type SessionSummary } from "./api/client";
import { prettyId } from "./domain/models";
import { EmptyState, Inspector } from "./components/Chrome";
import { wroteElsewhere } from "./domain/artifacts";
import { MissionScreen } from "./components/MissionScreen";
import { nameOf, recentDocs, rememberDoc } from "./domain/recent";
import { WroteElsewhere } from "./components/WroteElsewhere";
import { SkipLinks } from "./components/SkipLinks";
import { EdgeHandles, handlesFor } from "./components/EdgeHandles";
import { LogoBadge, Wordmark } from "./components/Logo";
import { parentOf } from "./domain/docs";
import { peekOf } from "./domain/peek";
import { SessionPeek } from "./components/SessionPeek";
import { AssistantDock, InlineApproval } from "./components/AssistantDock";
import { ModelControl } from "./components/ModelControl";
import { ProviderSettings } from "./components/ProviderSettings";
import { LayoutMenu } from "./components/LayoutMenu";
import { Palette, PaletteActions } from "./components/Palette";
import { DocTabs } from "./components/DocTabs";
import { Separator } from "./components/Separator";
import { SessionList } from "./components/SessionList";
import { AccountMenu } from "./components/AccountMenu";
import { ShortcutSheet } from "./components/ShortcutSheet";
import { CatalogTree } from "./components/CatalogTree";
import { FilesPane } from "./components/FilesPane";
import { Composer } from "./components/Composer";
import { OpenDoc, WorkspaceLinks } from "./components/DocContext";
import type { Workspace } from "./domain/links";
import { NotebookViewer, TableViewer } from "./components/Viewer";
import type { WsNode } from "./components/WorkspaceTree";
import type { Candidate } from "./domain/fuzzy";
import { caps, display } from "./domain/keys";
import { useHotkeys } from "./hooks/useHotkeys";
import { useLayout } from "./hooks/useLayout";
import { useTheme } from "./hooks/useTheme";
import { ThemeSwitch } from "./components/ThemeSwitch";
import {
  ChevronLeft, PanelLeft, PanelRight, Search,
} from "./components/Icons";
import { ALL_FOUR_MIN, bounds, columns, DOCK_FOCUS_MIN, drawerWidth, modeFor, takesColumn, type RailTab } from "./domain/layout";
import {
  ACTIONS, asAttachment, docForNode, makeDoc, tablesWritten, touched, type Action, type Doc,
} from "./domain/docs";
import { focusFor, NO_FOCUS, sameFocus, withCell, withoutDoc, type Focus } from "./domain/focus";
import { canDecide, canSend } from "./domain/compose";
import { escapeTarget } from "./domain/keys";
import { useScrollHandoff } from "./hooks/useScrollHandoff";
import { attachmentsFor, autoAttachment } from "./domain/binding";
import { searchRoot as computeSearchRoot } from "./domain/searchroot";
import type { Attachment } from "./domain/events";
import type { Suggestion } from "./domain/dock";
import { useSessionStream } from "./hooks/useSessionStream";
import { useRoute } from "./hooks/useRoute";
import { EMPTY_ROUTE, linkTo, type Route } from "./domain/route";
import { copyText } from "./domain/clipboard";
import { readWorkingSet, saveWorkingSet } from "./domain/workingset";
import { afterClose, docTabId, moveTab } from "./domain/tabs";

type Rail = "sessions" | "files" | "catalog";
const CHAT = "chat";

const dedupe = (items: Attachment[]) => {
  const seen = new Set<string>();
  return items.filter((a) => (seen.has(`${a.kind}:${a.ref}`) ? false : (seen.add(`${a.kind}:${a.ref}`), true)));
};

export function App() {
  const [savedSessions, setSessions] = useState<SessionSummary[]>([]);
  /** True until the first `/api/sessions` answers. Until then the list knows nothing, and saying
   *  "No conversations yet" would be a statement it cannot support — it flashed for 90 ms on every
   *  load and shifted everything below it by 34 px (measured CLS 0.0064). */
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [user, setUser] = useState("");
  const [catalogue, setCatalogue] = useState<CatalogueResponse | null>(null);
  const [defaultModel, setDefaultModel] = useState("");
  const [scratch, setScratch] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [demo, setDemo] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [folder, setFolder] = useState("");
  const [model, setModel] = useState("");
  const [notice, setNotice] = useState("");
  /** A short confirmation that must be visible whatever is on screen (the empty state's `notice` is not). */
  const [toast, setToast] = useState("");
  useEffect(() => { if (toast) { const id = window.setTimeout(() => setToast(""), 2600); return () => window.clearTimeout(id); } }, [toast]);

  const [docs, setDocs] = useState<Doc[]>([]);
  const closedDocs = useRef<{ doc: Doc; index: number }[]>([]);
  const [closedCount, setClosedCount] = useState(0);
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(() => new Set());
  const documentDirty = useCallback((doc: Doc, dirty: boolean) => {
    setDirtyIds((cur) => {
      if (cur.has(doc.id) === dirty) return cur;
      const next = new Set(cur);
      if (dirty) next.add(doc.id); else next.delete(doc.id);
      return next;
    });
  }, []);
  const [view, setView] = useState<string>(CHAT);
  const [focus, setFocus] = useState<Focus>(NO_FOCUS);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [treeRev, setTreeRev] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  useEffect(() => {
    const open = () => setKeysOpen(true);
    window.addEventListener("opengenie:shortcuts", open); // OPEN_SHORTCUTS in domain/cellkeys.ts
    return () => window.removeEventListener("opengenie:shortcuts", open);
  }, []);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"providers" | "models">("providers");
  const [modelOpen, setModelOpen] = useState(0);
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const { layout, setWidth, resetOne, resetAll, toggle, setRailTab: setLayoutTab } = useLayout(viewport);
  const theme = useTheme();
  const { railVisible: railShown, inspectorVisible: inspShown, assistantVisible: dockShown, railTab: rail } = layout;
  const mode = modeFor(viewport);
  const narrow = mode === "narrow";
  const overlay = mode !== "wide";
  /* The dock takes a column as soon as one fits: a column shrinks the editor, an overlay covers it —
     and an overlay was covering cell run controls at 1180. The rule is `takesColumn` in layout.ts; this
     used to be a hardcoded `viewport >= 1136`, which drifted by the two 1px gaps and became a second
     source of truth. At 1200 and 1136 the two disagreed: `columns()` emitted three tracks and App drew
     four children, so the dock wrapped to a second grid row (measured: rows=2, dock y=52 under the
     rail). Calling the rule is the only way they cannot disagree. */
  const dockColumn = dockShown && takesColumn("assistant", layout, viewport);
  /* Where the inspector can be DRAWN — and therefore what `⌘I`, the toolbar toggle and the palette row
     must all act on.
   *
   * A column needs `wide` AND room for the dock as well (`ALL_FOUR_MIN`, 1476 px). At 1440 with the
   * dock open neither holds, so `⌘I` used to set a flag that rendered nothing: `aria-pressed` said
   * true, the screen did not change, and the next press hid it. When it cannot be a column it is a
   * drawer. `inspectorOnScreen` is what the user can SEE, and it is the only value a toggle may use. */
  /** The LEFT overlay slot: the navigator. The inspector used to share it, so opening one closed the
   *  other — and opening the ASSISTANT cleared the slot, closing the inspector with it. They are
   *  panels about different things and now have different state (`ZN-9`). */
  const [drawer, setDrawer] = useState<"rail" | null>(null);
  /* The inspector is a COLUMN when there is room, a DRAWER when there is not — and "room" changes while
     it is open (opening the conversation can take the fourth column away). Keying the drawer off a
     one-shot click meant that when the room disappeared the inspector unmounted and stayed unmounted:
     it was "on" per the toggle and absent on screen. So the placement is derived, and the drawer flag
     only records that the user wants it while it cannot be a column. */
  const inspectorPlacement: "column" | "drawer" | "none" =
    !inspShown ? "none"
      : (mode === "wide" && (!dockShown || viewport >= ALL_FOUR_MIN)) ? "column"
        : "drawer";
  /* And when it is a drawer it is either a grid CHILD (the preferred form: it pushes the work instead
     of covering it) or a fixed OVERLAY, when a track would cost the centre its `CENTRE_MIN`. The
     decision is `drawerWidth`'s — the same function `columns()` uses — so a track and a child are
     created together or not at all. Deriving them separately is what let four children land in a
     three-track grid, which wrapped the dock onto a second row beneath the navigator. */
  const inspectorInGrid = inspectorPlacement === "drawer" && drawerWidth(layout, viewport) !== null;
  /* The inspector used to require a session, which left it with no restore path at all in the state
     this audit was opened for: a notebook open with "No session", the inspector hidden, and every
     control for it disabled. It has real content without a session too — the fence, the tools, the
     audit log — so it opens whenever it is asked for, and says so when it is empty (`ZN-7`). */
  const wantsInspector = inspShown;
  /** The assistant's own slot. It is NOT an alternative to the navigator: browsing files and asking
   *  about one is the whole workflow, and at 760 px the single slot made them mutually exclusive —
   *  opening the navigator closed the conversation (and vice versa), which the scorecard found by
   *  scoring 84% instead of 100% for that reason alone. */
  const [dockDrawer, setDockDrawer] = useState(false);
  const dockOverlay = dockShown && !dockColumn;
  /* `dockShown` is the user's intent; `dockOnScreen` is whether the conversation is actually painted
     (a column, or an open drawer). The centre's composer must key off the second: keying off the
     first left a mid-width window with NO message box at all — the dock "shown" but not drawn, and
     the centre's composer hidden to avoid a duplicate. */
  const dockRendered = dockColumn || (dockOverlay && dockDrawer);
  /** The dock was opened in a window that has room for it beside the work but not beside the
   *  navigator too: it takes a column and the navigator steps aside (see DOCK_FOCUS_MIN). */
  const focusDock = dockOverlay && dockDrawer && viewport >= DOCK_FOCUS_MIN;
  /* `inspectorOnScreen` must be what is DRAWN, and `focusDock` is a state in which nothing but the
     work and the conversation is drawn (it takes the centre column and the navigator steps aside).
     Omitting `focusDock` made the toggle lie: with the dock focused, the markup below suppressed the
     inspector while the button still read "Hide the inspector" with `aria-pressed="true"` — the exact
     "on and invisible" defect this file warns about, on a screen the e2e exercises. Pressing it then
     flipped a flag with no visible effect, and nothing on screen could bring the inspector back,
     because `inspectorPlacement` was "none". Declared after `focusDock`, which it depends on. */
  const inspectorOnScreen = wantsInspector && !focusDock && inspectorPlacement !== "none";
  const dockOnScreen = dockRendered;
  const setRail = useCallback((r: RailTab) => { setLayoutTab(r); }, [setLayoutTab]);

  useEffect(() => {
    const onResize = () => setViewport(window.innerWidth);
    window.addEventListener("resize", onResize, { passive: true });
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useEffect(() => {
    setDrawer(null); setDockDrawer(false);
    // A return link on a phone must open the conversation, not an inspector over its controls.
    if (mode === "narrow") toggle("inspector", false);
  }, [mode, toggle]);
  const composerBox = useRef<HTMLTextAreaElement | null>(null);
  const dockComposer = useRef<HTMLTextAreaElement | null>(null);

  const { session, conn, error, send, stop, restore, retry: retryConnection, setSession } = useSessionStream(active);
  // The active stream is fresher than the visibility-aware history poll.
  const sessions = savedSessions.map((s) => s.id !== session.id || session.status === "provisioning" ? s : {
    ...s, status: session.status, requiresResume: session.requiresResume,
    execution: { persistence: s.execution?.persistence ?? "memory" as const,
      maxRunSeconds: s.execution?.maxRunSeconds ?? 21600,
      state: session.status === "streaming" ? "running" : session.turns.at(-1)?.status ?? "ready",
      queued: session.turns.filter((t) => t.status === "queued").length,
      pendingApprovals: session.approvals.filter((a) => !a.outcome).length },
  });


  const refresh = useCallback(async () => {
    const [s, m, me] = await Promise.all([
      api.sessions(), api.models(), api.me().catch(() => ({ scratch: "", demo: false, user: "", workspace: undefined }))]);
    setSessions(s.sessions);
    setSessionsLoaded(true);
    setCatalogue(m);
    setDefaultModel(m.default);
    setScratch(me.scratch ?? "");
    setUser(me.user ?? "");
    setWorkspace(me.workspace?.host ? me.workspace : null);
    setDemo(Boolean(me.demo));
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  // Inactive sessions still run. Refresh history without refetching the model catalogue.
  useEffect(() => {
    let alive = true;
    const poll = () => {
      if (document.visibilityState !== "visible") return;
      void api.sessions().then((r) => { if (alive) setSessions(r.sessions); }).catch(() => {});
    };
    const timer = window.setInterval(poll, 5000);
    document.addEventListener("visibilitychange", poll);
    window.addEventListener("online", poll);
    return () => { alive = false; window.clearInterval(timer);
      document.removeEventListener("visibilitychange", poll); window.removeEventListener("online", poll); };
  }, []);
  useEffect(() => { if (!folder && scratch) setFolder(scratch); }, [scratch, folder]);
  /* The assistant's visibility at first paint.
     Wide: it is a column and it is shown — that is the whole point of this shell.
     Mid/narrow: it is a DRAWER, and a drawer that opens by itself covers the workspace. An earlier
     version opened it on the first paint so the feature was discoverable, and the very first thing a
     user did at 1180 px was try to press Run in the notebook and hit the drawer instead (found by the
     scorecard: the click was intercepted by a suggestion button inside the overlay).
     Discoverability does not justify covering the work. The toggle, ⌘J and the tooltip carry it
     instead, and the drawer still persists once the user opens it. */
  useEffect(() => {
    if (dockColumn) setDockDrawer(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);
  useEffect(() => { if (!model && defaultModel) setModel(defaultModel); }, [defaultModel, model]);

  // -- documents and focus ----------------------------------------------------------------
  /** The navigator as a drawer is a chooser: once you have chosen, it gets out of the way. Left open it
   *  covers the very thing you just opened (found at 760 px: the notebook was under the file list). */
  const dismissRailDrawer = useCallback(() => {
    if ((narrow || focusDock) && drawer === "rail") { setDrawer(null); toggle("rail", false); }
  }, [narrow, focusDock, drawer, toggle]);
  const [recent, setRecent] = useState(() => recentDocs());
  const openDoc = useCallback((doc: Doc) => {
    setDocs((cur) => (cur.some((d) => d.id === doc.id) ? cur : [...cur, doc]));
    // What the home screen offers as "pick up where you left off". A table is not a path in the
    // workspace, so it is remembered under its own kind.
    setRecent(rememberDoc({ path: doc.ref, name: doc.name || nameOf(doc.kind, doc.ref), kind: doc.kind }));
    setView(doc.id);
    // Opening a document IS the binding (006 FX-1): the dock is now about it, and its cell is cleared.
    setFocus(focusFor(doc));
    dismissRailDrawer();
  }, [dismissRailDrawer]);
  const selectTab = (id: string) => {
    setView(id);
    if (id === CHAT) { setFocus(withoutDoc()); return; }
    const d = docs.find((x) => x.id === id);
    setFocus((f) => (d ? (sameFocus(f, focusFor(d)) ? f : focusFor(d)) : withoutDoc()));
  };
  const closeDocuments = (ids: string[]) => {
    const removed = new Set(ids.filter((id) => docs.some((d) => d.id === id)));
    if (!removed.size) return;
    const nextView = afterClose(docs, view, removed);
    const focusedTab = document.activeElement?.closest<HTMLElement>("[data-tab-id]")?.dataset.tabId;
    const restoreFocus = removed.has(view) || (focusedTab && removed.has(focusedTab));
    const entries = docs.flatMap((doc, index) => removed.has(doc.id) ? [{ doc, index }] : []);
    closedDocs.current = [...closedDocs.current.filter((entry) => !removed.has(entry.doc.id)), ...entries].slice(-20);
    setClosedCount(closedDocs.current.length);
    setDocs((cur) => cur.filter((d) => !removed.has(d.id)));
    setDirtyIds((cur) => new Set([...cur].filter((id) => !removed.has(id))));
    if (view !== nextView) selectTab(nextView);
    if (restoreFocus) requestAnimationFrame(() => {
      (document.getElementById(docTabId(nextView)) ?? document.getElementById("doc-panel"))?.focus({ preventScroll: true });
    });
  };
  const closeDoc = (id: string) => closeDocuments([id]);
  const moveDocument = (id: string, index: number) => setDocs((cur) => moveTab(cur, id, index));
  const reopenDocument = () => {
    const entry = closedDocs.current.pop();
    setClosedCount(closedDocs.current.length);
    if (!entry) return;
    openDoc(entry.doc);
    setDocs((cur) => moveTab(cur, entry.doc.id, entry.index));
    requestAnimationFrame(() => document.getElementById(docTabId(entry.doc.id))?.focus({ preventScroll: true }));
  };
  /** A cell in the open document: the `ask` button on a cell, or a click in the gutter. */
  const focusCell = useCallback((doc: Doc, cell: number) => {
    setFocus(withCell(focusFor(doc), cell));
    setAttachments([]);
    if (!dockShown) toggle("assistant", true);
    if (overlay) setDockDrawer(true);
    requestAnimationFrame(() => dockComposer.current?.focus());
  }, [dockShown, overlay, toggle]);

  const viewDoc = docs.find((d) => d.id === view) ?? null;

  const workspaceScope = user ? `${window.location.origin}|${workspace?.host ?? ""}|${user}` : null;
  const [restoredScope, setRestoredScope] = useState<string | null>(null);
  useEffect(() => {
    if (!workspaceScope || restoredScope === workspaceScope) return;
    const saved = readWorkingSet(workspaceScope);
    const changingAccount = Boolean(restoredScope && restoredScope !== workspaceScope);
    setDocs((current) => [...saved.docs, ...(changingAccount ? [] : current.filter((d) => !saved.docs.some((s) => s.id === d.id)))]);
    if (changingAccount) { setActive(null); setView(CHAT); setFocus(withoutDoc()); }
    closedDocs.current = saved.closed;
    setClosedCount(saved.closed.length);
    // A pasted document/session/settings route outranks the previous selection.
    if ((!window.location.hash || changingAccount) && saved.active !== CHAT) {
      const doc = saved.docs.find((d) => d.id === saved.active);
      if (doc) { setView(doc.id); setFocus(focusFor(doc)); }
    }
    setRestoredScope(workspaceScope);
  }, [workspaceScope, restoredScope]);
  useEffect(() => {
    if (workspaceScope && restoredScope === workspaceScope) saveWorkingSet(workspaceScope, docs, view, closedDocs.current);
  }, [workspaceScope, restoredScope, docs, view, closedCount]);

  // -- deep links: the address bar says what is on screen, and what it says can be opened (domain/route.ts)
  const route = useMemo<Route>(() => {
    if (settingsOpen) return { ...EMPTY_ROUTE, settings: settingsTab };
    if (viewDoc) {
      return { ...EMPTY_ROUTE, doc: { kind: viewDoc.kind, ref: viewDoc.ref },
               cell: viewDoc.kind === "notebook" && focus.docId === viewDoc.id ? focus.cell : null };
    }
    if (view === CHAT && active) return { ...EMPTY_ROUTE, session: active };
    return EMPTY_ROUTE;
  }, [settingsOpen, settingsTab, viewDoc, view, active, focus.docId, focus.cell]);
  const applyRoute = useCallback((r: Route) => {
    if (r.settings) { setSettingsTab(r.settings); setSettingsOpen(true); return; }
    setSettingsOpen(false);
    if (r.doc) {
      const d = makeDoc(r.doc.kind, r.doc.ref);
      openDoc(d);
      if (r.cell) { setFocus(withCell(focusFor(d), r.cell)); setAttachments([]); }
      return;
    }
    if (r.session) { setActive(r.session); setView(CHAT); setFocus(withoutDoc()); return; }
    setActive(null); setView(CHAT); setFocus(withoutDoc());
  }, [openDoc]);
  useRoute(route, applyRoute);
  const copyLink = useCallback(async (r: Route = route) => {
    const ok = await copyText(linkTo(r, window.location));
    setToast(ok ? "Link copied" : "Could not copy; use the address bar");
  }, [route]);

  PaletteActions.onOpenTable = (ref: string) => openDoc(makeDoc("table", ref));
  PaletteActions.onOpenFile = (kind: string, path: string) => {
    const d = docForNode(kind as never, path);
    if (d) openDoc(d);
  };
  const addContext = useCallback((a: Attachment) => setAttachments((cur) => dedupe([...cur, a])), []);

  const seen = useRef(new Set<string>());
  useEffect(() => {
    const written: Doc[] = [];
    for (const t of session.turns) for (const c of t.tools) {
      if (c.status !== "completed" || seen.current.has(c.callId)) continue;
      seen.current.add(c.callId);
      const wroteTables = tablesWritten(c.name, c.args);
      if (wroteTables.length) {
        // A table open on screen is stale after the agent changes it: refresh it, same as a notebook.
        setDocs((cur) => cur.map((d) => (d.kind === "table" && wroteTables.some((t) => d.ref.toLowerCase() === t || d.ref.toLowerCase().endsWith(`.${t}`))
          ? { ...d, rev: d.rev + 1 } : d)));
      }
      const hit = touched(c.name, c.args, c.summary);
      if (hit?.mutates) written.push(hit.doc);
    }
    if (!written.length) return;
    setTreeRev((n) => n + 1);
    setDocs((cur) => cur.map((d) => (written.some((w) => w.id === d.id) ? { ...d, rev: d.rev + 1 } : d)));
    // Spec 011: refresh open results, but keep the reader on their mission until they choose Open.
  }, [session.turns]);
  useEffect(() => { seen.current = new Set(); }, [active]);

  // -- sending ----------------------------------------------------------------------------
  const starting = useRef(false);
  const start = async (prompt: string, ctx: Attachment[] = []) => {
    if (starting.current) return;
    starting.current = true;
    try {
      // The page may be used before `/api/me` has answered (a slow start): the folder is then still
      // empty, and sending it empty is a 422 the user cannot act on. Ask once, here, instead.
      const where = folder || scratch || (await api.me()).scratch;
      const created = await api.create(where, model || defaultModel || undefined);
      setActive(created.id);
      await api.send(created.id, prompt, `${created.id}:1`, ctx);
      await refresh();
    } finally {
      starting.current = false;
    }
  };

  /** One send path for both composers: the centre's and the dock's. */
  const message = async (text: string, extra: Attachment[] = []) => {
    const auto = focus.doc ? autoAttachment(focus) : null;
    const ctx = dedupe([...(auto ? [auto] : []), ...attachments, ...extra]);
    setAttachments([]);
    /* Sending a message is a request to SEE the answer, wherever it was typed from. This used to be
       `if (viewDoc && !dockOnScreen)` — gated on a document being open — so on the home screen at a
       mid width the message went off, a session was created on the server, the composer emptied, and
       the conversation stayed an unopened drawer behind an edge handle. Measured: at 900 px, 0 turns
       on screen with a `ready` session in the API. The condition was never about documents; it was
       about the dock being an overlay rather than a column, which `reveal()` already handles. */
    if (!dockOnScreen) reveal();
    if (!active) await start(text, ctx);
    else await send(text, ctx);
  };

  const ask = (action: Action, doc: Doc) => {
    if (!dockOnScreen) reveal();
    void (async () => {
      if (!active) await start(ACTIONS[action].prompt, [asAttachment(doc)]);
      else await message(ACTIONS[action].prompt, [asAttachment(doc)]);
    })();
  };

  /** An instruction typed on a cell (or the gap between two). The binding is the cell, not the notebook:
   *  `attachmentsFor` makes a cell supersede its document, so the context is sent once. The
   *  conversation opens in the dock so the user watches the work where Stop and approvals live. */
  const promptCell = (doc: Doc, p: { cell: number; text: string }) => {
    const next = p.cell > 0 ? withCell(focusFor(doc), p.cell) : focusFor(doc);
    setFocus(next);
    setAttachments([]);
    if (!dockShown) toggle("assistant", true);
    if (overlay) setDockDrawer(true);
    const ctx = attachmentsFor(next);
    void (async () => {
      if (!active) await start(p.text, ctx);
      else await send(p.text, ctx);
    })();
  };

  /** A dock suggestion: a prompt with the binding already chosen. */
  const fromSuggestion = (s: Suggestion) => {
    const auto = focus.doc ? autoAttachment(focus) : null;
    void message(s.prompt, auto ? [auto] : []);
  };

  /** Delete is archive on the server. Leaving the open conversation returns to the start screen. */
  const deleteSession = async (s: { id: string }) => {
    await api.archive(s.id);
    if (s.id === active) { setActive(null); setView(CHAT); setFocus(withoutDoc()); setAttachments([]); }
    await refresh();
  };

  const decide = async (approvalId: string, outcome: "allow_once" | "allow_session" | "deny") => {
    if (!active) return;
    const a = session.approvals.find((x) => x.approvalId === approvalId);
    const pick = a?.options.find((o) => o.kind === (outcome === "deny" ? "reject_once" : outcome === "allow_session" ? "allow_always" : "allow_once"));
    await api.decide(active, approvalId, outcome, pick?.optionId);
    void refresh();
  };

  const useFolder = (path: string) => {
    setFolder(path);
    setActive(null);
    setView(CHAT);
    setNotice(`The next session will work in ${path}`);
  };
  useEffect(() => { if (notice) { const id = window.setTimeout(() => setNotice(""), 6000); return () => window.clearTimeout(id); } }, [notice]);

  const newSession = useCallback(() => {
    setActive(null);
    setView(CHAT);
    setFocus(withoutDoc());
    setAttachments([]);
    requestAnimationFrame(() => dockComposer.current?.focus());
  }, []);

  const focusComposer = useCallback(() => {
    const el = dockOnScreen ? dockComposer.current : composerBox.current;
    (el ?? composerBox.current)?.focus();
  }, [dockOnScreen]);

  const openRail = useCallback((on: boolean) => {
    if (on && inspectorOnScreen && dockColumn && viewport - layout.railWidth - layout.inspectorWidth - layout.assistantWidth - 3 < 640) toggle("inspector", false);
    toggle("rail", on);
    setDrawer(on && (narrow || focusDock) ? "rail" : null);
  }, [toggle, narrow, focusDock, inspectorOnScreen, dockColumn, viewport, layout]);
  const openInspector = useCallback((on: boolean) => {
    if (on && railShown && dockColumn && viewport - layout.railWidth - layout.inspectorWidth - layout.assistantWidth - 3 < 640) toggle("rail", false);
    toggle("inspector", on);
    /* Focus mode draws the work and the conversation and nothing else, so asking for the inspector
       there would set a flag that cannot be honoured — a press with no visible effect, which is the
       control lying in the other direction. Opening the inspector closes the focused dock instead:
       one deliberate choice replaces another, and the panel that was asked for actually appears. */
    if (on && focusDock) { setDockDrawer(false); toggle("assistant", false); }
  }, [toggle, focusDock, railShown, dockColumn, viewport, layout]);
  const openDock = useCallback((on: boolean) => {
    toggle("assistant", on);
    setDockDrawer(on && mode !== "wide");
    // Deliberately does NOT touch inspDrawer: on the right, the conversation and the inspector are
    // siblings. Clearing a shared slot here is what closed the inspector when the dock opened.
  }, [toggle, mode]);
  const toggleDock = useCallback(() => {
    /* One key, one meaning: show or hide the assistant — acting on what is ON SCREEN.
       Where the dock is a column, the column's presence is what the key toggles. Where it is a
       drawer, the drawer starts closed while the *intent* is still true, so keying the toggle off the
       intent made ⌘J a no-op: it "hid" a panel that was not visible. */
    if (dockColumn) { openDock(false); return; }
    if (mode !== "wide" && dockDrawer) { setDockDrawer(false); return; }
    if (!dockShown) toggle("assistant", true);
    setDockDrawer(true);
  }, [mode, dockColumn, dockDrawer, dockShown, openDock, toggle]);
  /** Make the conversation visible. A request sent from a document's own composer, or from an Ask menu,
   *  is a request to WATCH the answer: a drawer that stays shut leaves the user looking at an
   *  unchanged notebook with no sign anything started (the bug that prompted this). A column needs
   *  nothing; a drawer is opened. */
  const reveal = useCallback(() => {
    if (!dockShown) toggle("assistant", true);
    if (!dockColumn) setDockDrawer(true);
  }, [dockShown, dockColumn, toggle]);
  const setRailAndOpen = useCallback((r: RailTab) => { setLayoutTab(r); openRail(true); },
    [setLayoutTab, openRail]);

  const searchRoot = computeSearchRoot(focus, session.folder || folder, scratch);
  /* Whether the active model can consume an image — the catalogue's DECLARED property, not a guess from
     the model's name. A name is not evidence, and a substring match here either blocked a working feature
     or shipped a picture to a blind model (spec 009 [CAP-2], [D7]). The server checks the same field again
     before it stores a byte. */
  const activeModel = active ? session.model : (model || defaultModel);
  const modelSeesImages = useMemo(() => {
    const hit = catalogue?.available?.find((m) => m.id === activeModel);
    return Boolean(hit?.seesImages);
  }, [catalogue, activeModel]);
  useEffect(() => { PaletteActions.root = searchRoot; }, [searchRoot]);

  const paletteItems = useMemo<Candidate[]>(() => {
    const items: Candidate[] = [];
    const add = (id: string, title: string, group: string, run: () => void, hint?: string, weight = 0) =>
      items.push({ id, title, group, run, hint, weight });

    add("act:new", "New conversation", "Actions", newSession, display("mod+shift+n"), 5);
    add("act:keys", "Keyboard shortcuts", "Actions", () => setKeysOpen(true), display("mod+slash"));
    add("act:providers", "Providers and keys", "Actions", () => { setSettingsTab("providers"); setSettingsOpen(true); }, display("mod+comma"), 2);
    add("act:models", "Configure models", "Actions", () => { setSettingsTab("models"); setSettingsOpen(true); }, undefined, 2);
    add("act:link", route.cell ? "Copy link to this cell" : "Copy link to this view", "Actions", () => void copyLink(), undefined, 1);
    add("act:model", "Change the model", "Actions", () => setModelOpen((n) => n + 1),
      display("mod+shift+m"), 4);
    add("act:dock", dockShown ? "Hide the assistant" : "Show the assistant", "Panels",
      toggleDock, display("mod+j"), 2);
    add("act:reset", "Reset layout", "Actions", resetAll, "panels, widths and tab", 1);
    add("act:refresh", "Refresh sessions and models", "Actions", () => void refresh());
    for (const r of ["sessions", "files", "catalog"] as Rail[]) {
      const key = r === "sessions" ? "mod+1" : r === "files" ? "mod+2" : "mod+3";
      add(`rail:${r}`, `${r[0].toUpperCase()}${r.slice(1)} panel`, "Panels",
        () => setRailAndOpen(r), display(key), 2);
    }
    add("panel:rail", railShown ? "Hide the left panel" : "Show the left panel", "Panels",
      () => openRail(!railShown), display("mod+b"));
    add("panel:insp", inspectorOnScreen ? "Hide the inspector" : "Show the inspector", "Panels",
      () => openInspector(!inspectorOnScreen), display("mod+i"));

    add("tab:chat", "Chat", "Open", () => selectTab(CHAT), undefined, 1);
    if (closedCount) add("tab:reopen", "Reopen closed tab", "Actions", reopenDocument, display("mod+shift+t"));

    // Actions on what is in context. A palette that only navigates is a menu; this is the useful part.
    const bound = focus.doc;
    if (bound) {
      const doc = docs.find((d) => d.id === focus.docId) ?? makeDoc(bound.kind, bound.ref);
      add("act:attach", `Add ${bound.name} to the message`, "Actions",
        () => addContext(asAttachment(doc)), undefined, 2);
      for (const a of ["explain", "fix", "document", "optimize"] as Action[]) {
        if (!(ACTIONS[a] && doc)) continue;
        add(`act:${a}:${doc.id}`, `${ACTIONS[a].label} ${bound.name}`, "Actions", () => ask(a, doc), a, 3);
      }
    }
    for (const d of docs) {
      add(`doc:${d.id}`, d.name, d.kind === "table" ? "Tables" : "Files", () => selectTab(d.id), d.ref, 1);
    }
    for (const s of sessions.slice(0, 40)) {
      const title = s.title === "New session" ? s.id.slice(0, 8) : s.title;
      items.push({
        id: `session:${s.id}`, title, group: "Sessions", hint: s.folder,
        keywords: s.id, weight: 3,
        run: () => { setActive(s.id); setView(CHAT); },
      });
    }
    return items;
  }, [docs, sessions, railShown, inspShown, newSession, refresh, focus, addContext, ask, openRail,
      openInspector, resetAll, toggleDock, dockShown, closedCount, reopenDocument]);

  const busy = session.status === "streaming";
  /* ONE answer to "may this be sent", shared by both composers and by the approval buttons.
     It cannot see the connection: losing the stream means the answer will not ARRIVE yet, not that
     the question is refused (specs/012 01 §P1). This replaces three expressions that disagreed. */
  const sendDecision = canSend({ status: session.status, requiresResume: session.requiresResume });
  /** Drawn as a column, or as the right-hand drawer. Never "on" and invisible.
   *
   *  In focus only the work and the conversation are drawn, so the inspector is not a column there
   *  either — the grid below and the markup that follows must agree, which is the whole point. */
  const inspectorColumn = wantsInspector && !focusDock && inspectorPlacement === "column";
  const inspectorDrawer = wantsInspector && !focusDock && inspectorPlacement === "drawer";
  const railDrawn = railShown && !narrow && !focusDock ? true : (railShown && (narrow || focusDock) && drawer === "rail");
  /** What the grid is laid out from.
   *
   *  `inspectorVisible` is `inspectorColumn`, NOT a second opinion. It used to be
   *  `Boolean(active) && session.turns !== undefined && inspShown` — the old rule that the inspector
   *  needs a session — while the markup below drew it unconditionally. On the home screen those
   *  disagreed: `columns()` emitted three tracks and the DOM had four children, so the dock wrapped to
   *  a second implicit row and rendered UNDER the navigator, 276 px wide instead of 380 (measured at
   *  1480 and 1600: dock x=0, y=497, w=276). A grid whose track count is not its child count is not a
   *  layout, it is an accident that happens to look arranged. One predicate, used twice. */
  const gridLayout = focusDock
    ? { ...layout, railVisible: false, inspectorVisible: false }
    : { ...layout, inspectorVisible: inspectorColumn };

  /* Handlers are keyed by SHORTCUT ID, not by combo: `resolve()` maps the press to an id, so a chord
     can never have two owners and the sheet's ids are the binding's ids by construction (007 KB-2,
     KB-5). Adding a chord is adding a row to the registry and, if it needs app state, one line here. */
  const handlers = useMemo(() => {
    const go = (r: RailTab) => () => setRailAndOpen(r);
    const cycle = (step: number) => () => {
      const ids = [CHAT, ...docs.map((d) => d.id)];
      const at = ids.indexOf(view);
      selectTab(ids[(at + step + ids.length) % ids.length]);
    };
    return {
      palette: () => setPaletteOpen((v) => !v),
      help: () => { setKeysOpen((v) => !v); },
      providers: () => setSettingsOpen((v) => !v),
      changeModel: () => setModelOpen((n) => n + 1),
      toggleDock,
      newSession,
      focusComposer,
      railSessions: go("sessions"),
      railFiles: go("files"),
      railCatalog: go("catalog"),
      cycleTheme: theme.cycle,
      toggleRail: () => openRail(!railDrawn),
      /* ONE implementation, shared with the toolbar button and the palette: a chord that sets the
         intent without drawing the panel is the bug this line replaces. */
      toggleInspector: () => openInspector(!inspectorOnScreen),
      searchFiles: () => { setRailAndOpen("files"); focusComposer(); },
      nextTab: cycle(1),
      prevTab: cycle(-1),
      reopenTab: reopenDocument,
      closeTab: () => {
        if (view === CHAT) return false;      // never close someone's only view by accident
        closeDoc(view);
        return true;
      },
      /* Escape, resolved by the ONE function that documents its order (specs/012 [KB-A]).
       *
       * This replaces a chain of five `if`s. That chain happened to be right, and it was unverifiable:
       * its behaviour was a function of a `useMemo` dependency list that includes `layout`, `mode` and
       * `narrow`, so Escape's precedence varied with window width and no test covered the wiring.
       * `escapeTarget()` was exported, documented, unit-tested and cited by a comment in
       * `useHotkeys` — and called only from its own tests (specs/012 [F4]).
       *
       * A `switch` over the union is exhaustive: adding an `EscapeTarget` is now a compile error
       * rather than a silent fall-through. */
      stop: () => {
        const target = escapeTarget({
          dialog: settingsOpen || paletteOpen || keysOpen,
          popover: modelOpen > 0,
          drawer: dockDrawer || inspectorDrawer || Boolean(drawer),
          editing: false,
          running: session.status === "streaming",
          composerFocused: document.activeElement === dockComposer.current
            || document.activeElement === composerBox.current,
        });
        switch (target) {
          case "dialog": setSettingsOpen(false); setPaletteOpen(false); setKeysOpen(false); return true;
          case "popover": setModelOpen(0); return true;
          case "drawer":
            if (dockDrawer) { setDockDrawer(false); toggle("assistant", false); }
            else if (inspectorDrawer) { toggle("inspector", false); }
            else { setDrawer(null); toggle("rail", false); }
            return true;
          case "edit": return false;                  // the editor owns its own Escape
          case "stop-agent": void stop(); return true;
          case "nothing": return false;               // never steal the browser's meaning [KB-D]
        }
      },
    };
  }, [docs, view, paletteOpen, keysOpen, settingsOpen, newSession, focusComposer, drawer, dockDrawer,
      narrow, mode, layout, toggle, theme.cycle, toggleDock, selectTab, setRailAndOpen, closeDoc,
      openInspector, inspectorOnScreen, reopenDocument, openRail, railDrawn]);

  /* The context the arbiter needs, read live so the listener is registered once (007 KB-2). */
  const hotkeyContext = useMemo(() => ({
    dialogOpen: () => settingsOpen || paletteOpen || keysOpen || Boolean(document.querySelector('[role="dialog"][aria-modal="true"]')),
    inCell: () => Boolean(document.activeElement?.closest?.(".cell-block")),
    running: () => Boolean(session.status === "streaming"),
  }), [settingsOpen, paletteOpen, keysOpen, session.status]);
  useHotkeys(handlers, hotkeyContext);
  /* One delegated wheel listener: a contained scroller hands its remainder to the nearest scrollable
     ancestor, so a wheel at the edge of a cell's output keeps reading (specs/012 [SC-1]). */
  useScrollHandoff();
  /* A write that did not land in the document on screen. The centre must say so: a screen that does
     not change while the dock reports a write reads as "the refresh is broken" (it happened on the
     deployed app, with the agent correctly writing a copy outside the repo). */
  const elsewhere = useMemo(
    () => (viewDoc ? wroteElsewhere(session.turns, viewDoc.id) : null),
    [session.turns, viewDoc],
  );
  /** The banner is about one write, and the user may dismiss it. Keyed by path, so the next write
   *  shows a new one rather than staying silent for the rest of the session. */
  const [elsewhereSeen, setElsewhereSeen] = useState<string | null>(null);
  /* Opening a document must not replay its history: whatever the conversation wrote before you opened
     it is not news. Only a write that lands while you are looking is. So the baseline is taken when
     the document changes, and the banner needs a turn id newer than that. */
  const elsewhereBase = useRef<string | null>(null);
  const elsewhereDoc = elsewhere?.docs[0] ?? null;
  const elsewhereTurn = elsewhere?.at ?? "";
  useEffect(() => {
    // A different document: forget both the baseline and the dismissal.
    elsewhereBase.current = elsewhere?.at ?? null;
    setElsewhereSeen(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewDoc?.id]);
  const showElsewhere = Boolean(
    elsewhereDoc && elsewhereTurn && elsewhereTurn !== elsewhereBase.current && elsewhereSeen !== elsewhereTurn,
  );
  const peek = useMemo(() => peekOf(session), [session]);
  const pending = session.approvals.find((a) => !a.outcome);
  const turns = session.turns;
  const selectedRef = viewDoc?.ref ?? null;
  const viewerActions = useMemo(() => ({
    onDirtyChange: documentDirty,
    onAsk: ask,
    onAttach: (d: Doc) => addContext(asAttachment(d)),
    onAskCell: (d: Doc, cell: number) => focusCell(d, cell),
    onPromptCell: promptCell,
    onCopyLink: (d: Doc, cell?: number) =>
      void copyLink({ ...EMPTY_ROUTE, doc: { kind: d.kind, ref: d.ref }, cell: cell ?? null }),
    linkedCell: viewDoc && focus.docId === viewDoc.id ? focus.cell : null,
    live: busy,
    editing: {
      folder: session.folder || folder || "",
      sessionId: active,
      theme: theme.effective,
    },
  }), [ask, addContext, focusCell, promptCell, copyLink, viewDoc, focus.docId, focus.cell, busy, session.folder, folder, active, theme.effective, documentDirty]);

  const modelControl = (variant: "chip" | "inline") => (
    <ModelControl
      catalogue={catalogue}
      current={active ? session.model : model || defaultModel}
      variant={variant}
      openRequest={modelOpen}
      onChoose={async (id) => {
        if (!active) { setModel(id); return; }
        const r = await api.setModel(active, id);
        setSession((s) => ({ ...s, model: r.current }));
        void refresh();
      }}
      onAddKey={() => setSettingsOpen(true)}
      onRefresh={() => void refresh()}
    />
  );

  /** The navigator's body, shared by its in-grid form and its drawer form (one definition, not two). */
  const railBody = (
    <>
      <button className="rail-collapse" onClick={() => openRail(false)}
        title="Hide this panel (⌘B)" aria-label="Hide the left panel"><ChevronLeft size={15} /></button>
      {!narrow && (
        <Separator zone="rail" width={layout.railWidth} {...bounds("rail", layout, viewport)}
          label="Resize the navigator"
          onResize={(px) => setWidth("rail", px)} onReset={() => resetOne("rail")} />
      )}
      <div className="rail-tabs" role="tablist" aria-label="Navigator">
        {(["sessions", "files", "catalog"] as RailTab[]).map((r) => (
          <button key={r} id={`rail-tab-${r}`} className="rail-tab" role="tab" aria-selected={rail === r}
            aria-controls={`rail-panel-${r}`} tabIndex={rail === r ? 0 : -1}
            onClick={() => setRail(r)}
            onKeyDown={(e) => {
              const order = ["sessions", "files", "catalog"] as RailTab[];
              const at = order.indexOf(rail);
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                e.preventDefault();
                const next = order[(at + (e.key === "ArrowRight" ? 1 : -1) + order.length) % order.length];
                setRail(next);
                requestAnimationFrame(() => document.getElementById(`rail-tab-${next}`)?.focus());
              }
            }}>
            {r === "sessions" ? "Sessions" : r === "files" ? "Files" : "Catalog"}
          </button>
        ))}
      </div>
      <div id={`rail-panel-${rail}`} role="tabpanel" aria-labelledby={`rail-tab-${rail}`} className="rail-panel">
        {rail === "sessions" && (
          <>
            <div className="rail-head">
              <span className="rail-title">Recent</span>
              <button className="btn" onClick={newSession}>+ New</button>
            </div>
            <SessionList sessions={sessions} loaded={sessionsLoaded} activeId={active}
              onOpen={(x) => { setActive(x.id); setView(CHAT); setFocus(withoutDoc()); dismissRailDrawer(); }}
              onDelete={deleteSession} />
          </>
        )}
        {rail === "files" && (
          <FilesPane selected={selectedRef} revision={treeRev}
            onOpenFile={(n: WsNode) => { const d = docForNode(n.kind, n.path); if (d) openDoc(d); }}
            onAttach={addContext} onUseFolder={useFolder} />
        )}
        {rail === "catalog" && (
          <div className="rail-tree">
            <CatalogTree selected={selectedRef} onAttach={addContext} onOpenTable={(ref) => openDoc(makeDoc("table", ref))} />
          </div>
        )}
      </div>
    </>
  );

  const dockNode = (extra = "") => (
    <AssistantDock
      focus={focus}
      session={session}
      hasSession={Boolean(active)}
      running={busy}
      conn={conn}
      error={error}
      onRetryConnection={retryConnection}
      onSend={(text, mine) => message(text, mine)}
      onStop={stop}
      onRestore={restore}
      onSuggestion={fromSuggestion}
      onApprove={(a, outcome) => decide(a.approvalId, outcome)}
      onRetry={() => void message(lastPrompt(turns))}
      onNewSession={newSession}
      onHide={() => openDock(false)}
      onAttach={addContext}
      onRemoveAttachment={(a) => setAttachments((cur) => cur.filter((x) => x !== a))}
      attachments={attachments}
      openDocs={docs}
      searchRoot={searchRoot}
      sessionId={active}
      modelSeesImages={modelSeesImages}
      modelName={prettyId(activeModel ?? "")}
      onOpenDoc={(d) => selectTab(d.id)}
      overlay={overlay}
      className={extra}
      edge={extra ? (
        <Separator zone="assistant" width={layout.assistantWidth} {...bounds("assistant", gridLayout, viewport)}
          label="Resize the assistant"
          onResize={(px) => setWidth("assistant", px)} onReset={() => resetOne("assistant")} />
      ) : null}
      catalogue={catalogue}
      onAddKey={() => setSettingsOpen(true)}
      onRefreshModels={() => void refresh()}
      onChooseModel={async (id) => {
        if (!active) { setModel(id); return; }
        const r = await api.setModel(active, id);
        setSession((s) => ({ ...s, model: r.current }));
        void refresh();
      }}
      currentModel={active ? session.model : model || defaultModel}
      lastTurnModel={turns.at(-1)?.model}
      composerRef={dockComposer}
      sessions={sessions}
      activeId={active}
      onOpenSession={(x) => { setActive(x.id); setView(CHAT); setFocus(withoutDoc()); }}
      onDeleteSession={deleteSession}
      modelSlot={modelControl("inline")}
      placeholder={focus.doc ? `Ask about ${focus.doc.name}…` : undefined}
    />
  );

  return (
    <WorkspaceLinks.Provider value={workspace}>
      <OpenDoc.Provider value={openDoc}>
        {/* `--dock-w` lives on `.app` because a drawer is rendered as a SIBLING of `.layout`, not inside
            it. It is the dock's own width, so the inspector drawer can open to its left instead of on
            top of it: the facts must never cover the conversation they describe (007 ZN-2). */}
        <div className="app" style={{ "--dock-w": dockColumn ? `${layout.assistantWidth}px` : "0px" } as React.CSSProperties}>
          <header className="topbar">
            <SkipLinks />
            <h1 className="brand"><LogoBadge size={21} tone="accent" /> <Wordmark /></h1>
            <span className="meta">
              {modelControl("chip")}
              {active && (
                <button className={`pill session-chip ${peek.state} ${session.status}`} onClick={dockOnScreen ? focusComposer : reveal}
                  title={`${session.title || "This conversation"} — ${dockOnScreen ? "message the assistant" : "show the conversation"}`}
                  aria-label={`Conversation: ${peek.headline}`}>
                  <span className="session-chip-dot" aria-hidden />
                  {peek.state === "working" ? "working" : peek.state === "waiting" ? "needs you"
                    : peek.state === "failed" ? "stopped" : peek.state === "idle" ? "starting" : "ready"}
                </button>
              )}
              <button className="search-trigger" onClick={() => setPaletteOpen(true)}
                aria-label={`Search or run a command (${display("mod+k")})`} title={`Search or run a command — ${display("mod+k")}`}>
                <Search size={14} />
                <span className="search-trigger-label">Search or run a command</span>
                <span className="kbd-hint">{caps("mod+k").map((c) => <kbd key={c}>{c}</kbd>)}</span>
              </button>
              <button className="btn ghost shell-toggle" aria-pressed={railDrawn}
                onClick={() => openRail(!railDrawn)}
                aria-label={railDrawn ? "Hide the navigator" : "Show the navigator"}
                title={`${railDrawn ? "Hide" : "Show"} the navigator (${display("mod+b")})`}>
                <PanelLeft size={16} />
              </button>
              {/* Pressed means "the assistant is ON SCREEN", not "the user once said they wanted it".
                  It used to reflect the intent, so at narrow widths the button showed as active while
                  the drawer was closed — a control stating something untrue. */}
              <button className="btn ghost shell-toggle" aria-pressed={dockOnScreen}
                onClick={toggleDock}
                aria-label={dockOnScreen ? "Hide the assistant" : "Show the assistant"}
                title={`${dockOnScreen ? "Hide" : "Show"} the assistant (${display("mod+j")})`}>
                <PanelRight size={16} />
              </button>
              <button className="btn ghost shell-toggle" aria-pressed={inspectorOnScreen}
                onClick={() => openInspector(!inspectorOnScreen)}
                aria-label={inspectorOnScreen ? "Hide the inspector" : "Show the inspector"}
                title={`${inspectorOnScreen ? "Hide" : "Show"} the inspector (${display("mod+i")})`}>
                <ChevronLeft size={16} className="flip" />
              </button>
              <ThemeSwitch pref={theme.pref} onChoose={theme.choose} title={theme.title} />
              <LayoutMenu railVisible={railDrawn} dockVisible={dockOnScreen} inspectorVisible={inspectorOnScreen}
                onToggleDock={toggleDock} onToggleRail={() => openRail(!railDrawn)} onToggleInspector={() => openInspector(!inspectorOnScreen)}
                onReset={resetAll} onKeys={() => setKeysOpen(true)} onRefresh={() => void refresh()}
                onFocus={() => { toggle("rail", false); toggle("assistant", false); toggle("inspector", false); setDrawer(null); setDockDrawer(false); }} />
            </span>
            {/* Outside `.meta`: that cluster clips its overflow so it can shrink, and a popover inside it is cut off. */}
            <AccountMenu user={user} host={workspace?.host ?? null} folder={folder || scratch} demo={demo}
              onProviders={() => setSettingsOpen(true)} onKeys={() => setKeysOpen(true)} />
          </header>

          <div className="layout"
            style={{ "--layout-columns": columns(gridLayout, viewport, focusDock, inspectorDrawer) } as React.CSSProperties}>
            {railShown && !narrow && !focusDock && (
              <nav className="pane rail" aria-label="Navigator">
                {railBody}
              </nav>
            )}

            <main className="pane main">
              {active && docs.length > 0 && <button type="button" className="mission-return" aria-current={view === CHAT ? "page" : undefined}
                onClick={() => selectTab(CHAT)}>Mission overview <span>{session.title || "Current session"}</span></button>}
              {docs.length > 0 && (
                <DocTabs docs={docs} active={view} dirtyIds={dirtyIds} onSelect={selectTab} onClose={closeDoc}
                  onMove={moveDocument} onCloseMany={closeDocuments} onReopen={reopenDocument} canReopen={closedCount > 0} />
              )}

              {/* Where a hidden panel WOULD be (007 ZN-7). The top-bar toggles always worked; this is
                  what makes them findable: a handle on the edge the panel slides out from. */}
              <EdgeHandles handles={handlesFor({
                dockHidden: !dockOnScreen,
                inspectorHidden: !inspectorOnScreen,
                railHidden: !railDrawn,
                onDock: () => toggleDock(),
                onInspector: () => openInspector(true),
                onRail: () => openRail(true),
              })} />
              <div id="doc-panel" tabIndex={-1} role={viewDoc ? "tabpanel" : "region"}
                aria-labelledby={viewDoc ? docTabId(view) : undefined} aria-label={viewDoc ? undefined : active ? "Mission workspace" : "Home"}
                className="doc-panel">
              {/* Spec 011: the centre is an open document, the active mission or the start screen.
                  A hidden dock leaves the mission and its selected-turn Activity available. */}
              {viewDoc && showElsewhere && elsewhereDoc && (
                <WroteElsewhere
                  name={elsewhereDoc.name}
                  folder={parentOf(elsewhereDoc.ref)}
                  onOpen={() => { setElsewhereSeen(elsewhereTurn); openDoc(elsewhereDoc); }}
                  onDismiss={() => setElsewhereSeen(elsewhereTurn)}
                />
              )}
              {viewDoc ? (
                viewDoc.kind === "table"
                  ? <TableViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
                  : <NotebookViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
              ) : active ? (
                <MissionScreen key={active} session={session} conn={conn} dockVisible={dockOnScreen} error={error}
                  onOpen={openDoc} onConversation={() => { reveal(); requestAnimationFrame(() => dockComposer.current?.focus()); }}
                  onStop={stop} onRestore={restore} />
              ) : (
                /* Everything else — no document open — shows the start screen. It used to be the
                   `else` of `!dockOnScreen`, so a window where the dock was on screen but nothing was
                   open rendered an EMPTY canvas: a white page with a composer, which is what the
                   760 px screenshot showed. The centre must always have something to say. */
                <EmptyState catalogue={catalogue} folder={folder} onFolder={setFolder} model={model}
                  onModel={setModel} onAddKey={() => setSettingsOpen(true)}
                  demo={demo} notice={notice} user={user}
                  onStart={(p) => start(p, attachments).then(() => setAttachments([]))}
                  onOpenSearch={() => setPaletteOpen(true)}
                  onOpenCatalog={() => setRailAndOpen("catalog")}
                  onAskAssistant={focusComposer}
                  recent={recent}
                  onOpenRecent={(path, kind) => openDoc(makeDoc(kind, path))} />
              )}
              </div>

              {!dockOnScreen && (
                <>
              {active && viewDoc && (
                <SessionPeek session={session} onOpen={reveal} onStop={stop} />
              )}
              {!active && (
                <p className="composer-note" aria-live="off">
                  {(folder || scratch) ? (
                    <>
                      {viewDoc ? "New session" : "Session"} in <code>{folder || scratch}</code> —{" "}
                      <strong>the agent can write only there</strong>.
                    </>
                  ) : (
                    <span className="composer-note-pending">Preparing your scratch folder…</span>
                  )}
                </p>
              )}
              {/* Approvals need a WRITABLE session, not a live stream: deciding one is a POST.
                  `conn !== "live"` here was specs/012 [F3] — the control disabled by the symptom. */}
              {pending && <InlineApproval approval={pending} disabled={!canDecide({ status: session.status, requiresResume: session.requiresResume })}
                onDecide={(a, outcome) => decide(a.approvalId, outcome)} />}
              <Composer compact
                inputRef={composerBox}
                blockedReason={sendDecision.canSend ? null : sendDecision.reason} busy={busy} onSend={message} onStop={stop}
                attachments={attachments} auto={viewDoc ? asAttachment(viewDoc) : null}
                onAdd={addContext} onRemove={(a) => setAttachments((cur) => cur.filter((x) => x !== a))}
                openDocs={docs}
                searchRoot={searchRoot}
                sessionId={active}
                modelSeesImages={modelSeesImages}
                modelName={prettyId(activeModel ?? "")}
                modelSlot={modelControl("inline")}
                placeholder={viewDoc ? `Ask about ${viewDoc.name}…` : !active ? "Describe what you want to build, or pick an example above…" : undefined}
              />
                </>
              )}
            </main>

            {/* One inspector, with its handle, whether or not the dock shares the row. It used to be two
                branches and only one had a separator, so with the assistant hidden it could not be
                resized at all. The room test is the layout module's, not a second literal. */}
            {inspectorColumn && (
              <Inspector session={session} onHide={() => openInspector(false)} activeId={active}
                folder={folder || scratch} onAddKey={() => setSettingsOpen(true)}
                edge={<Separator zone="inspector" width={layout.inspectorWidth}
                  {...bounds("inspector", layout, viewport)} label="Resize the inspector"
                  onResize={(px) => setWidth("inspector", px)} onReset={() => resetOne("inspector")} />} />
            )}
            {/* The dock is the last column, and a grid child takes its size from content — so it must
                span the track explicitly. Its separator is absolutely positioned on the inner edge,
                exactly as the rail's and the inspector's are. */}
            {(dockColumn || focusDock) && dockNode("dock-column")}
            {/* The inspector's DRAWER, when it has a track: a grid item, not a fixed overlay. As an
                overlay it covered the document's own toolbar and, when the dock had a column, sat on
                top of the conversation (`ZN-10`, `ZN-9`). As a column it pushes the work instead.
                When it has NO track (`drawerWidth` returned null — a 1180 px window cannot afford
                276 + 480 + 380 and an inspector) it is drawn outside this grid, below: a grid child
                without a track is not an overlay, it is an extra implicit row, which is exactly how
                the dock came to render underneath the navigator. */}
            {inspectorDrawer && inspectorInGrid && (
              <Inspector session={session} onHide={() => openInspector(false)}
                className="is-drawer below-bar"
                folder={folder || scratch} activeId={active} onAddKey={() => setSettingsOpen(true)} />
            )}
          </div>

          {/* The same inspector, when a track would cost the centre its minimum: a fixed overlay at the
              right edge. Same component, same content — only the placement differs, and the placement
              is the layout module's answer, not a second guess made here. */}
          {inspectorDrawer && !inspectorInGrid && (
            <Inspector session={session} onHide={() => openInspector(false)} className="is-drawer"
              folder={folder || scratch} activeId={active} onAddKey={() => setSettingsOpen(true)} />
          )}

          {/* The scrim belongs to the drawers that cover the work *against the user's wish* — the
              rail and the inspector. The assistant is the surface the user is using, so dimming the
              document behind it would dim the thing they are asking about, and at 1024 px it stole
              the model control's clicks entirely (found by the e2e, scene 7). It gets a soft edge
              instead: see `.pane.assistant.is-drawer` box-shadow. */}
          {/* Only the NAVIGATOR drawer gets a scrim. The inspector and the assistant are siblings of
              the work, not modals over it: a scrim — even a transparent one — swallows the click meant
              for the notebook behind it, which is what broke the chord scene of `shell-e2e`. */}
          {(drawer || (dockDrawer && !focusDock)) && (
            <div className={`drawer-scrim${drawer ? "" : " is-clear"}`} role="presentation"
              onClick={() => {
                if (drawer) { setDrawer(null); toggle("rail", false); return; }
                setDockDrawer(false); toggle("assistant", false);
              }} />
          )}

          {railShown && (narrow || focusDock) && drawer === "rail" && (
            <nav className="pane rail is-drawer" aria-label="Navigator">{railBody}</nav>
          )}
          {dockOverlay && dockDrawer && !focusDock && dockNode("is-drawer")}
          {settingsOpen && (
            <ProviderSettings tab={settingsTab} onTab={setSettingsTab} onClose={() => setSettingsOpen(false)} onChanged={() => void refresh()} />
          )}

          {toast && <div className="toast" role="status">{toast}</div>}
          {paletteOpen && <Palette items={paletteItems} onClose={() => setPaletteOpen(false)} />}
          {keysOpen && <ShortcutSheet onClose={() => setKeysOpen(false)} />}


        </div>
      </OpenDoc.Provider>
    </WorkspaceLinks.Provider>
  );
}

/** Retry sends the last prompt again: the turn's own text is the honest thing to repeat. */
function lastPrompt(turns: { prompt: string }[]): string {
  return turns.at(-1)?.prompt ?? "Try that again.";
}
