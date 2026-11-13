import { createContext } from "react";
import type { Doc } from "../domain/docs";
import type { Workspace } from "../domain/links";

/** Lets any tool card open the notebook or file it touched, without prop-drilling through the transcript. */
/** The workspace this app is attached to, so any component can link to the same object in Databricks. */
export const WorkspaceLinks = createContext<Workspace | null>(null);

export const OpenDoc = createContext<(doc: Doc) => void>(() => {});

/** Explicit SQL promotion from an assistant code block; never executes the proposal. */
export const OpenSqlQuery = createContext<((text: string) => void) | null>(null);
