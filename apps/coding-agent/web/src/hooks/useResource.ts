/** One fetched value and its three states, spelled once.
 *
 *  Nine call sites in this spec need `loading → ready → error` plus a reload, and writing that by hand
 *  nine times is nine places to get three things wrong: an out-of-date response painting over a newer
 *  one, a component setting state after it unmounted, and a reload that does not clear the old error.
 *
 *  The generation counter is the load-bearing part, not the `AbortController`. A document remounts on a
 *  different id (the `key` trick `LakebasePage` uses), but a RE-POLL of the same document does not — so
 *  two requests for one key can be in flight and only the newer one may write. The counter makes that
 *  impossible; the abort makes it cheap.
 *
 *  Kept deliberately small: `{ state, data, error, reload }` and no cache. A cache here would be a second
 *  cache beside the server's, with its own staleness rules. The server already has one, keyed by token.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type ResourceState = "loading" | "ready" | "error";

export interface Resource<T> {
  state: ResourceState;
  /** Undefined until the first answer. Kept across a reload so a refresh does not blank the page. */
  data?: T;
  error?: string;
  reload: () => void;
  /** True while a reload is in flight over existing data, so a control can say "Refreshing…". */
  refreshing: boolean;
}

/**
 * `useResource(key, fetcher)`.
 *
 * `key` is the identity of what is being read: a URL, or a string built from one. When it changes the
 * hook reloads. Passing `null` skips the fetch entirely — that is how a page says "this block needs a
 * fact I do not have yet" without a conditional hook.
 */
export function useResource<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: { initial?: T } = {},
): Resource<T> {
  const [state, setState] = useState<ResourceState>(key === null ? "ready" : "loading");
  const [data, setData] = useState<T | undefined>(options.initial);
  const [error, setError] = useState<string | undefined>(undefined);
  const [tick, setTick] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // The generation is what makes a late answer harmless. `useRef`, not state: changing it must not render.
  const generation = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  // `fetcher` is deliberately not a dependency: it is usually an inline arrow closure, and depending on it
  // would refetch on every render. The KEY is the identity, which is the honest dependency.
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;
  const initial = useRef(options.initial);

  useEffect(() => {
    if (key === null) {
      setState("ready");
      setData(initial.current);
      setError(undefined);
      return;
    }
    const mine = ++generation.current;
    const controller = new AbortController();
    // A reload over existing data keeps the data on screen and says it is refreshing; a first load shows
    // a skeleton. Blanking a page to refresh it is how a user loses the value they were reading.
    setRefreshing(data !== undefined);
    if (data === undefined) setState("loading");
    setError(undefined);

    fetchRef.current(controller.signal)
      .then((value) => {
        if (!mounted.current || mine !== generation.current) return;
        setData(value);
        setState("ready");
        setRefreshing(false);
      })
      .catch((exc: unknown) => {
        if (!mounted.current || mine !== generation.current) return;
        if (controller.signal.aborted) return;
        setError(exc instanceof Error ? exc.message : "could not read this");
        setState("error");
        setRefreshing(false);
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  return { state, data, error, reload, refreshing };
}
