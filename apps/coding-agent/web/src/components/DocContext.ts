import { createContext } from "react";
import type { Doc } from "../domain/docs";

/** Lets any tool card open the notebook or file it touched, without prop-drilling through the transcript. */
export const OpenDoc = createContext<(doc: Doc) => void>(() => {});
