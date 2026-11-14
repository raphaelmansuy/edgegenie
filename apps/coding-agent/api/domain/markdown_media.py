"""Bounded raster metadata validation. Never execute/decode SVG or trust a filename MIME."""
import struct

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def validate_raster(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError("image exceeds the 5 MiB limit")
    width = height = 0
    mime = ""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        # Animated PNG is deliberately unsupported; it has a separate animation control chunk.
        at = 8
        while at + 12 <= len(data):
            size = struct.unpack_from(">I", data, at)[0]
            if data[at + 4:at + 8] == b"acTL":
                raise ValueError("animated images are not supported")
            at += size + 12
        width, height = struct.unpack_from(">II", data, 16)
        mime = "image/png"
    elif data[:2] == b"\xff\xd8":
        at = 2
        while at + 8 < len(data):
            if data[at] != 255:
                break
            while at < len(data) and data[at] == 255:
                at += 1
            if at >= len(data):
                break
            marker = data[at]
            at += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 1 or 0xD0 <= marker <= 0xD7:
                continue
            if at + 2 > len(data):
                break
            size = struct.unpack_from(">H", data, at)[0]
            if size < 2 or at + size > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack_from(">HH", data, at + 3)
                mime = "image/jpeg"
                break
            at += size
    if not mime or not width or not height:
        raise ValueError("only valid PNG and JPEG images are supported")
    if width * height > MAX_PIXELS:
        raise ValueError("image exceeds the 16 megapixel limit")
    return mime
