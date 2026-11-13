"""Choose attachment adapters, including the compatibility path when agent-work is disabled."""

from ..adapters.databricks.handlers.workspace import WorkspaceHandler
from ..adapters.databricks.handlers.table import TableHandler
from ..adapters.databricks.handlers.sql import QueryHandler
from ..adapters.databricks.handlers.attachments import CellAttachmentReader, FolderAttachmentReader
from ..adapters.blob_context import BlobAttachmentReader
from ..domain.asset import Actor
from ..domain.asset_registry import AssetRegistry, Registration
from ..domain.scope import Scope
from ..services.context import RegistryContextReader


def build_attachment_reader(
    workspace=None,
    catalog=None,
    token=None,
    *,
    blobs=None,
    user_id="",
    sql=None,
    sql_actor=None,
    registry=None,
    actor=None,
):
    who = actor or Actor(
        "attachment",
        sql_actor.user if sql_actor else user_id,
        "",
        Scope.for_session("attachment", "", None),
        workspace=sql_actor.workspace if sql_actor else "",
        token=sql_actor.token if sql_actor else token,
        username=sql_actor.run_as if sql_actor else user_id,
    )
    if registry is None:
        registry = AssetRegistry(
            [
                Registration(
                    "notebook",
                    "Notebooks",
                    "workspace.workspace",
                    WorkspaceHandler(workspace, "notebook"),
                    "",
                ),
                Registration(
                    "file", "Files", "workspace.workspace", WorkspaceHandler(workspace, "file"), ""
                ),
                Registration("table", "Tables", "catalog.tables:read", TableHandler(catalog), ""),
                Registration("query", "Queries", "sql", QueryHandler(sql), ""),
                Registration("query-draft", "Query drafts", "sql", QueryHandler(sql, "query-draft"), ""),
            ]
        )
    return RegistryContextReader(
        registry,
        who,
        {
            "cell": CellAttachmentReader(registry.handler("notebook")),
            "folder": FolderAttachmentReader(workspace),
            "blob": BlobAttachmentReader(blobs),
        },
    )
