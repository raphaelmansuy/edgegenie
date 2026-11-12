/** A job's dependency graph, drawn as levels.
 *
 *  A node-link diagram is unreadable in a 470 px column at the sizes this app runs, and it cannot be
 *  selected as text. Levels plus an explicit `after X` on each task carry the same information, stay
 *  legible at 620 px, and are copyable — which is what a user does with a graph they are debugging
 *  (spec 014 [JOB-3], and 04 §What is deliberately absent).
 *
 *  The levels come from `taskLevels()`, the same function the tool server validates with, so a graph the
 *  validator accepted cannot render as cyclic — and a cyclic one renders as a refusal, never as a partial
 *  picture ([RB-5]).
 */
import type { JobTask } from "../api/client";
import { taskLevels } from "../domain/jobs";
import { Alert } from "./Icons";

/** The one thing a task runs, in the words a person would use. */
export function taskTarget(task: JobTask): { kind: string; value: string } {
  if (task.notebook_path) return { kind: "notebook", value: task.notebook_path };
  if (task.python_file) return { kind: "python", value: task.python_file };
  if (task.sql_file) return { kind: "sql file", value: task.sql_file };
  if (task.pipeline_id) return { kind: "pipeline", value: task.pipeline_id };
  if (task.job_id) return { kind: "job", value: String(task.job_id) };
  return { kind: "unset", value: "no task type — this job cannot run" };
}

/** The last segment of a path, so a row reads `silver` rather than a 60-character path. */
const leaf = (path: string): string => path.split("/").filter(Boolean).pop() ?? path;

export function JobGraph({ tasks, levels, problem }: {
  tasks: JobTask[];
  /** Precomputed levels from the server, when it sent them. Falls back to computing locally, which is
   *  the same function — the fallback exists so a page renders while one block is still loading. */
  levels?: string[][];
  problem?: string | null;
}) {
  const byKey = new Map(tasks.map((t) => [t.task_key, t]));
  const drawn = problem ? [] : (levels ?? taskLevels(tasks));

  if (problem) {
    return (
      <div className="job-graph is-invalid" role="alert">
        <Alert size={14} />
        <div>
          <span>{problem}</span>
          <p className="infra-note">
            This job cannot run as defined. The graph is not drawn, because a partial picture of a broken
            job reads as a job that is merely small.
          </p>
        </div>
      </div>
    );
  }

  if (!drawn.length) {
    return <p className="infra-block-empty">No tasks. The agent has not built this job&rsquo;s graph yet.</p>;
  }

  return (
    <div className="job-graph" role="list" aria-label="Tasks by dependency level">
      {drawn.map((level, depth) => (
        <div className="job-level" key={`level-${depth}`} role="listitem">
          <span className="job-level-index" aria-hidden>{depth + 1}</span>
          <div className="job-level-tasks">
            {level.map((key) => {
              const task = byKey.get(key);
              const target = task ? taskTarget(task) : { kind: "missing", value: key };
              const after = task?.depends_on ?? [];
              return (
                <div className="job-task" key={key}>
                  <span className="job-task-key">{key}</span>
                  <span className="job-task-kind">{target.kind}</span>
                  <span className="job-task-target" title={target.value}>{leaf(target.value)}</span>
                  {after.length > 0 && (
                    <span className="job-task-after" title={after.join(", ")}>
                      after {after.join(", ")}
                    </span>
                  )}
                  {(task?.max_retries ?? 0) > 0 && (
                    <span className="infra-tag quiet">{task?.max_retries} retries</span>
                  )}
                  {(task?.timeout_seconds ?? 0) > 0 && (
                    <span className="infra-tag quiet">{task?.timeout_seconds}s timeout</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
