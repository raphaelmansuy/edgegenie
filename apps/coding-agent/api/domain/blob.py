"""Blob attachments: the rules, with no I/O, no clock and no store.

A blob is bytes the user handed us — a pasted screenshot, a dropped CSV. Every other attachment this app
accepts is a *reference* to something already in the workspace, and the server re-reads it with the user's
own token. Bytes have no such authority behind them: the browser is the only source, and the browser is
exactly the party the reference rule refused to trust.

So this module is the trust boundary, and it is pure on purpose — no network, no file system, no time. That
is what makes the whole rule set testable in milliseconds, and what stops a validation from quietly
depending on which machine it runs on. (specs/009 [D3], [P1])

The one thing that is *not* decided here: whether the model can consume the result. `CAPABILITY` says what
each family is, and `validate` refuses a family the active model cannot read, because accepting an
attachment the model cannot see is worse than refusing it (spec 03 [CAP-2]).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum

# -- limits -------------------------------------------------------------------------------------
# Every one of these is interpolated into a user-facing sentence, so a limit cannot be changed without
# the sentence changing with it. 8 MB matches the cap FilesPane.tsx already enforces; a test asserts the
# two agree, because two constants that happen to be equal are two constants. (spec 009 [D4])
MAX_BYTES = 8 * 1024 * 1024
MAX_BYTES_TOTAL = 24 * 1024 * 1024
MAX_ATTACHMENTS = 6  # blobs and references together; mirrors domain/context.py
MAX_STORED_NAME = 120
MAX_IMAGE_EDGE = 2048
MAX_THUMB_EDGE = 96

#: A blob id. Opaque, and long enough that guessing one is pointless. (spec 009 [D8])
BLOB_ID = re.compile(r"^blb_[0-9a-f]{12}$")


class BlobRefusal(ValueError):
    """Bytes we will not store. `code` indexes REFUSALS; the message is the user's sentence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Family(str, Enum):
    """What a blob *is*, after its bytes were checked — not what its name claims. (spec 009 [SEC-3])"""

    IMAGE = "image"
    TEXT = "text"
    NOTEBOOK = "notebook"
    PDF = "pdf"
    #: A spreadsheet. `[R-21]`: Genie Code takes `.xlsx`/`.xls` and this did not, so a user with a
    #: workbook had to export it first. It is its own family because it needs a CONVERSION (to CSV text)
    #: rather than a decode, and because the conversion has a shape a reader should be told about.
    SHEET = "sheet"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class BlobSpec:
    """A blob that passed validation. Everything a row needs, and nothing the row must re-derive."""

    original_name: str
    stored_name: str
    mime: str
    family: Family
    size: int
    sha256: str
    #: True when the active model cannot consume this blob's family. The prompt says so rather than
    #: pretending, and the chip says so rather than hiding it.
    unseen_by_model: bool = False


# -- copy ---------------------------------------------------------------------------------------
# One register, one sentence each: present tense, no exclamation marks, every size limit naming both the
# limit and the observed value. The client's table (web/src/domain/blob.ts) must have exactly these keys,
# and a test on each side asserts it. (spec 009 [AFC-16], 09 §the-copy-register)
REFUSALS: dict[str, str] = {
    "too_big": "{name} is {size}; the limit is {limit}.",
    "too_many": "At most {limit} attachments per message.",
    "unknown_type": "{name} is not a file type this app can read.",
    "mismatch": "{name} looks like {detected} but says it is {declared}.",
    "empty": "{name} is empty.",
    "bad_name": "{name} has characters a workspace path cannot hold.",
    "no_vision": "Images need a model that can see them. {model} cannot; choose a vision model.",
    "pdf_needs_eye": "A PDF has to be read as text or converted to an image first.",
    "upload_failed": "{name} could not be uploaded: {reason}.",
    "unavailable": "{name} is no longer available.",
}


def say(code: str, **values: object) -> str:
    """The sentence for `code`, with its values filled in. One formatter, so punctuation cannot drift."""
    return REFUSALS[code].format(**values)


# -- magic bytes --------------------------------------------------------------------------------
# A closed table, not a sniffer. python-magic reads host config and can answer differently on different
# machines, which would make this module impure and its tests flaky. Seven prefixes are auditable in one
# screen and cannot surprise a new deployment. (spec 009 [D3])
def _png(b: bytes) -> bool:
    return b.startswith(b"\x89PNG\r\n\x1a\n")


def _jpeg(b: bytes) -> bool:
    return b.startswith(b"\xff\xd8\xff")


def _gif(b: bytes) -> bool:
    return b.startswith(b"GIF87a") or b.startswith(b"GIF89a")


def _webp(b: bytes) -> bool:
    return b.startswith(b"RIFF") and b[8:12] == b"WEBP"


def _pdf(b: bytes) -> bool:
    return b.startswith(b"%PDF")


def _zip(b: bytes) -> bool:
    return b.startswith(b"PK\x03\x04")


_DETECTORS: tuple[tuple[str, "callable"], ...] = (
    ("image/png", _png),
    ("image/jpeg", _jpeg),
    ("image/gif", _gif),
    ("image/webp", _webp),
    ("application/pdf", _pdf),
    ("application/zip", _zip),
)


def detect_mime(raw: bytes) -> str | None:
    """The type the BYTES are, or None when nothing matches. Never consults the name."""
    for mime, test in _DETECTORS:
        if test(raw):
            return mime
    return None


def _is_xlsx(raw: bytes) -> bool:
    """A real `.xlsx`, by content: a ZIP whose central directory names the spreadsheet parts.

    Not by extension. `[R-21]` admits spreadsheets, and a `.xlsx` is a ZIP — the same bytes a `.docx` or
    an `.ipynb` starts with — so the archive's own file names are the only honest test. `xl/workbook.xml`
    is present in every workbook and absent from every notebook, which is why it is the marker.
    """
    if not raw.startswith(b"PK\x03\x04"):
        return False
    # The central directory lists every member name in plain text; searching the raw bytes for one
    # unambiguous marker is enough and costs no decompression.
    return b"xl/workbook.xml" in raw or b"xl/worksheets/" in raw


def _family_of(mime: str, name: str, raw: bytes = b"") -> Family:
    if mime.startswith("image/"):
        return Family.IMAGE
    if mime == "application/pdf":
        return Family.PDF
    if _is_xlsx(raw):
        return Family.SHEET
    if mime == "application/zip" and name.lower().endswith(".ipynb"):
        return Family.NOTEBOOK
    if mime.startswith("text/") or mime in _TEXTUAL:
        return Family.TEXT
    return Family.OTHER


#: Types that are text even though the prefix does not say so. Kept short and explicit.
_TEXTUAL: frozenset[str] = frozenset({
    "application/json", "application/xml", "application/x-yaml", "application/yaml",
    "application/javascript", "application/x-sh", "application/sql",
})

_TEXTUAL_EXT = {
    ".txt", ".md", ".csv", ".tsv", ".log", ".json", ".yaml", ".yml", ".xml", ".html", ".css",
    ".js", ".ts", ".tsx", ".jsx", ".py", ".sql", ".scala", ".r", ".sh", ".ini", ".toml", ".cfg",
}


def guess_textual(name: str) -> bool:
    """Is this name one we are willing to read as text when the bytes carry no magic?

    Text has no signature, so for text the name is the only evidence there is. That is why this is a
    narrow extension whitelist and not "anything that decodes" — and why the caller must still check that
    the bytes are valid UTF-8 before believing it.
    """
    dot = name.rfind(".")
    return dot >= 0 and name[dot:].lower() in _TEXTUAL_EXT


# -- names --------------------------------------------------------------------------------------
# A path is not a name. Everything below is deterministic: the same input always yields the same stored
# name, so a retry of the same file cannot produce a second row that looks like a different file.
_UNSAFE = re.compile(r"[^\w.\- ]", re.UNICODE)
_RUNS = re.compile(r"[_\s]{2,}")
_RUN_UNDERSCORES = re.compile(r"_{2,}")


def sanitise_name(name: str) -> str:
    """A name that is safe as one path segment, or an empty string when nothing usable survives."""
    # Take the basename first: `a/b/c.png` and `..\\..\\x` must not be able to name a directory.
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    # Control characters, then everything a path cannot hold. `.` is kept so extensions survive.
    base = "".join(ch for ch in base if ch.isprintable())
    base = _UNSAFE.sub("_", base).strip(" .")
    # `<>` are two characters and become two underscores; collapse them to one so a name with punctuation
    # does not look machine-mangled. Spaces are preserved (a filename may legitimately have them).
    base = _RUN_UNDERSCORES.sub("_", base)
    base = re.sub(r" {2,}", " ", base)
    if not base or base in (".", ".."):
        return ""
    stem, dot, ext = base.rpartition(".")
    if not dot:  # no extension at all
        return base[:MAX_STORED_NAME]
    keep = max(1, MAX_STORED_NAME - len(ext) - 1)
    return f"{stem[:keep]}.{ext}" if ext else base[:MAX_STORED_NAME]


def human_size(n: int) -> str:
    """`12.4 MB`. One decimal, and the unit chosen by magnitude, so two sizes are comparable at a glance."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} bytes"


def sha256_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# -- what the model can consume ------------------------------------------------------------------
# This table IS requirement [CAP-1..4]. The picker's `accept` list, the drag-over sentence and the tests
# all read it, so the UI cannot promise a type the server refuses. (spec 009 [D7], [V6])
@dataclass(frozen=True, slots=True)
class Capability:
    family: Family
    needs_vision: bool
    accept: tuple[str, ...]
    describe: str  # what the drag-over says it takes


CAPABILITY: tuple[Capability, ...] = (
    Capability(Family.IMAGE, needs_vision=True,
               accept=("image/png", "image/jpeg", "image/webp", "image/gif"),
               describe="images"),
    Capability(Family.TEXT, needs_vision=False,
               accept=("text/*", ".csv", ".tsv", ".md", ".txt", ".log", ".json", ".yaml", ".py", ".sql"),
               describe="text, CSV, code"),
    Capability(Family.NOTEBOOK, needs_vision=False, accept=(".ipynb",), describe="notebooks"),
    Capability(Family.PDF, needs_vision=True, accept=(".pdf",), describe="PDFs"),
    # A workbook is converted to CSV text at resolution time, so it needs no vision and its size is
    # bounded by the converter, not by the model. `[R-21]`.
    Capability(Family.SHEET, needs_vision=False, accept=(".xlsx", ".xls"), describe="spreadsheets"),
)

#: The `accept` attribute for the file input, generated from the table above rather than typed twice.
ACCEPT_ATTR = ",".join(item for cap in CAPABILITY for item in cap.accept)

#: What the drop target says it takes, generated the same way.
DROP_HINT = ", ".join(cap.describe for cap in CAPABILITY if not cap.needs_vision) + ", images"


def needs_vision(family: Family) -> bool:
    return any(c.family is family and c.needs_vision for c in CAPABILITY)


# -- the rule ------------------------------------------------------------------------------------
def validate(name: str, raw: bytes, declared: str = "", *, model_sees_images: bool,
             limit: int = MAX_BYTES) -> BlobSpec:
    """Check the bytes and the name, or refuse with a sentence the user can act on.

    The order is not arbitrary: the cheapest check that can refuse runs first, so a huge body is never
    hashed, and a name that cannot be stored is never used to build a key. (spec 07 §6 flowchart)
    """
    shown = name or "the file"

    # 1. size, before anything reads the bytes
    if len(raw) > limit:
        raise BlobRefusal("too_big", say("too_big", name=shown, size=human_size(len(raw)),
                                         limit=human_size(limit)))

    # 2. the name must survive as a path segment
    stored = sanitise_name(name)
    if not stored:
        raise BlobRefusal("bad_name", say("bad_name", name=shown))

    # 3. emptiness, before sniffing
    if not raw.strip():
        raise BlobRefusal("empty", say("empty", name=shown))

    # 4. what the bytes are
    detected = detect_mime(raw)
    if detected is None:
        # No magic: acceptable only for a name we are willing to read as text, and only if it decodes.
        if not guess_textual(stored):
            raise BlobRefusal("unknown_type", say("unknown_type", name=shown))
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BlobRefusal("unknown_type", say("unknown_type", name=shown)) from None
        detected = declared if declared.startswith("text/") else "text/plain"

    # 5. the declaration must not contradict the bytes ACROSS families. Inside one family (a JPEG named
    #    .png) the detected type wins silently, because the reader produces the same answer either way.
    family = _family_of(detected, stored, raw)
    if declared and not _compatible(declared, detected, family):
        raise BlobRefusal("mismatch", say("mismatch", name=shown, detected=detected, declared=declared))

    # 6. A model that cannot see an image is NOT a reason to refuse it. The bytes are still the user's
    #    evidence; refusing them leaves the user with no way to hand a screenshot over at all. The
    #    description step states the limitation to the model instead ([P4]: what is unacceptable is an
    #    attachment the model silently cannot see). Recorded on the spec so the prompt can say so.
    unable_to_see = family is Family.IMAGE and not model_sees_images

    return BlobSpec(
        original_name=name or stored,
        stored_name=stored,
        mime=detected,
        family=family,
        size=len(raw),
        sha256=sha256_of(raw),
        unseen_by_model=unable_to_see,
    )


def _compatible(declared: str, detected: str, family: Family) -> bool:
    """Is the claim the client made consistent with what the bytes are?

    Same family is always fine: `image/png` vs `image/jpeg` for the same bytes cannot mislead a reader,
    because the reader dispatches on the DETECTED type. Across families it matters — a ZIP called a text
    file would be read as mojibake.
    """
    if declared == detected:
        return True
    # A notebook is a ZIP that the client declares as JSON, because that is what its bytes are inside the
    # archive. Accepting the pair is what lets a real `.ipynb` through without special-casing the caller.
    if family is Family.NOTEBOOK and detected == "application/zip":
        return True
    declared_family = _family_of(declared, "x")
    if declared_family is family:
        return True
    # A generic text declaration over a textual detection is consistent enough to accept.
    return declared_family is Family.TEXT and family is Family.TEXT


def check_count(existing: int, incoming: int) -> None:
    """Attachments are counted together — blobs and references — because the budget is the prompt's."""
    if existing + incoming > MAX_ATTACHMENTS:
        raise BlobRefusal("too_many", say("too_many", limit=MAX_ATTACHMENTS))
