import { useContext, useEffect, useRef } from "react";
import type { AgentQuestion } from "../../domain/events";
import { Context } from "./model";
import { Status } from "./Status";
export function QuestionCard({ question }: { question: AgentQuestion }) {
  const { busy, act } = useContext(Context);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    form.current?.querySelector<HTMLElement>("select,input")?.focus();
  }, [question.id]);
  return (
    <form
      className="work-card work-question"
      ref={form}
      aria-label="Agent question"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          void act(`questions/${question.id}`, { action: "cancel" });
        }
      }}
      onSubmit={(e) => {
        e.preventDefault();
        const fields = new FormData(e.currentTarget);
        const content: Record<string, unknown> = {};
        for (const [name, spec] of Object.entries(question.schema.properties)) {
          const raw = fields.get(name);
          if (raw === null || raw === "") continue;
          content[name] =
            spec.type === "boolean"
              ? raw === "true"
              : ["integer", "number"].includes(spec.type)
                ? Number(raw)
                : raw;
        }
        void act(`questions/${question.id}`, { action: "accept", content });
      }}
    >
      <header>
        Question from {question.agent}
        <Status state={question.state} />
      </header>
      <h3>{question.message}</h3>
      <p>
        {question.state === "expired"
          ? "This question expired when the agent restarted. Restore the agent and ask it to continue if you still need this work."
          : "Your response guides the agent. It does not approve workspace actions."}
      </p>
      {question.state === "pending" && (
        <>
          {Object.entries(question.schema.properties).map(([name, spec]) => (
            <label className="work-question-field" key={name}>
              <span>
                {spec.title || name}
                {question.schema.required?.includes(name) ? " *" : ""}
              </span>
              {spec.enum || spec.type === "boolean" ? (
                <select
                  name={name}
                  required={question.schema.required?.includes(name)}
                  defaultValue={String(spec.default ?? "")}
                >
                  <option value="">Choose…</option>
                  {(spec.enum ?? [true, false]).map((v) => (
                    <option key={String(v)} value={String(v)}>
                      {String(v)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  name={name}
                  type={
                    ["number", "integer"].includes(spec.type)
                      ? "number"
                      : "text"
                  }
                  step={spec.type === "number" ? "any" : "1"}
                  defaultValue={String(spec.default ?? "")}
                  required={question.schema.required?.includes(name)}
                  min={spec.minimum}
                  max={spec.maximum}
                  minLength={spec.minLength}
                  maxLength={Math.min(spec.maxLength ?? 2000, 2000)}
                />
              )}
              {spec.description && <small>{spec.description}</small>}
            </label>
          ))}
          <div className="work-actions">
            <button className="btn primary" disabled={busy}>
              Send response
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={busy}
              onClick={() =>
                void act(`questions/${question.id}`, { action: "decline" })
              }
            >
              Skip question
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={busy}
              onClick={() =>
                void act(`questions/${question.id}`, { action: "cancel" })
              }
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </form>
  );
}
