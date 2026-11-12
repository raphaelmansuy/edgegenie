import { Database, FileIcon, Folder, Notebook, Table } from "./Icons";

/** Shared by tabs, attachment chips and mention pickers. */
export const KIND_ICON: Record<string, (p: { size?: number }) => React.ReactNode> = {
  notebook: Notebook, file: FileIcon, folder: Folder, table: Table, blob: FileIcon, cell: Notebook,
  query: Database, "query-draft": Database,
};
