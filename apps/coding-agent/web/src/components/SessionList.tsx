/** The conversation history: search, grouped by day, delete with a confirmation.
 *
 * Grouping and matching are `domain/sessions.ts`; this only draws and carries the two bits of UI state
 * (the query, and which row is asking "delete?"). Delete is two steps on the row itself rather than a
 * modal: it keeps the user's place, and a misclick costs one more click instead of a conversation.
 */
import { useMemo, useState } from "react";
import { exactTime, relativeTime } from "../domain/time";
import { groupSessions, sessionLabel, type SessionLike } from "../domain/sessions";
import { Close, Search } from "./Icons";

export function SessionList<T extends SessionLike>({ sessions, loaded = true, activeId, onOpen, onDelete }: {
  sessions: T[]; /** Has the first fetch answered? Absent means "yes" (tests and previews that seed data). */
  loaded?: boolean; activeId: string | null; onOpen: (s: T) => void; onDelete: (s: T) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const groups = useMemo(() => groupSessions(sessions, query), [sessions, query]);

  const confirm = async (s: T) => {
    try { await onDelete(s); setFailed(null); } catch { setFailed(s.id); }
    setAsking(null);
  };

  return (
    <>
      {/* The search box appears once there are more than four conversations. It is 30 px + 4 px of
          padding, and rendering it late pushed the whole list down by exactly that much — measured
          CLS 0.0064 at 82 ms, with `rail-list` moving y 152 → 186. Its space is reserved from the
          first paint so the list never moves: an empty slot while loading, the real box once there is
          something to search. A control that appears is fine; content that jumps is not. */}
      {(!loaded || sessions.length > 4) && (
        <div className={`rail-search${loaded ? "" : " is-reserved"}`} aria-hidden={!loaded}>
          {loaded && (
            <>
              <Search size={13} />
              <input type="search" value={query} placeholder="Search conversations" aria-label="Search conversations"
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape" && query) { e.stopPropagation(); setQuery(""); } }} />
              {query && (
                <button type="button" className="rail-search-clear" aria-label="Clear the search" onClick={() => setQuery("")}>
                  <Close size={12} />
                </button>
              )}
            </>
          )}
        </div>
      )}
      <div className="rail-list">
        {/* "Nothing here" is a claim about the data, so it waits for the data. Rendering it while the
            fetch is in flight put a false statement on screen and moved every row below it when the
            real list arrived. The placeholder reserves the first row's height so the swap is silent. */}
        {!loaded && (
          <p className="rail-empty rail-loading" role="status">Loading conversations…</p>
        )}
        {loaded && sessions.length === 0 && (
          <p className="rail-empty">No conversations yet. Start with what you want to build.</p>
        )}
        {loaded && sessions.length > 0 && groups.length === 0 && (
          <p className="rail-empty" role="status">Nothing matches “{query}”.</p>
        )}
        {groups.map((g) => (
          <section key={g.label} aria-label={g.label}>
            <h2 className="rail-group">{g.label}</h2>
            {g.items.map((s) => {
              const when = relativeTime(s.createdAt);
              return asking === s.id ? (
                <div key={s.id} className="rail-confirm" role="alertdialog" aria-label={`Delete ${sessionLabel(s)}?`}>
                  <p>Delete this conversation?</p>
                  <div className="rail-confirm-actions">
                    <button type="button" className="btn sm danger" autoFocus onClick={() => void confirm(s)}>Delete</button>
                    <button type="button" className="btn sm ghost" onClick={() => setAsking(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div key={s.id} className="rail-row">
                  <button className="rail-item" aria-current={s.id === activeId}
                    title={exactTime(s.createdAt) || undefined} onClick={() => onOpen(s)}>
                    <span className={`dot${s.status === "streaming" ? " busy" : ""}`} aria-hidden />
                    <span className="rail-item-label">{sessionLabel(s)}</span>
                    {when && <span className="rail-item-when" aria-label={exactTime(s.createdAt)}>{when}</span>}
                  </button>
                  <button type="button" className="rail-del" aria-label={`Delete ${sessionLabel(s)}`} title="Delete this conversation"
                    onClick={() => setAsking(s.id)}><Close size={12} /></button>
                  {failed === s.id && <p className="rail-fail" role="alert">Could not delete. Try again.</p>}
                </div>
              );
            })}
          </section>
        ))}
      </div>
    </>
  );
}
