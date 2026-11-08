/** Model configuration: which external models exist, which one is the default, who sees them.
 *
 * Everything on this screen is written to the registry database, and the first line says so (or says
 * plainly that it cannot). Three rules it keeps:
 *
 * 1. **Say where it is saved.** A setting that looks saved and is not is the failure to avoid, so the
 *    storage line is always visible and the controls disable with a reason when saving is impossible.
 * 2. **Read-only is a state, not an error.** Anyone can see the catalogue; only administrators can
 *    change it for everyone, and the screen says which one you are.
 * 3. **The same checks as the server.** `validateNewModel` runs on every keystroke, so a mistake is
 *    named at the field before a round trip.
 */
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import {
  defaultCandidates, externalProviders, formatTokens, modelsOf, storageLine, validateNewModel,
  type ConfigModel, type ConfigProvider, type ModelConfig, type NewModelForm,
} from "../domain/modelconfig";
import { Alert, Check, Lock, Plus, Trash, Warning } from "./Icons";

const EMPTY: NewModelForm = { model: "", name: "", context: "128k", output: "8k" };

export function ModelConfigPane({ onChanged }: { onChanged?: () => void }) {
  const [cfg, setCfg] = useState<ModelConfig | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [pick, setPick] = useState("");

  const load = useCallback(async () => {
    try {
      const next = await api.llmConfig();
      setCfg(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "the configuration could not be read");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  // The selector shows the saved default until the user chooses something else, and follows it when
  // the default changes by another route (the "Make default" button, or another administrator).
  useEffect(() => { if (cfg) setPick(cfg.default); }, [cfg?.default]);  // eslint-disable-line react-hooks/exhaustive-deps

  /** One wrapper for every write: busy flag, error text, reload, and tell the picker to re-read. */
  const act = async (key: string, doing: () => Promise<unknown>, done: string): Promise<boolean> => {
    setBusy(key); setError(""); setNotice("");
    try {
      await doing();
      setNotice(done);
      await load();
      onChanged?.();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "the change was not saved");
      return false;
    } finally {
      setBusy("");
    }
  };

  const candidates = useMemo(() => (cfg ? defaultCandidates(cfg) : []), [cfg]);
  if (!cfg) {
    return <div className="mc-loading" role="status">{error ? <><Alert size={14} /> {error}</> : "Reading the configuration…"}</div>;
  }
  const storage = storageLine(cfg);
  const editable = cfg.canConfigure && cfg.canSave;
  const why = !cfg.canConfigure
    ? "Read only: only an administrator of this app can change the model configuration."
    : !cfg.canSave ? cfg.reason : "";

  return (
    <div className="mc" aria-label="Model configuration">
      <div className={`mc-storage is-${storage.tone}`} role="status">
        {storage.tone === "ok" ? <Check size={14} /> : <Warning size={14} />}
        <span>{storage.text}</span>
        <span className="mc-role">{cfg.canConfigure ? "You can change this" : "Read only"}</span>
      </div>
      {error && <p className="settings-error" role="alert"><Alert size={14} /> {error}</p>}
      {notice && !error && <p className="settings-ok" role="status"><Check size={14} /> {notice}</p>}
      {why && !error && <p className="mc-why"><Lock size={12} /> {why}</p>}
      {!cfg.externalAllowed && (
        <p className="settings-notice" role="note"><Warning size={14} /> External providers are switched off for
          this workspace (APP_LLM_ALLOW_EXTERNAL), so models added here stay unavailable.</p>
      )}

      <div className="mc-body">
        <section className="mc-card" aria-labelledby="mc-default-title">
          <header><h3 id="mc-default-title">Default model</h3><span className="mc-sub">Used for every new conversation unless someone picks another.</span></header>
          <div className="mc-row">
            <label className="mc-field grow">
              <span className="sr-only">Default model</span>
              <select value={pick} onChange={(e) => setPick(e.target.value)} disabled={!editable} aria-label="Default model">
                {candidates.map((m) => (
                  <option key={m.id} value={m.id}>{m.providerName} · {m.name}</option>
                ))}
              </select>
            </label>
            <button className="btn primary" disabled={!editable || !pick || pick === cfg.default || busy === "default"}
              onClick={() => void act("default", () => api.setDefaultModel(pick), "Default model saved.")}>
              {busy === "default" ? "Saving…" : "Use as default"}
            </button>
          </div>
          <p className="mc-hint">Now: <b>{cfg.models.find((m) => m.id === cfg.default)?.name ?? cfg.default}</b></p>
        </section>

        {externalProviders(cfg).map((p) => (
          <ProviderBlock
            key={p.id}
            provider={p}
            models={modelsOf(cfg, p.id)}
            editable={editable}
            busy={busy}
            adding={adding === p.id}
            onAdd={() => setAdding(adding === p.id ? null : p.id)}
            act={act}
            onDone={() => setAdding(null)}
          />
        ))}
      </div>
    </div>
  );
}

function ProviderBlock({ provider, models, editable, busy, adding, onAdd, onDone, act }: {
  provider: ConfigProvider; models: ConfigModel[]; editable: boolean; busy: string;
  adding: boolean; onAdd: () => void; onDone: () => void;
  act: (key: string, doing: () => Promise<unknown>, done: string) => Promise<boolean>;
}) {
  const [address, setAddress] = useState(provider.baseUrl);
  useEffect(() => setAddress(provider.baseUrl), [provider.baseUrl]);
  const addressBad = address.trim() !== "" && !address.trim().startsWith("https://");

  return (
    <section className="mc-card" aria-label={provider.name}>
      <header className="mc-provider-head">
        <div>
          <h3>{provider.name}</h3>
          <span className={`mc-chip ${provider.hasKey ? "is-ok" : "is-warn"}`}>
            {provider.hasKey ? <><Check size={11} /> you have a key</> : "no key from you yet"}
          </span>
        </div>
        <label className="mc-switch">
          <input type="checkbox" role="switch" checked={provider.enabled} disabled={!editable || busy === `prov-${provider.id}`}
            aria-label={`${provider.name} enabled`}
            onChange={(e) => void act(`prov-${provider.id}`, () => api.patchProvider(provider.id, { enabled: e.target.checked }),
              `${provider.name} ${e.target.checked ? "switched on" : "switched off"}.`)} />
          <span>{provider.enabled ? "On" : "Off"}</span>
        </label>
      </header>

      {provider.kind !== "google_vertex" && (
        <div className="mc-row">
          <label className="mc-field grow">
            <span>Address <i>(leave empty for the provider's own)</i></span>
            <input value={address} placeholder="https://api.example.com/v1" spellCheck={false}
              disabled={!editable} onChange={(e) => setAddress(e.target.value)} aria-invalid={addressBad}
              aria-label={`${provider.name} address`} />
          </label>
          <button className="btn" disabled={!editable || addressBad || address.trim() === provider.baseUrl || busy === `addr-${provider.id}`}
            onClick={() => void act(`addr-${provider.id}`, () => api.patchProvider(provider.id, { baseUrl: address.trim() }), "Address saved.")}>
            Save address
          </button>
        </div>
      )}
      {addressBad && <p className="mc-error">A provider address must start with https://</p>}

      <table className="mc-models">
        <thead>
          <tr><th scope="col">Model</th><th scope="col">Window</th><th scope="col">State</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          {models.length === 0 && (
            <tr><td colSpan={4} className="mc-empty">No models yet. Add the first one below.</td></tr>
          )}
          {models.map((m) => (
            <tr key={m.id} className={m.enabled ? "" : "is-off"}>
              <td>
                <div className="mc-name">{m.name}{m.isDefault && <span className="mc-chip is-ok">default</span>}</div>
                <div className="mc-id">{m.endpoint}</div>
              </td>
              <td className="mc-num" title={`${m.limits.evidence}: ${m.limits.source}`}>
                {formatTokens(m.limits.context)} in · {formatTokens(m.limits.output)} out
                <span className={`mc-evidence is-${m.limits.evidence}`}>{m.limits.evidence}</span>
              </td>
              <td><span className={`mc-state is-${m.enabled ? m.state : "off"}`}>{m.enabled ? m.state.replace("_", " ") : "switched off"}</span></td>
              <td className="mc-actions-cell"><div className="mc-actions">
                {!m.isDefault && m.enabled && m.selectable && (
                  <button className="btn ghost" disabled={!editable || !!busy}
                    onClick={() => void act(`d-${m.id}`, () => api.setDefaultModel(m.id), `${m.name} is now the default.`)}>Make default</button>
                )}
                <label className="mc-switch is-small">
                  <input type="checkbox" role="switch" checked={m.enabled} aria-label={`${m.name} enabled`}
                    disabled={!editable || !!busy || m.isDefault}
                    onChange={(e) => void act(`e-${m.id}`, () => api.setModelEnabled(m.id, e.target.checked),
                      `${m.name} ${e.target.checked ? "switched on" : "switched off"}.`)} />
                </label>
                <button className="btn ghost icon" aria-label={`Remove ${m.name}`} title={m.isDefault ? "Choose another default first" : "Remove"}
                  disabled={!editable || !!busy || m.isDefault}
                  onClick={() => { if (window.confirm(`Remove ${m.name} from the catalogue?`)) void act(`r-${m.id}`, () => api.removeModel(m.id), `${m.name} removed.`); }}>
                  <Trash size={14} />
                </button>
              </div></td>
            </tr>
          ))}
        </tbody>
      </table>

      {adding ? (
        <AddModel provider={provider} busy={busy === `add-${provider.id}`}
          onCancel={onAdd}
          onAdd={async (form, context, output, makeDefault) => {
            const saved = await act(`add-${provider.id}`, () => api.addModel({
              provider: provider.id, model: form.model.trim(), name: form.name.trim(), context, output, makeDefault,
            }), `${form.name.trim() || form.model.trim()} added.`);
            if (saved) onDone();
          }} />
      ) : (
        <div className="mc-foot">
          <button className="btn" disabled={!editable} onClick={onAdd}><Plus size={13} /> Add a model</button>
        </div>
      )}
    </section>
  );
}

function AddModel({ provider, busy, onAdd, onCancel }: {
  provider: ConfigProvider; busy: boolean; onCancel: () => void;
  onAdd: (form: NewModelForm, context: number, output: number, makeDefault: boolean) => Promise<void>;
}) {
  const uid = useId();
  const [form, setForm] = useState<NewModelForm>(EMPTY);
  const [touched, setTouched] = useState<Partial<Record<keyof NewModelForm, boolean>>>({});
  const [makeDefault, setMakeDefault] = useState(false);
  const result = validateNewModel(form);
  const set = (k: keyof NewModelForm) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const show = (k: keyof NewModelForm) => (touched[k] ? result.errors[k] : undefined);
  const touch = (k: keyof NewModelForm) => () => setTouched({ ...touched, [k]: true });
  const valid = Object.keys(result.errors).length === 0;

  return (
    <form className="mc-add" aria-label={`Add a model to ${provider.name}`}
      onSubmit={(e) => { e.preventDefault(); if (valid) void onAdd(form, result.context, result.output, makeDefault); }}>
      <h4>Add a model to {provider.name}</h4>
      <div className="mc-grid">
        <Field id={`${uid}-model`} label="Model name" error={show("model")}>
          <input id={`${uid}-model`} value={form.model} onChange={set("model")} onBlur={touch("model")} autoFocus
            spellCheck={false} placeholder={provider.example || "model-name"} aria-invalid={!!show("model")}
            aria-describedby={`${uid}-model-err`} />
        </Field>
        <Field id={`${uid}-name`} label={<>Display name <i>(optional)</i></>}>
          <input id={`${uid}-name`} value={form.name} onChange={set("name")} placeholder="as shown in the picker" />
        </Field>
        <Field id={`${uid}-context`} label="Context window" error={show("context")}>
          <input id={`${uid}-context`} value={form.context} onChange={set("context")} onBlur={touch("context")}
            placeholder="128k" aria-invalid={!!show("context")} aria-describedby={`${uid}-context-err`} />
        </Field>
        <Field id={`${uid}-output`} label="Max output" error={show("output")}>
          <input id={`${uid}-output`} value={form.output} onChange={set("output")} onBlur={touch("output")}
            placeholder="8k" aria-invalid={!!show("output")} aria-describedby={`${uid}-output-err`} />
        </Field>
      </div>
      <p className="mc-hint">
        The limits are recorded as <b>stated by you</b>: the app clamps every request to them, so a number
        larger than the provider allows makes turns fail after the wait.
      </p>
      <label className="mc-check"><input type="checkbox" checked={makeDefault} onChange={(e) => setMakeDefault(e.target.checked)} /> Make it the default model</label>
      <div className="mc-actions-row">
        <button type="submit" className="btn primary" disabled={!valid || busy}>{busy ? "Adding…" : "Add model"}</button>
        <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** A label, a control and its error as siblings: the error is the control's description, never part of
 *  its name (nesting it in the label made the accessible name "Max output The output limit …"). */
function Field({ id, label, error, children }: { id: string; label: ReactNode; error?: string; children: ReactNode }) {
  return (
    <div className="mc-field">
      <label htmlFor={id}>{label}</label>
      {children}
      <small id={`${id}-err`} className="mc-error" role={error ? "alert" : undefined}>{error}</small>
    </div>
  );
}
