export const stateLabel = (state: string) => state.replaceAll("_", " ");
export function Status({ state }: { state: string }) {
  return (
    <span className={`work-state state-${state}`}>{stateLabel(state)}</span>
  );
}
