/** Navigation is not permission to fetch. Media uses an explicit, identity-scoped endpoint. */
export type Destination = { kind: "external" | "email" | "fragment" | "workspace" | "volume" | "blocked"; value: string; reason?: string };
export function destination(raw: string, documentPath = ""): Destination {
  const value = raw.trim();
  let decoded: string;
  try { decoded = decodeURIComponent(value); } catch { return { kind: "blocked", value, reason: "Invalid URL encoding" }; }
  if (/[\u0000-\u001f\u007f\\]/.test(decoded) || decoded.startsWith("//")) return { kind: "blocked", value, reason: "Unsupported or unsafe address" };
  if (value.startsWith("#")) return { kind: "fragment", value };
  if (/^https:\/\//i.test(value)) {
    try { const url = new URL(value); if (url.username || url.password) throw new Error(); return { kind: "external", value: url.href }; } catch { return { kind: "blocked", value, reason: "Invalid HTTPS address" }; }
  }
  if (/^mailto:[^<>\s]+$/i.test(value)) return { kind: "email", value };
  if (/^\/(?:Workspace|Users|Shared|Repos|Volumes)\//.test(value) || (/^\.\.?\//.test(value) && documentPath.startsWith("/"))) {
    const parts = (decoded.startsWith("/") ? decoded : `${documentPath.slice(0, documentPath.lastIndexOf("/"))}/${decoded}`).split("/");
    const normalized: string[] = [];
    for (const part of parts) {
      if (!part || part === ".") continue;
      if (part === "..") { if (normalized.length <= 1) return { kind: "blocked", value, reason: "Path leaves the workspace namespace" }; normalized.pop(); }
      else normalized.push(part);
    }
    const path = "/" + normalized.join("/");
    return { kind: normalized[0] === "Volumes" ? "volume" : "workspace", value: path };
  }
  return { kind: "blocked", value, reason: "Only HTTPS, email and workspace destinations are supported" };
}

export function headingId(namespace: string, ordinal: number): string {
  return `md-${encodeURIComponent(namespace).replace(/%/g, "_")}-${ordinal}`;
}
export function headingSlug(label: string): string { return label.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-"); }
