/** A link to the same object in the Databricks workspace UI. Renders nothing when there is no workspace. */
import { useContext, type ReactNode } from "react";
import { workspaceUrl, type LinkTarget } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";

export function useWorkspaceUrl(t: LinkTarget): string | null {
  return workspaceUrl(useContext(WorkspaceLinks), t);
}

export function ExtLink({ target, className = "ext-link", children, label }: {
  target: LinkTarget; className?: string; children?: ReactNode; label?: string;
}) {
  const href = useWorkspaceUrl(target);
  if (!href) return null;
  return (
    <a className={className} href={href} target="_blank" rel="noopener noreferrer"
      title={label ?? "Open in Databricks"} aria-label={label ?? "Open in Databricks"}
      onClick={(e) => e.stopPropagation()}>
      {children ?? "↗"}
    </a>
  );
}
