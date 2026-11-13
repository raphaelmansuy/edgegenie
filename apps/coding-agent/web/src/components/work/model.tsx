import {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Attachment, SessionView } from "../../domain/events";
export interface Asset {
  kind: string;
  id: string;
}
export interface WorkRow {
  id: string;
  state: string;
  asset: Asset;
  reason?: string;
  diff?: string;
  baseRevision?: string;
  newRevision?: string;
  undoAvailable?: boolean;
  canRun?: boolean;
  tier?: string;
  nativeId?: string;
  ranAs?: string;
  lastObservedAt?: number;
  wakeup?: string;
  result?: unknown;
  action?: string;
  arguments?: Record<string, unknown>;
}
export interface Capability {
  kind: string;
  label: string;
  tier: string;
  read: boolean;
  change: boolean;
  run: boolean;
  reason?: string;
}
export interface Work {
  cursors?: Record<string, string>;
  mode: "plan" | "review" | "auto";
  budget?: {
    limit: number;
    unit: string;
  };
  usedTokens: number;
  usedCost: number;
  currency: string;
  toolCount: number;
  change: WorkRow[];
  operation: WorkRow[];
  resource: WorkRow[];
  approval: WorkRow[];
  capabilities: Capability[];
  fence: {
    folder: string;
    schema?: string;
  };
}
export interface Model {
  reviewing: boolean;
  setReviewing: (value: boolean) => void;
  data?: Work;
  error: string;
  busy: boolean;
  act: (path: string, body?: unknown) => Promise<void>;
  reload: () => Promise<void>;
}
export const SessionFeatures = createContext<Partial<SessionView>>({});
export const Context = createContext<Model>({
  reviewing: false,
  setReviewing: () => {},
  error: "",
  busy: false,
  act: async () => {},
  reload: async () => {},
});
export async function request(path: string, body?: unknown) {
  const response = await fetch(
    path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : result.detail?.message || "The request could not be completed.",
    );
  return result;
}
export const AttachAsset = createContext<(asset: Attachment) => void>(() => {});
export function AgentWorkProvider({
  session,
  children,
  onAttach,
}: {
  session: SessionView;
  children: ReactNode;
  onAttach?: (asset: Attachment) => void;
}) {
  const [reviewing, setReviewing] = useState(false);
  const [data, setData] = useState<Work>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const current = useRef(session.id);
  current.current = session.id;
  const prefix = `/api/sessions/${encodeURIComponent(session.id)}`;
  const reload = useCallback(async () => {
    if (!session.agentWork || !session.id) return;
    try {
      const next = await request(`${prefix}/work`);
      if (current.current === session.id) {
        setData(next);
        setError("");
      }
    } catch (e) {
      if (current.current === session.id)
        setError(String((e as Error).message));
    }
  }, [session.id, session.agentWork, prefix]);
  useEffect(() => {
    setData(undefined);
    setError("");
  }, [session.id]);
  useEffect(() => {
    void reload();
  }, [reload, session.workVersion]);
  useEffect(() => {
    if (!session.agentWork || !session.id) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible")
        void request(`${prefix}/keepalive`, {}).catch(() => {});
    }, 30000);
    return () => window.clearInterval(timer);
  }, [session.id, session.agentWork, prefix]);
  const act = useCallback(
    async (path: string, body: unknown = {}) => {
      setBusy(true);
      setError("");
      try {
        await request(`${prefix}/${path}`, body);
        await reload();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [prefix, reload],
  );
  return (
    <AttachAsset.Provider value={onAttach ?? (() => {})}>
      <SessionFeatures.Provider value={session}>
        <Context.Provider
          value={{ data, error, busy, act, reload, reviewing, setReviewing }}
        >
          {children}
        </Context.Provider>
      </SessionFeatures.Provider>
    </AttachAsset.Provider>
  );
}
export const SessionIdContext = createContext("");
