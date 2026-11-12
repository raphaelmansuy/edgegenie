/** The scaffold step definitions, as a typed module.
 *
 * This JSON is the single definition: the Python twin (`api/domain/scaffold.py`) reads the same file,
 * which is what keeps one rule in two runtimes from drifting (spec 013 [07 §2.1]). It lives beside
 * the TypeScript module that consumes it, and the Python side reaches it by path.
 */
declare module "./scaffold-steps.json" {
  interface ScaffoldStep {
    key: string;
    label: string;
    detail: string;
    tools: string[];
    proof: string;
    alt_proof?: string[];
    why: string;
  }
  const value: { steps: ScaffoldStep[] };
  export default value;
}
