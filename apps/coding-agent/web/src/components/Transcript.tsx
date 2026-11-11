/** The transcript: turns, thinking, tool cards, evidence, blocked panel. */
import { createElement, memo, useContext, useState, type ReactNode } from "react";
import { toolState, type Turn } from "../domain/events";
import { Alert, Check, ChevronDown, ChevronRight, Dot, Refresh, Ring, User } from "./Icons";
import { LogoMark } from "./Logo";
import { touched } from "../domain/docs";
import { stripEvidence, subject, toolLabel } from "../domain/toolview";
import { modelTail } from "../domain/models";
import { OpenDoc } from "./DocContext";
import { ExtLink } from "./ExtLink";
import { Chip } from "./Composer";
import { CopyButton } from "./CopyButton";
import { Markdown } from "./Markdown";
import { missionProof } from "../domain/mission";
import { pageLabel, pageOf } from "../domain/paging";

const label = toolLabel;

/** A query result as a real table: alignment, numbers right, one header row. */
function Grid({ table }: { table: { columns: string[]; rows: string[][]; truncated: boolean } }) {
  const numeric = table.columns.map((_, c) =>
    table.rows.length > 0 && table.rows.every((r) => r[c] === "" || /^-?[\d.,]+$/.test(r[c])));
  return (
    <div className="grid-wrap">
      <table className="grid">
        <caption>{table.rows.length} row{table.rows.length === 1 ? "" : "s"}{table.truncated ? ", first ones shown" : ""}</caption>
        <thead><tr>{table.columns.map((c, i) => <th key={i} className={numeric[i] ? "num" : ""}>{c}</th>)}</tr></thead>
        <tbody>
          {table.rows.map((r, ri) => (
            <tr key={ri}>{r.map((v, ci) => <td key={ci} className={numeric[ci] ? "num" : ""}>{v}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ToolCard({ name, args, status, seconds, summary, error, table }: {
  name: string; args?: string; status: string; seconds?: number; summary?: string; error?: string;
  table?: { columns: string[]; rows: string[][]; truncated: boolean };
}) {
  const [open, setOpen] = useState(false);
  const openDoc = useContext(OpenDoc);
  const hit = touched(name, args, summary);
  const state = toolState(status);
  /* A reply that is a PAGE of a larger result says so ([R-3]). Without this the card shows a list and a
     reader has no way to know whether it is the whole list — which is the visual form of the defect the
     payload window fixed on the server. `[F-2]` */
  const page = pageOf(parseLoose(summary));
  const pageText = pageLabel(page);
  // Drawn, not typed: a "✓" character sits on the font baseline and never centres in the badge.
  const glyph = state === "error" ? <Alert size={12} /> : state === "completed" ? <Check size={12} /> : null;
  return (
    <div className="tool" data-open={open}>
      <button className="tool-row" onClick={() => setOpen((o) => !o)}
        aria-expanded={open} aria-label={`${label(name)} ${state}${pageText ? `, ${pageText}` : ""}`}>
        <span className={`icon state-${state}`} aria-hidden>
          {state === "running" ? <span className="spin" /> : glyph}
        </span>
        <span className="name">{label(name)}</span>
        <span className="args" title={args}>{subject(args)}</span>
        {pageText && <span className="page-count" title="This reply is one page of a larger result">
          {pageText}</span>}
        {seconds !== undefined && <span className="time">{seconds.toFixed(1)}s</span>}
        <span className="chev" aria-hidden>▶</span>
      </button>
      {hit && state === "completed" && (
        <div className="tool-actions">
          <button className="tool-open" onClick={() => openDoc(hit.doc)}
            title={`${hit.mutates ? "Open what the agent wrote" : "Open"}: ${hit.doc.ref}`}>
            {hit.mutates ? "Open result" : "Open"}
          </button>
          <ExtLink className="tool-open ext" label={`Open ${hit.doc.name} in Databricks`}
            target={{ kind: hit.doc.kind, ref: hit.doc.ref }}>Databricks ↗</ExtLink>
        </div>
      )}
      {table && state === "completed" && <Grid table={table} />}
      {open && (
        <div className="tool-body">
          {args ? `input: ${pretty(args)}\n` : ""}
          {summary ? `result: ${summary}` : state === "running" ? "running…" : "no summary"}
          {error ? `\nerror: ${error}` : ""}
        </div>
      )}
    </div>
  );
}

/** A tool summary is JSON when the tool returned a structured reply, or prose when it did not.
 *
 *  A card needs the parsed form to read a window out of it ([R-3]). A summary that is not JSON is not an
 *  error: most tools answer in prose, and a card must not fail because of it.
 */
function parseLoose(text?: string): unknown {
  if (!text) return null;
  const t = text.trim();
  if (!t.startsWith("{") && !t.startsWith("[")) return null;
  try { return JSON.parse(t); } catch { return null; }
}

/** Arguments in full, wrapped, for the one case where the detail matters. */
function pretty(args: string): string {
  try { return JSON.stringify(JSON.parse(args), null, 2); } catch { return args; }
}

const PLAN_GLYPH: Record<string, (p: { size?: number }) => ReactNode> = {
  completed: Check, in_progress: Dot, pending: Ring,
};

function Plan({ turn }: { turn: Turn }) {
  if (!turn.plan?.length) return null;
  const done = turn.plan.filter((p) => p.status === "completed").length;
  return (
    <section className="plan" aria-label="Plan">
      <div className="plan-head">Plan <span className="count">{done} of {turn.plan.length} done</span></div>
      <ol>
        {turn.plan.map((p, i) => (
          <li key={i} className={`plan-${p.status}`}>
            <span className="plan-mark" aria-hidden>{createElement(PLAN_GLYPH[p.status] ?? Ring, { size: 12 })}</span>
            <span>{p.content}</span>
            <span className="sr-only">{p.status.replace("_", " ")}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

const tokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

function Footer({ turn }: { turn: Turn }) {
  if (!["completed", "blocked", "failed", "cancelled", "interrupted"].includes(turn.status)) return null;
  const u = turn.usage;
  const parts = [
    turn.seconds ? `${turn.seconds.toFixed(1)} s` : "",
    u && (u.input || u.output) ? `${tokens(u.input)} in` : "",
    u && (u.input || u.output) ? `${tokens(u.output)} out` : "",
    u?.cached ? `${tokens(u.cached)} cached` : "",
  ].filter(Boolean);
  // A blocked or failed turn already has a panel that says so. Repeating the word here, in its own
  // red box, was the same sentence twice; the footer keeps only what the panel does not: the cost.
  const said = Boolean(turn.blocked);
  const word = said ? "" : statusWord[turn.status] ?? turn.status;
  const label = [word, ...parts].filter(Boolean).join(" · ");
  if (!label) return null;
  return <p className={`turn-foot ${said ? "" : turn.status}`}>{label}</p>;
}

/** What a person does with an answer: take it, or ask again. Shown once the turn has ended. */
function TurnActions({ turn, onRetry }: { turn: Turn; onRetry?: () => void }) {
  const ended = ["completed", "blocked", "failed", "cancelled", "interrupted"].includes(turn.status);
  const text = turn.evidence.length ? stripEvidence(turn.answer) : turn.answer;
  if (!ended || (!text.trim() && !onRetry)) return null;
  return (
    <div className="turn-actions" role="group" aria-label="Answer actions">
      {text.trim() && <CopyButton text={text} label="Copy answer" title="Copy the answer as text" />}
      {onRetry && (
        <button type="button" className="copy-btn" onClick={onRetry} title="Ask the same thing again">
          <Refresh size={12} /> Retry
        </button>
      )}
    </div>
  );
}

function Evidence({ turn }: { turn: Turn }) {
  const proof = missionProof(turn);
  const ok = proof.filter((r) => r.verified).length;
  const [open, setOpen] = useState(false);
  if (!turn.evidence.length) return null;
  const allProven = ok === turn.evidence.length;
  const shown = open || !allProven;
  return (
    <section className="evidence" aria-label="Evidence">
      <button className="evidence-head" aria-expanded={shown} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden>{allProven ? <Check size={13} /> : <Alert size={13} />}</span> Evidence
        <span className="count">{allProven ? `all ${turn.evidence.length} proven` : `${ok} of ${turn.evidence.length} proven`}</span>
        <span className="chev" aria-hidden>{shown ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>
      </button>
      {shown && proof.map(({ row: r, verified }, i) => (
        <div key={i} className={`evidence-row${verified ? "" : " unverified"}`}>
          <span className="tick" aria-hidden>{verified ? <Check size={13} /> : <Alert size={13} />}</span>
          <span className="req">{r.requirement || "(unnamed requirement)"}</span>
          <span className="ev-tool" title={r.tool || "no tool"}>{r.tool || "no tool"}</span>
        </div>
      ))}
    </section>
  );
}

function Blocked({ turn }: { turn: Turn }) {
  if (!turn.blocked) return null;
  return (
    <section className="blocked" aria-label="Blocked">
      <h3><Alert size={14} /> {turn.status === "interrupted" ? "Work was interrupted" : "I could not finish this"}</h3>
      <p>{turn.blocked.reason}</p>
      {turn.blocked.missing.length > 0 && (
        <>
          <p><strong>Still missing</strong></p>
          <ul>{turn.blocked.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </>
      )}
      {turn.blocked.attempted.length > 0 && (
        <>
          <p><strong>What I tried</strong></p>
          <ul>{turn.blocked.attempted.map((a, i) => (
            <li key={i}><code>{a.tool}</code> — {a.status}{a.summary ? `: ${a.summary}` : ""}</li>
          ))}</ul>
        </>
      )}
      <p style={{ marginBottom: 0 }}>Review saved tool results before repeating an operation. Some changes may already have completed.</p>
    </section>
  );
}

/** Tool calls, folded to a summary when there are many and none failed: reading is the point, not scrolling. */
function ToolList({ tools }: { tools: Turn["tools"] }) {
  const failed = tools.some((t) => t.status === "error");
  const many = tools.length > 4;
  const [open, setOpen] = useState(!many || failed);
  return (
    <>
      <button className="who tools-head" aria-expanded={open || !many} onClick={() => many && setOpen((o) => !o)}>
        <span className="avatar agent" aria-hidden><LogoMark size={12} /></span> Agent
        <time>{tools.length} tool {tools.length === 1 ? "call" : "calls"}{failed ? ", one failed" : ""}</time>
        {many && <span className="chev" aria-hidden>{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>}
      </button>
      {open && <div className="tools">{tools.map((c) => <ToolCard key={c.callId} {...c} />)}</div>}
    </>
  );
}

/** The most markdown this surface will parse in one answer. Past it, plain text (see the render). */
export const MAX_MARKDOWN = 40_000;

const statusWord: Record<string, string> = {
  running: "working", auditing: "checking the work", queued: "queued", completed: "done",
  blocked: "blocked", cancelled: "stopped", failed: "failed", interrupted: "interrupted",
};

function TurnViewInner({ turn, onRetry }: { turn: Turn; onRetry?: () => void }) {
  const streamingNow = turn.status === "running" || turn.status === "auditing";
  const [showThought, setShowThought] = useState(streamingNow);
  const streaming = turn.status === "running" || turn.status === "auditing";
  return (
    <article className="turn">
      <div className="who">
        <span className="avatar you" aria-hidden><User size={12} /></span> You
        {turn.model && <span className="chip" style={{ marginLeft: 6 }} title={turn.model}>{modelTail(turn.model)}</span>}
        <time>{statusWord[turn.status] ?? turn.status}</time>
      </div>
      <div className="prompt">
        {turn.attachments && turn.attachments.length > 0 && (
          <div className="ctx-row in-prompt">{turn.attachments.map((a) => <Chip key={`${a.kind}:${a.ref}`} a={a} />)}</div>
        )}
        {turn.prompt}
      </div>
      <Plan turn={turn} />

      {turn.thought && (
        <div className="thought">
          <button className="thought-toggle" onClick={() => setShowThought((s) => !s)} aria-expanded={showThought}>
            <span aria-hidden>{showThought ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span> thinking
            {streaming && <span className="spin" aria-hidden />}
          </button>
          {showThought && <div className="thought-body">{turn.thought}</div>}
        </div>
      )}

      {turn.tools.length > 0 && <ToolList tools={turn.tools} />}

      {turn.answer && (
        <section className="answer-block" aria-label="The agent's answer">
          {/* A real h2 for the answer, visually hidden. The brand is the page's only h1, and markdown
              renders "###" as a genuine h3 — so without a heading here the document skipped h1 to h3,
              which the audit flagged on every turn. This also makes the transcript navigable by
              heading in a screen reader, which is the point of headings in a long log. */}
          <h2 className="sr-only">The agent's answer</h2>
          {/* Markdown is parsed only up to a bound. Streaming a long answer as plain text was already
              the rule; a FINISHED 200 000-character answer was still handed to the markdown parser
              whole, and that is enough DOM to crash the tab — which is exactly what happened while
              measuring (the page died mid-run, taking an e2e with it). Past the bound the answer is
              shown as text, with a line saying so, because a rendered answer nobody can read the end
              of is worse than an honest one. */}
          {turn.answer.length > MAX_MARKDOWN
            ? (
              <>
                <div className="answer streaming-plain">{turn.answer}</div>
                <p className="answer-clipped" role="note">
                  This answer is {Math.round(turn.answer.length / 1000)}k characters, so it is shown as
                  plain text rather than formatted.
                </p>
              </>
            )
            : <Markdown text={turn.evidence.length ? stripEvidence(turn.answer) : turn.answer} streaming={streaming} />}
          {streaming && <span className="caret" aria-hidden />}
        </section>
      )}
      {turn.status === "auditing" && !turn.answer && <p style={{ color: "var(--ink-3)" }}>Checking the work…</p>}
      <Evidence turn={turn} />
      <Blocked turn={turn} />
      <TurnActions turn={turn} onRetry={onRetry} />
      <Footer turn={turn} />
    </article>
  );
}

/** One changed turn replaces one object, so the others skip work. */
export const TurnView = memo(TurnViewInner);
