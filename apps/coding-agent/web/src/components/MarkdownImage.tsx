import { useEffect, useRef, useState } from "react";
import { destination } from "../domain/markdown/policy";
import { MEDIA_LIMITS, readRaster, withMediaSlot } from "../domain/markdown/media";

/** No fetch on render. User-activated loads are bounded and never use another principal. */
export function MarkdownImage({ source, alt, documentPath }: { source: string; alt: string; documentPath: string }) {
  const [state, setState] = useState<{ status: "idle" | "loading" | "ready" | "failed" | "denied"; url?: string; error?: string }>({ status: "idle" });
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const objectUrl = useRef("");
  useEffect(() => {
    setState({ status: "idle" });
    return () => { generation.current++; request.current?.abort(); if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); objectUrl.current = ""; };
  }, [source, documentPath]);
  const target = destination(source, documentPath);
  const allowed = ["external", "workspace", "volume"].includes(target.kind);
  const load = async () => {
    if (!allowed || state.status === "loading") return;
    if (objectUrl.current) { URL.revokeObjectURL(objectUrl.current); objectUrl.current = ""; }
    const current = ++generation.current;
    const controller = new AbortController(); request.current = controller;
    const timer = window.setTimeout(() => controller.abort(), MEDIA_LIMITS.timeout);
    setState({ status: "loading" });
    try {
      const external = target.kind === "external";
      const url = external ? target.value : `/api/workspace/markdown-image?path=${encodeURIComponent(target.value)}`;
      const response = await withMediaSlot(controller.signal, async () => {
        const response = await fetch(url, { signal: controller.signal, credentials: external ? "omit" : "same-origin", referrerPolicy: "no-referrer", redirect: "error" });
        // Keep the slot through body validation, rather than only until headers arrive.
        if (!response.ok) return { response, blob: null };
        return { response, blob: await readRaster(response) };
      });
      const denied = response.response.status === 401 || response.response.status === 403;
      try {
        const blob = response.blob ?? await readRaster(response.response);
        if (generation.current !== current) return;
        objectUrl.current = URL.createObjectURL(blob);
        setState({ status: "ready", url: objectUrl.current });
      } catch (e) {
        if (generation.current === current) setState({ status: denied ? "denied" : "failed", error: e instanceof Error ? e.message : "Image unavailable" });
      }
    } catch { if (generation.current === current) setState({ status: "failed", error: "Image request failed or timed out. The source is unchanged." }); }
    finally { window.clearTimeout(timer); }
  };
  return <span className={`markdown-image is-${state.status}`} role="group" aria-label={alt || "Markdown image"}>
    {state.status === "ready" ? <img src={state.url} alt={alt} referrerPolicy="no-referrer" onError={() => setState({ status: "failed", error: "Image could not be decoded." })} /> : <>
      <span className="markdown-image-alt">{alt || "Image without a description"}</span>
      <span className="markdown-image-source">{source}</span>
      <span role="status">{state.status === "loading" ? "Loading image…" : state.error || (target.kind === "external" ? "External image. Loading shares your IP address with this host." : allowed ? "Image not loaded. Uses your workspace permissions." : target.reason)}</span>
      {allowed && state.status !== "denied" && <button type="button" className="btn sm" disabled={state.status === "loading"} onClick={() => void load()}>{state.status === "failed" ? "Retry image" : "Load image"}</button>}
    </>}
  </span>;
}
