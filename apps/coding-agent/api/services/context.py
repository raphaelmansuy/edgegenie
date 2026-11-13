"""Resolve attachments through injected readers; per-item failure never hides missing context."""

from __future__ import annotations
import asyncio
from ..domain.asset import AssetRef
from ..domain.context import Attachment, Resolved
from ..ports.context import AttachmentReader


class RegistryContextReader:
    """Asset reads have exactly the same handler as tools, routes and capability probing."""

    def __init__(self, registry, actor, extensions=None):
        self.registry, self.actor = registry, actor
        self.extensions = extensions or {}

    async def read(self, attachment: Attachment) -> Resolved:
        extension = self.extensions.get(attachment.kind)
        if extension:
            return await extension.read(attachment, self.actor)
        value = await self.registry.handler(attachment.kind).read(
            AssetRef(attachment.kind, attachment.ref), self.actor
        )
        return Resolved(
            attachment,
            value.content,
            "Asset revision " + value.revision + "; read the rest with dbx_read when capped.",
        )


async def resolve(items: list[Attachment], reader: AttachmentReader) -> list[Resolved]:
    """Every item is read as its owner. An unreadable item is explicit, never an empty success."""

    async def one(item):
        try:
            return await reader.read(item)
        except (PermissionError, LookupError, IsADirectoryError) as exc:
            return Resolved(item, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - preserve other readable attachments
            return Resolved(item, error=f"{type(exc).__name__}: {str(exc)[:120]}")

    return list(await asyncio.gather(*(one(item) for item in items)))
