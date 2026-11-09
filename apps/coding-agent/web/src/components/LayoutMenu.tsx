/** Shell actions use the same focus and keyboard contract as document actions. */
import { memo } from "react";
import { display } from "../domain/keys";
import { LayoutGrid } from "./Icons";
import { ActionMenu } from "./ActionMenu";

interface Props {
  railVisible: boolean; dockVisible: boolean; inspectorVisible: boolean;
  onToggleRail: () => void; onToggleDock: () => void; onToggleInspector: () => void;
  onReset: () => void; onKeys: () => void; onRefresh: () => void; onFocus: () => void;
}
export const LayoutMenu = memo(function LayoutMenu(p: Props) {
  return <ActionMenu label="Layout and panels" actions={[
    { label: "Navigator", checked: p.railVisible, shortcut: display("mod+b"), onSelect: p.onToggleRail },
    { label: "Assistant", checked: p.dockVisible, shortcut: display("mod+j"), onSelect: p.onToggleDock },
    { label: "Context and audit", checked: p.inspectorVisible, shortcut: display("mod+i"), onSelect: p.onToggleInspector },
    null,
    { label: "Focus editor", onSelect: p.onFocus },
    { label: "Reset layout", onSelect: p.onReset },
    null,
    { label: "Keyboard shortcuts", shortcut: display("mod+slash"), onSelect: p.onKeys },
    { label: "Refresh sessions and models", onSelect: p.onRefresh },
  ]}><LayoutGrid size={16} /></ActionMenu>;
});
