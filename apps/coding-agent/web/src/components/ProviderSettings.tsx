/** Providers and keys: one row per provider, and the add-key form.
 *
 * Three decisions from 07 that this file respects:
 *
 * 1. **A route, not a modal.** Key entry is revisited and interrupted; a route survives a refresh and
 *    a tab close. The app has no router, so "route" is a view state with `esc` as the back path and a
 *    `#settings/providers` hash so a reload lands in the same place.
 * 2. **Test before Save.** A malformed service-account JSON must fail before it is stored (K3), and
 *    the form names the failing field (K1/K2).
 * 3. **Never a reveal.** The key is masked once it validates, and nothing derived from it comes back
 *    from the server beyond `last4` and a fingerprint (C-1).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CredentialView, type LlmHealth } from "../api/client";
import { sourceNotice, type CatalogueResponse, type ModelSpec } from "../domain/models";
import { Alert, Check, Lock, Plus, Refresh, Warning } from "./Icons";

export interface ProviderSettingsProps {
  onClose: () => void;
  /** Called after a key changes, so the catalogue can be re-read and the picker updated. */
  onChanged?: () => void;
}

interface ProviderRow {
  id: string;
  name: string;
  kind: string;
  credentialKind: string;
  models: ModelSpec[];
  credential: CredentialView | null;
  health: string;
  detail: string;
  usable: number;
}

/** The credential kind a provider needs, derived from its models: one place, not a switch per row. */
function credentialKindOf(models: ModelSpec[]): string {
  const spec = models.find((m) => m.credential.kind !== "none");
  return spec?.credential.kind ?? "none";
}

export function ProviderSettings({ onClose, onChanged }: ProviderSettingsProps) {
  const [catalogue, setCatalogue] = useState<CatalogueResponse | null>(null);
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [credentials, setCredentials] = useState<CredentialView[]>([]);
  const [canSave, setCanSave] = useState(false);
  const [vaultMode, setVaultMode] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const [cat, creds, healthBody] = await Promise.all([
      api.catalogue().catch(() => api.models()),
      api.credentials().catch(() => ({ credentials: [], vault: { mode: "", available: false }, canSave: false })),
      api.llmHealth().catch(() => null),
    ]);
    setCatalogue(cat);
    setCredentials(creds.credentials);
    setCanSave(creds.canSave);
    setVaultMode(creds.vault.mode);
    setHealth(healthBody);
  }, []);

  useEffect(() => { void load(); }, [load]);

  // `esc` is the back path from every surface (07 §Navigation map).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows = useMemo<ProviderRow[]>(() => {
    const specs = catalogue?.available ?? [];
    const byProvider = new Map<string, ModelSpec[]>();
    for (const spec of specs) {
      const list = byProvider.get(spec.provider) ?? [];
      list.push(spec);
      byProvider.set(spec.provider, list);
    }
    return [...byProvider.entries()].map(([id, models]) => {
      const credential = credentials.find((c) => c.provider === id) ?? null;
      const providerHealth = health?.providers.find((p) => p.id === id);
      return {
        id,
        name: models[0]?.providerName ?? id,
        kind: models[0]?.provider ?? id,
        credentialKind: credentialKindOf(models),
        models,
        credential,
        health: providerHealth?.state ?? "unknown",
        detail: providerHealth?.detail ?? "",
        usable: models.filter((m) => m.selectable).length,
      };
    });
  }, [catalogue, credentials, health]);

  const revoke = async (ref: string) => {
    setBusy(ref);
    setError("");
    try {
      await api.revokeCredential(ref);
      setNotice("The key was revoked. It will never be decrypted again.");
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "the key could not be revoked");
    } finally {
      setBusy("");
    }
  };

  const noticeText = catalogue ? sourceNotice(catalogue.source) : "";
  const current = rows.find((r) => r.id === adding);

  return (
    <div className="settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header className="settings-head">
        <div>
          <h2 id="settings-title">Providers and keys</h2>
          <p className="settings-sub">
            A key is encrypted before it is stored and is never shown again. Prompts and tool results
            in a session on an external model leave your Databricks workspace.
          </p>
        </div>
        <div className="settings-head-actions">
          <button className="btn" onClick={async () => { setBusy("refresh"); try { await api.refreshDiscovery(); await load(); onChanged?.(); } catch (err) { setError(err instanceof Error ? err.message : "discovery failed"); } finally { setBusy(""); } }}
            disabled={busy === "refresh"}>
            <Refresh size={13} /> Refresh models
          </button>
          <button className="btn" onClick={onClose} aria-label="Close settings">Close</button>
        </div>
      </header>

      {noticeText && (
        <p className="settings-notice" role="note"><Warning size={14} /> {noticeText}</p>
      )}
      {error && <p className="settings-error" role="alert"><Alert size={14} /> {error}</p>}
      {notice && !error && <p className="settings-ok" role="status"><Check size={14} /> {notice}</p>}

      {adding && current ? (
        <AddKey
          provider={current.id}
          providerName={current.name}
          credentialKind={current.credentialKind}
          models={current.models}
          canSave={canSave}
          onCancel={() => setAdding(null)}
          onSaved={async () => { setAdding(null); setNotice("Key saved. It is encrypted at rest and never shown again."); await load(); onChanged?.(); }}
        />
      ) : (
        <div className="settings-rows">
          {rows.map((row) => (
            <ProviderCard
              key={row.id}
              row={row}
              canSave={canSave}
              busy={busy === row.credential?.id}
              onAdd={() => setAdding(row.id)}
              onRevoke={() => row.credential && void revoke(row.credential.id)}
              onTest={row.models[0] ? async () => {
                setBusy(row.credential?.id ?? row.id);
                try {
                  const r = await api.probeModel(row.models[0].id);
                  setNotice(`${row.name}: ${r.state}${r.detail ? ` — ${r.detail}` : ""}`);
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "the probe failed");
                } finally { setBusy(""); }
              } : undefined}
            />
          ))}
        </div>
      )}

      <footer className="settings-foot">
        <span>
          source: {catalogue?.source ?? "…"}
          {vaultMode && <> · keys {canSave ? `encrypted with ${vaultMode}` : "cannot be saved here"}</>}
        </span>
        <span>
          {rows.filter((r) => r.credentialKind !== "none").length} of {rows.length} providers need a key
          {" · "}
          {rows.filter((r) => r.credential).length} configured
        </span>
      </footer>
    </div>
  );
}

function ProviderCard({ row, canSave, busy, onAdd, onRevoke, onTest }: {
  row: ProviderRow; canSave: boolean; busy: boolean;
  onAdd: () => void; onRevoke: () => void; onTest?: () => void;
}) {
  // Three cases, not two: a provider whose credential is the workspace token, a replay with no
  // credential at all, and one that needs a key of its own. Collapsing the middle case into the
  // first made the demo agent claim a workspace token it never uses.
  const managed = row.credentialKind === "none";
  const needsKey = !managed;
  const state = managed ? (row.kind === "fake" ? "demo" : "managed")
    : row.credential ? row.health : "missing";
  return (
    <section className="provider-card" aria-label={row.name}>
      <header className="provider-head">
        <h3>{row.name}</h3>
        <span className={`provider-state is-${state}`}>
          {state === "managed" ? <><Lock size={12} /> workspace token · managed</>
            : state === "demo" ? <>replayed locally · no credential</>
              : row.credential ? <><Check size={12} /> connected</>
                : <><span aria-hidden>✕</span> no key</>}
        </span>
      </header>
      <dl className="provider-facts">
        <dt>Models</dt>
        <dd>
          {row.models.length} available · {row.usable} usable
          {row.models.filter((m) => m.state === "not_enabled").length > 0
            && ` · ${row.models.filter((m) => m.state === "not_enabled").length} not enabled`}
        </dd>
        {state === "demo" ? (
          <>
            <dt>Credential</dt>
            <dd>none — the demo agent replays a recorded turn, so there is no provider to reach</dd>
          </>
        ) : managed ? (
          <>
            <dt>Credential</dt>
            <dd>your Databricks session — there is no key to manage</dd>
          </>
        ) : row.credential ? (
          <>
            <dt>Key</dt>
            <dd>
              {row.credential.kind.replace(/_/g, " ")} · …{row.credential.last4}
              {row.credential.projectHint && ` · project ${row.credential.projectHint}`}
            </dd>
            {row.detail && (<><dt>Provider says</dt><dd className="provider-error">{row.detail}</dd></>)}
          </>
        ) : (
          <>
            <dt>Nothing configured</dt>
            <dd>
              {row.models.length} {row.models.length === 1 ? "model" : "models"} would become available.
            </dd>
          </>
        )}
      </dl>
      {needsKey && (
        <div className="provider-actions">
          {row.credential ? (
            <>
              {onTest && <button className="btn" onClick={onTest} disabled={busy}>Test</button>}
              <button className="btn" onClick={onAdd} disabled={!canSave}>Rotate</button>
              <button className="btn danger" onClick={onRevoke} disabled={busy}>Revoke</button>
            </>
          ) : (
            <button className="btn primary" onClick={onAdd} disabled={!canSave}>
              <Plus size={13} /> Add a key
            </button>
          )}
          {!canSave && <span className="provider-hint">keys cannot be saved in this deployment</span>}
        </div>
      )}
    </section>
  );
}

/** The add-key form. Validation runs on paste, the secret is masked after it passes, and Test must
 *  pass before Save unless the user saves anyway with the error shown (K1–K4). */
function AddKey({ provider, providerName, credentialKind, models, canSave, onCancel, onSaved }: {
  provider: string; providerName: string; credentialKind: string;
  models: ModelSpec[]; canSave: boolean;
  onCancel: () => void; onSaved: () => void;
}) {
  const [secret, setSecret] = useState("");
  const [tested, setTested] = useState<null | { ok: boolean; detail?: string; state?: string; field?: string }>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set(models.filter((m) => m.selectable).slice(0, 3).map((m) => m.id)),
  );
  const isJson = credentialKind === "service_account_json";
  const masked = tested?.ok === true;

  const test = async () => {
    setError("");
    setTested(null);
    try {
      const r = await api.testCredential(provider, credentialKind, secret, models[0]?.id);
      setTested(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "the test could not run");
    }
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await api.saveCredential(provider, credentialKind, secret);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "the key could not be saved");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="add-key" aria-label={`Add a key for ${providerName}`}>
      <header className="add-key-head">
        <h3>Add a key · {providerName}</h3>
        <button className="btn ghost" onClick={onCancel} aria-label="Cancel adding a key">Cancel</button>
      </header>
      <p className="add-key-lede">
        {isJson
          ? "Paste the service-account JSON, or drop the .json file here. It is encrypted before it is stored, and never shown again."
          : `Paste the ${providerName} API key. It is encrypted before it is stored, and never shown again.`}
      </p>

      <label className="add-key-field">
        <span className="sr-only">{isJson ? "Service-account JSON" : "API key"}</span>
        {isJson ? (
          <textarea
            className="add-key-input mono"
            rows={7}
            spellCheck={false}
            value={masked ? maskJson(secret) : secret}
            onChange={(e) => { setSecret(e.target.value); setTested(null); }}
            placeholder={'{\n  "type": "service_account",\n  "project_id": "…",\n  "private_key": "-----BEGIN PRIVATE KEY-----\\n…"\n}'}
            aria-describedby="add-key-status"
          />
        ) : (
          <input
            className="add-key-input mono"
            type={masked ? "password" : "text"}
            spellCheck={false}
            autoComplete="off"
            value={secret}
            onChange={(e) => { setSecret(e.target.value); setTested(null); }}
            placeholder={provider === "anthropic" ? "sk-ant-…" : "sk-…"}
            aria-describedby="add-key-status"
          />
        )}
      </label>

      <div id="add-key-status" className="add-key-status" role="status" aria-live="polite">
        {tested?.ok && <p className="ok"><Check size={13} /> The key is well formed{tested.state === "available" ? " and the provider answered" : ""}.</p>}
        {tested && !tested.ok && (
          <p className="bad"><Warning size={13} /> {tested.field ? `${tested.field}: ` : ""}{tested.detail ?? "the key was refused"}</p>
        )}
        {masked && isJson && <p className="muted"><Lock size={12} /> private key masked — it is never shown again</p>}
      </div>

      <fieldset className="add-key-models">
        <legend>Which models should this key enable?</legend>
        {models.map((m) => (
          <label key={m.id} className="add-key-model">
            <input
              type="checkbox"
              checked={chosen.has(m.id)}
              onChange={(e) => {
                const next = new Set(chosen);
                if (e.target.checked) next.add(m.id); else next.delete(m.id);
                setChosen(next);
              }}
            />
            <span>{m.name}</span>
            <span className="add-key-model-state">{m.state}</span>
          </label>
        ))}
      </fieldset>

      <p className="add-key-egress" role="note">
        Prompts and tool results in these sessions leave your Databricks workspace: {providerName}'s
        terms apply, not Unity Catalog.
      </p>

      {error && <p className="add-key-error" role="alert"><Alert size={13} /> {error}</p>}

      <div className="add-key-actions">
        <button className="btn" onClick={() => void test()} disabled={!secret.trim()}>Test connection</button>
        <button className="btn primary" onClick={() => void save()}
          disabled={!canSave || !secret.trim() || saving || (tested ? !tested.ok : false)}>
          {saving ? "Saving…" : "Save key"}
        </button>
      </div>
    </section>
  );
}

/** Keep the structure readable while proving the private key is not on screen. */
function maskJson(text: string): string {
  return text.replace(
    /("private_key"\s*:\s*")([^"]{0,40})[^"]*(")/,
    (_m, head: string, shown: string, tail: string) => `${head}${shown.split("\\n")[0]}••••••${tail}`,
  );
}
