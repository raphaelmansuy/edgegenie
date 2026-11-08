/** Which folder an `@` search starts from. Pure.
 *
 * The bug this fixes: `api.search(query)` was called with no root, so the server defaulted to the
 * user's home folder — files under /Shared or /Repos were simply not findable from the picker
 * (spec 006 FX-6).
 *
 * Precedence, most specific first:
 *   1. the folder of the open document — you are looking at it, you are naming its neighbours;
 *   2. the session's working folder — where the agent writes, so where new files appear;
 *   3. the user's home — the honest default when there is nothing else.
 */
import { folderOf, type Focus } from "./focus";

export function searchRoot(focus: Focus, sessionFolder: string, home: string): string {
  const fromDoc = folderOf(focus);
  if (fromDoc) return fromDoc;
  if (sessionFolder) return sessionFolder;
  return home;
}
