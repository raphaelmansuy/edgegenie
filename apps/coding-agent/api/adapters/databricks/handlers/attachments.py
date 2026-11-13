"""Non-asset attachment shapes delegate notebook reads to the registered asset handler."""

from ....domain.asset import AssetRef
from ....domain.context import Resolved
from ....domain.binding import cell_text, content_sha, parse_cell_ref, render_cell
from ....domain.notebook import parse_source


class CellAttachmentReader:
    def __init__(self, notebook):
        self.notebook = notebook

    async def read(self, attachment, who):
        path, index = parse_cell_ref(attachment.ref)
        value = await self.notebook.read(AssetRef("notebook", path), who)
        cells = parse_source(value.content, value.language)
        source, language = cell_text(cells, index)
        text = render_cell(path, index, source, language, sha=content_sha(source), seen_sha=attachment.sha)
        return Resolved(
            attachment, text, f"one cell of {len(cells)}; read the others with the notebook tool"
        )


class FolderAttachmentReader:
    def __init__(self, workspace):
        self.workspace = workspace

    async def read(self, attachment, who):
        children = await self.workspace.list_dir(attachment.ref, who.token)
        lines = [f"{'/' if row.has_children else ''}{row.name}  [{row.kind}]" for row in children[:80]]
        more = f"\n... and {len(children) - 80} more" if len(children) > 80 else ""
        return Resolved(attachment, "\n".join(lines) + more or "(empty)")
