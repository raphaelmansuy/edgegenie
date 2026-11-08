/** May this user run Python cells? Asked of the server once per page, because the answer does not
 *  change while the page is open and every notebook on screen needs it. Until it arrives the answer is
 *  "no": a control that turns out to be forbidden is worse than one that appears a moment late. */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PythonPolicy } from "../domain/cellrun";

const PENDING: PythonPolicy = { enabled: false, reason: "checking whether Python can run here…" };
let known: Promise<PythonPolicy> | null = null;

export function pythonPolicy(): Promise<PythonPolicy> {
  known ??= api.me().then((me) => me.pythonRun ?? { enabled: false, reason: "Python cells cannot run in this app." })
    .catch(() => { known = null; return { enabled: false, reason: "Python cells could not be checked." }; });
  return known;
}

export function usePythonPolicy(): PythonPolicy {
  const [policy, setPolicy] = useState(PENDING);
  useEffect(() => {
    let live = true;
    void pythonPolicy().then((p) => live && setPolicy(p));
    return () => { live = false; };
  }, []);
  return policy;
}
