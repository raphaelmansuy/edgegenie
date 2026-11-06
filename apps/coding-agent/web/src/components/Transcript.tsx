/** The transcript: turns, thinking, tool cards, evidence, blocked panel. */
import { useContext, useState } from "react";
import type { Turn } from "../domain/events";
import { touched } from "../domain/docs";
import { OpenDoc } from "./DocContext";
import { ExtLink } from "./ExtLink";
import { Chip } from "./Composer";
import { Markdown } from "./Markdown";

const FRIENDLY: Record<string, string> = {
  describe_table: "looked at the table", list_tables: "listed tables", run_sql: "ran SQL",
  write_notebook: "wrote a notebook", run_notebook: "ran a notebook", read_notebook: "read a notebook",
  grep_notebook: "searched a notebook", create_job: "created a job", run_job: "ran a job",
  write_file: "wrote a file", lakebase_create: "created a database", skill: "read a skill",
};

function label(name: string): string {
  const plain = name.replace(/^dbxnb_/, "").replace(/^dbx_/, "").replace(/^dbx/, "");
  return FRIENDLY[plain] ?? plain.replace(/_/g, " ");
}

export function ToolCard({ name, args, status, seconds, summary, error }: {
  name: string; args?: string; status: string; seconds?: number; summary?: string; error?: string;
}) {
  const [open, setOpen] = useState(false);
  const openDoc = useContext(OpenDoc);
  const hit = touched(name, args);
  const state = status === "error" ? "error" : status === "completed" ? "completed" : "running";
  const glyph = state === "error" ? "!" : state === "completed" ? "✓" : "";
  return (
    <div className="tool" data-open={open}>
      {hit && state === "completed" && (
        <button className="tool-open" onClick={() => openDoc(hit.doc)}
          title={`${hit.mutates ? "Open what the agent wrote" : "Open"}: ${hit.doc.ref}`}>
          {hit.mutates ? "Open result" : "Open"}
        </button>
      )}
      {hit && state === "completed" && (
        <ExtLink className="tool-open ext" label={`Open ${hit.doc.name} in Databricks`}
          target={{ kind: hit.doc.kind, ref: hit.doc.ref }}>Databricks ↗</ExtLink>
      )}
      <button className="tool-row" onClick={() => setOpen((o) => !o)}
        aria-expanded={open} aria-label={`${label(name)} ${state}`}>
        <span className={`icon state-${state}`} aria-hidden>
          {state === "running" ? <span className="spin" /> : glyph}
        </span>
        <span className="name">{label(name)}</span>
        <span className="args">{args}</span>
        {seconds !== undefined && <span className="time">{seconds.toFixed(1)}s</span>}
        <span className="chev" aria-hidden>▶</span>
      </button>
      {open && (
        <div className="tool-body">
          {args ? `input: ${args}\n` : ""}
          {summary ? `result: ${summary}` : state === "running" ? "running…" : "no summary"}
          {error ? `\nerror: ${error}` : ""}
        </div>
      )}
    </div>
  );
}

const PLAN_GLYPH: Record<string, string> = { completed: "✓", in_progress: "●", pending: "○" };

function Plan({ turn }: { turn: Turn }) {
  if (!turn.plan?.length) return null;
  const done = turn.plan.filter((p) => p.status === "completed").length;
  return (
    <section className="plan" aria-label="Plan">
      <div className="plan-head">Plan <span className="count">{done} of {turn.plan.length} done</span></div>
      <ol>
        {turn.plan.map((p, i) => (
          <li key={i} className={`plan-${p.status}`}>
            <span className="plan-mark" aria-hidden>{PLAN_GLYPH[p.status] ?? "○"}</span>
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
  if (turn.status !== "completed") return null;
  const u = turn.usage;
  const parts = [
    turn.seconds ? `${turn.seconds.toFixed(1)} s` : "",
    u && (u.input || u.output) ? `${tokens(u.input)} in` : "",
    u && (u.input || u.output) ? `${tokens(u.output)} out` : "",
    u?.cached ? `${tokens(u.cached)} cached` : "",
  ].filter(Boolean);
  return parts.length ? <p className="turn-foot">{parts.join(" · ")}</p> : null;
}

function Evidence({ turn }: { turn: Turn }) {
  if (!turn.evidence.length) return null;
  const ok = turn.evidence.filter((r) => r.verified).length;
  return (
    <section className="evidence" aria-label="Evidence">
      <div className="evidence-head">
        <span aria-hidden>🛡</span> Evidence
        <span className="count">{ok} of {turn.evidence.length} requirements proven</span>
      </div>
      {turn.evidence.map((r, i) => (
        <div key={i} className={`evidence-row${r.verified ? "" : " unverified"}`}>
          <span className="tick" aria-hidden>{r.verified ? "✓" : "?"}</span>
          <span className="req">{r.requirement || "(unnamed requirement)"}</span>
          <span className="tool">{r.tool || "no tool"}</span>
        </div>
      ))}
    </section>
  );
}

function Blocked({ turn }: { turn: Turn }) {
  if (!turn.blocked) return null;
  return (
    <section className="blocked" aria-label="Blocked">
      <h3>⛔ I could not finish this</h3>
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
      <p style={{ marginBottom: 0 }}>Nothing outside your working scope was changed.</p>
    </section>
  );
}

const statusWord: Record<string, string> = {
  running: "working", auditing: "checking the work", queued: "queued", completed: "done",
  blocked: "blocked", cancelled: "stopped", failed: "failed", interrupted: "interrupted",
};

export function TurnView({ turn }: { turn: Turn }) {
  const streamingNow = turn.status === "running" || turn.status === "auditing";
  const [showThought, setShowThought] = useState(streamingNow);
  const streaming = turn.status === "running" || turn.status === "auditing";
  return (
    <article className="turn">
      <div className="who">
        <span className="avatar you" aria-hidden>You</span> You
        {turn.model && <span className="chip" style={{ marginLeft: 6 }}>{turn.model.split("/").pop()}</span>}
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
            <span aria-hidden>{showThought ? "▾" : "▸"}</span> thinking
            {streaming && <span className="spin" aria-hidden />}
          </button>
          {showThought && <div className="thought-body">{turn.thought}</div>}
        </div>
      )}

      {turn.tools.length > 0 && (
        <div className="who" style={{ marginTop: 18 }}>
          <span className="avatar agent" aria-hidden>◧</span> Agent
          <time>{turn.tools.length} tool {turn.tools.length === 1 ? "call" : "calls"}</time>
        </div>
      )}
      <div className="tools">
        {turn.tools.map((c) => <ToolCard key={c.callId} {...c} />)}
      </div>

      {turn.answer && (
        <>
          <Markdown text={turn.answer} />
          {streaming && <span className="caret" aria-hidden />}
        </>
      )}
      {turn.status === "auditing" && !turn.answer && <p style={{ color: "var(--ink-3)" }}>Checking the work…</p>}
      <Evidence turn={turn} />
      <Blocked turn={turn} />
      <Footer turn={turn} />
    </article>
  );
}
