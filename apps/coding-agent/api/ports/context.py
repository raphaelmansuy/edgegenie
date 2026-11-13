"""Owner-bound attachment readers; transport and content-family details stay in adapters."""

from typing import Protocol
from ..domain.context import Attachment, Resolved


class AttachmentReader(Protocol):
    async def read(self, attachment: Attachment) -> Resolved: ...
