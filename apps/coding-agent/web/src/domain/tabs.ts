/** Tab order is metadata: moves retain the exact document objects and active identity. */
export const docTabId = (id: string) => `doc-tab-${encodeURIComponent(id)}`;

export function moveTab<T extends { id: string }>(items: T[], id: string, to: number): T[] {
  const from = items.findIndex((item) => item.id === id);
  if (from < 0 || !Number.isFinite(to)) return items;
  const index = Math.max(0, Math.min(items.length - 1, Math.trunc(to)));
  if (from === index) return items;
  const next = [...items];
  next.splice(from, 1);
  next.splice(index, 0, items[from]);
  return next;
}

/** Prefer the next surviving right neighbor, then the nearest left, then Home. */
export function afterClose<T extends { id: string }>(items: T[], active: string, removed: Set<string>): string {
  if (!removed.has(active)) return active;
  const at = items.findIndex((item) => item.id === active);
  return items.slice(at + 1).find((item) => !removed.has(item.id))?.id
    ?? items.slice(0, at).reverse().find((item) => !removed.has(item.id))?.id ?? "chat";
}
