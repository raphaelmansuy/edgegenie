"""Blob stores: bytes the user handed us, addressed by an opaque id."""

from .files import FileBlobStore
from .memory import MemoryBlobStore

__all__ = ["FileBlobStore", "MemoryBlobStore"]
