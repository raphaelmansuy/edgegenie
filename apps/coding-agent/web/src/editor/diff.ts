/** The smallest single replacement that turns `from` into `to`, or null when they are equal. Pure.
 *
 * Common prefix and suffix are kept, so the user's caret and selection (which CodeMirror maps through
 * a change) survive an outside edit that does not touch them.
 */
export function minimalChange(from: string, to: string): { from: number; to: number; insert: string } | null {
  if (from === to) return null;
  const max = Math.min(from.length, to.length);
  let a = 0;
  while (a < max && from.charCodeAt(a) === to.charCodeAt(a)) a++;
  let b = 0;
  while (b < max - a && from.charCodeAt(from.length - 1 - b) === to.charCodeAt(to.length - 1 - b)) b++;
  return { from: a, to: from.length - b, insert: to.slice(a, to.length - b) };
}
