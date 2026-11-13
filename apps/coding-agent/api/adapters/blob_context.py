"""User-supplied attachment bytes read only through their owner-scoped blob port."""

from ..domain.context import Resolved


class BlobAttachmentReader:
    def __init__(self, blobs):
        self.blobs = blobs

    async def read(self, attachment, who):
        if self.blobs is None:
            raise LookupError("this attachment is no longer available")
        try:
            row = await self.blobs.store.meta(attachment.ref, who.user_id)
            raw = await self.blobs.store.bytes_for(attachment.ref, who.user_id)
        except LookupError:
            raise LookupError("this attachment is no longer available") from None
        unseen = bool(getattr(row, "family", "") == "image" and not self.blobs.model_sees_images)
        text, note = await self.blobs.describe(row, raw, unseen=unseen)
        return Resolved(attachment, text, note)
