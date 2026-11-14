/** View intent is independent of focus, source and persistence. */
export interface MarkdownViewState { mode: "read" | "edit"; composing: boolean; pendingPreview: boolean; readOnly: boolean }
export type ViewEvent = { type: "edit" | "preview" | "compositionStart" | "compositionEnd" } | { type: "permission"; readOnly: boolean };
export const readingState: MarkdownViewState = { mode: "read", composing: false, pendingPreview: false, readOnly: false };
export function transition(state: MarkdownViewState, event: ViewEvent): MarkdownViewState {
  switch (event.type) {
    case "edit": return state.readOnly ? state : { ...state, mode: "edit", pendingPreview: false };
    case "preview": return state.composing ? { ...state, pendingPreview: true } : { ...state, mode: "read", pendingPreview: false };
    case "compositionStart": return { ...state, composing: true };
    case "compositionEnd": return { ...state, composing: false, mode: state.pendingPreview ? "read" : state.mode, pendingPreview: false };
    case "permission": return { ...state, readOnly: event.readOnly, mode: event.readOnly ? "read" : state.mode };
  }
}
