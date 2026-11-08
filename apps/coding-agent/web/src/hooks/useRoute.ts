/** Keeps the address bar and the app's state in step, in both directions.
 *
 *  - On load, and whenever the hash changes (a pasted link, Back, Forward), `apply` moves the app to
 *    the route the address names.
 *  - Whenever the app's own route changes, the address is updated: a new entry for a move to
 *    somewhere else (so Back returns), and a quiet replacement when only the cell moved.
 *
 * The write waits until the first `apply` has run: otherwise the app's empty first state would
 * overwrite the very link that was opened.
 */
import { useEffect, useRef, useState } from "react";
import { formatRoute, parseRoute, type Route } from "../domain/route";

const withoutQuery = (hash: string) => hash.split("?")[0];

export function useRoute(current: Route, apply: (route: Route) => void) {
  const [ready, setReady] = useState(false);
  const applyRef = useRef(apply);
  applyRef.current = apply;

  useEffect(() => {
    applyRef.current(parseRoute(window.location.hash));
    setReady(true);
    const onHash = () => applyRef.current(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const want = formatRoute(current);
  useEffect(() => {
    if (!ready) return;
    const have = formatRoute(parseRoute(window.location.hash));
    if (want === have) return;
    const url = want || `${window.location.pathname}${window.location.search}`;
    if (withoutQuery(want) === withoutQuery(have)) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
  }, [ready, want]);
}
