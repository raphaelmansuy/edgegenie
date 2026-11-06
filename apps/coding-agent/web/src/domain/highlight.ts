/** A deliberately small syntax highlighter: comments, strings, numbers, keywords. No dependencies.
 *
 * Highlighting is decoration; it must never alter the text. `tokenize(x).map(t => t.text).join("")`
 * equals x for every input, which the tests assert.
 */
export type TokenClass = "comment" | "string" | "number" | "keyword" | "plain";
export interface Token { text: string; cls: TokenClass }

const KEYWORDS: Record<string, string[]> = {
  python: ("and as assert async await break class continue def del elif else except False finally for from global if import in is " +
    "lambda None nonlocal not or pass raise return True try while with yield print").split(" "),
  sql: ("select from where group by order having limit join left right inner outer full on as and or not in is null like between " +
    "case when then else end union all distinct insert into values update set delete create table view replace temp or with " +
    "alter drop show describe use catalog schema using partitioned over partition count sum avg min max desc asc").split(" "),
  scala: "val var def class object trait extends with import if else for while match case return new null true false".split(" "),
  r: "function if else for while return library TRUE FALSE NULL".split(" "),
};

const COMMENT: Record<string, string> = {
  python: String.raw`#[^\n]*`, r: String.raw`#[^\n]*`, sql: String.raw`--[^\n]*|/\*[\s\S]*?\*/`, scala: String.raw`//[^\n]*|/\*[\s\S]*?\*/`,
};
const STRING_PY = String.raw`"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'`;
const STRING_SQL = String.raw`'(?:''|[^'])*'|"(?:\\.|[^"\\\n])*"|\x60[^\x60\n]*\x60`;

const cache = new Map<string, RegExp>();

function matcher(lang: string): RegExp {
  let re = cache.get(lang);
  if (!re) {
    const strings = lang === "sql" ? STRING_SQL : STRING_PY;
    re = new RegExp(`(${COMMENT[lang]})|(${strings})|(\\b\\d[\\d_]*(?:\\.\\d+)?\\b)|(\\b[A-Za-z_][A-Za-z0-9_]*\\b)`, "g");
    cache.set(lang, re);
  }
  re.lastIndex = 0;
  return re;
}

export function tokenize(text: string, language: string): Token[] {
  const lang = language.toLowerCase();
  if (!(lang in COMMENT)) return [{ text, cls: "plain" }];       // shell, fs, pip, markdown...: leave alone
  const kw = new Set((KEYWORDS[lang] ?? []).map((k) => (lang === "sql" ? k.toLowerCase() : k)));
  const out: Token[] = [];
  const re = matcher(lang);
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), cls: "plain" });
    const cls: TokenClass = m[1] !== undefined ? "comment" : m[2] !== undefined ? "string" : m[3] !== undefined ? "number"
      : kw.has(lang === "sql" ? m[4].toLowerCase() : m[4]) ? "keyword" : "plain";
    out.push({ text: m[0], cls });
    last = m.index + m[0].length;
    if (m[0].length === 0) re.lastIndex++;                          // never loop on an empty match
  }
  if (last < text.length) out.push({ text: text.slice(last), cls: "plain" });
  return out;
}
