"""Blob rules: the trust boundary, tested as a property rather than as a happy path.

`api/domain/blob.py` is pure, so these tests need no server, no store and no clock. They are the reason
the module was written pure: 40+ cases run in milliseconds, which is what makes it possible to enumerate
the refusals instead of spot-checking two.
"""

from __future__ import annotations

import pytest

from api.domain.blob import (
    ACCEPT_ATTR,
    BLOB_ID,
    CAPABILITY,
    Family,
    MAX_ATTACHMENTS,
    MAX_BYTES,
    MAX_STORED_NAME,
    REFUSALS,
    BlobRefusal,
    check_count,
    detect_mime,
    human_size,
    needs_vision,
    sanitise_name,
    say,
    validate,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
ZIP = b"PK\x03\x04" + b"\x00" * 64
TEXT = "hour,trips\n18,42\n".encode()


def v(name: str, raw: bytes, declared: str = "", *, vision: bool = True):
    return validate(name, raw, declared, model_sees_images=vision)


# -- detection -----------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"), (WEBP, "image/webp"),
    (PDF, "application/pdf"), (ZIP, "application/zip"),
])
def test_detect_by_magic_bytes(raw, expected):
    assert detect_mime(raw) == expected


def test_detect_ignores_the_name():
    # The bytes are a PNG; the name says .txt. Detection must answer for the bytes.
    assert detect_mime(PNG) == "image/png"


def test_detect_returns_none_for_plain_text():
    assert detect_mime(TEXT) is None


# -- names ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("given,expected", [
    ("report.png", "report.png"),
    ("/a/b/report.png", "report.png"),
    ("..\\..\\windows\\x.png", "x.png"),
    ("../../etc/passwd", "passwd"),
    ("a/b/c.png", "c.png"),
    ("with space.csv", "with space.csv"),
    ("weird<>.txt", "weird_.txt"),
    ("ünïcode.txt", "ünïcode.txt"),
])
def test_sanitise_keeps_a_basename(given, expected):
    assert sanitise_name(given) == expected


def test_sanitise_rejects_a_name_that_is_only_dots():
    assert sanitise_name("..") == ""
    assert sanitise_name(".") == ""
    assert sanitise_name("") == ""


def test_sanitise_strips_leading_dots_so_no_hidden_file_is_written():
    assert sanitise_name(".env") == "env"


def test_sanitise_removes_control_characters():
    assert "\x00" not in sanitise_name("a\x00b.png")
    assert sanitise_name("a\x00b.png") == "ab.png"


def test_sanitise_truncates_but_keeps_the_extension():
    out = sanitise_name("x" * 400 + ".png")
    assert len(out) <= MAX_STORED_NAME
    assert out.endswith(".png")


def test_sanitise_is_deterministic():
    once, twice = sanitise_name("a  b??c.png"), sanitise_name("a  b??c.png")
    assert once == twice


# -- size ----------------------------------------------------------------------------------------

def test_exactly_at_the_limit_is_accepted():
    raw = PNG + b"\x00" * (MAX_BYTES - len(PNG))
    assert v("big.png", raw).size == MAX_BYTES


def test_one_byte_over_is_refused_naming_both_values():
    raw = PNG + b"\x00" * (MAX_BYTES - len(PNG) + 1)
    with pytest.raises(BlobRefusal) as e:
        v("big.png", raw)
    assert e.value.code == "too_big"
    # Both numbers, because a limit without the observed value cannot be acted on.
    assert "8.0 MB" in e.value.message
    assert "big.png" in e.value.message


def test_human_size_units():
    assert human_size(900) == "900 bytes"
    assert human_size(2048) == "2 KB"
    assert human_size(12_400_000) == "11.8 MB"


# -- emptiness -----------------------------------------------------------------------------------

def test_zero_bytes_is_refused():
    with pytest.raises(BlobRefusal) as e:
        v("empty.txt", b"")
    assert e.value.code == "empty"


def test_whitespace_only_is_refused():
    with pytest.raises(BlobRefusal):
        v("blank.txt", b"   \n\t  ")


# -- types ---------------------------------------------------------------------------------------

def test_text_with_a_textual_name_is_accepted():
    spec = v("data.csv", TEXT, "text/csv")
    assert spec.family is Family.TEXT
    # Text carries no magic bytes, so the declaration is the only evidence — and it is kept verbatim
    # rather than flattened to text/plain, because the reader does care about CSV vs prose.
    assert spec.mime == "text/csv"
    assert spec.sha256 == __import__("hashlib").sha256(TEXT).hexdigest()


def test_unknown_bytes_with_a_binary_name_are_refused():
    with pytest.raises(BlobRefusal) as e:
        v("thing.bin", b"\x00\x01\x02\x03 not text at all")
    assert e.value.code == "unknown_type"


def test_unknown_bytes_that_are_not_utf8_are_refused():
    with pytest.raises(BlobRefusal) as e:
        v("notes.txt", b"\xff\xfe\x00\x01 not utf8")
    assert e.value.code == "unknown_type"


def test_zip_named_as_text_is_a_mismatch():
    with pytest.raises(BlobRefusal) as e:
        v("notes.txt", ZIP, "text/plain")
    assert e.value.code == "mismatch"
    assert "application/zip" in e.value.message


def test_jpeg_named_png_is_corrected_silently():
    # Inside one family the reader dispatches on the DETECTED type, so the claim cannot mislead it.
    spec = v("photo.png", JPEG, "image/png")
    assert spec.mime == "image/jpeg"
    assert spec.family is Family.IMAGE


def test_ipynb_is_a_notebook():
    spec = v("analysis.ipynb", ZIP, "application/json")
    assert spec.family is Family.NOTEBOOK


def test_pdf_is_its_own_family():
    assert v("report.pdf", PDF, "application/pdf").family is Family.PDF


# -- capability ----------------------------------------------------------------------------------

def test_an_image_without_vision_is_ACCEPTED_and_marked_unseen_by_the_model():
    """The bytes are the user's evidence; refusing them leaves them no way to hand a screenshot over.

    What must never happen is an attachment the model silently cannot see — so the fact is recorded on the
    spec, and the manifest says it in words (spec 009 [P4], [D7]).
    """
    spec = v("shot.png", PNG, "image/png", vision=False)
    assert spec.family is Family.IMAGE
    assert spec.unseen_by_model is True


def test_an_image_with_vision_is_not_marked_unseen():
    assert v("shot.png", PNG, "image/png", vision=True).unseen_by_model is False


def test_text_is_never_marked_unseen():
    assert v("data.csv", TEXT, "text/csv", vision=False).unseen_by_model is False


def test_an_image_with_vision_is_accepted():
    assert v("shot.png", PNG, "image/png", vision=True).family is Family.IMAGE


def test_text_never_needs_vision():
    assert v("data.csv", TEXT, "text/csv", vision=False).family is Family.TEXT


def test_needs_vision_matches_the_matrix():
    assert needs_vision(Family.IMAGE)
    assert needs_vision(Family.PDF)
    assert not needs_vision(Family.TEXT)
    assert not needs_vision(Family.NOTEBOOK)


def test_accept_attribute_is_generated_from_the_matrix():
    # [V6]: the picker must not promise a type the server refuses.
    for cap in CAPABILITY:
        for item in cap.accept:
            assert item in ACCEPT_ATTR


# -- counts --------------------------------------------------------------------------------------

def test_count_is_shared_between_blobs_and_references():
    check_count(0, MAX_ATTACHMENTS)  # exactly full is fine
    with pytest.raises(BlobRefusal) as e:
        check_count(MAX_ATTACHMENTS, 1)
    assert e.value.code == "too_many"
    assert str(MAX_ATTACHMENTS) in e.value.message


# -- the copy register ---------------------------------------------------------------------------

def test_every_refusal_code_has_a_sentence():
    for code, sentence in REFUSALS.items():
        assert sentence.endswith("."), f"{code} must end with a full stop"
        assert "!" not in sentence, f"{code} must not exclaim"


def test_say_fills_the_placeholders():
    assert say("too_big", name="a.png", size="9.0 MB", limit="8.0 MB") == "a.png is 9.0 MB; the limit is 8.0 MB."


def test_a_size_refusal_always_names_both_numbers():
    # The rule from 09 §the-copy-register: a limit without the observed value is unactionable.
    for key in ("too_big",):
        assert "{size}" in REFUSALS[key] and "{limit}" in REFUSALS[key]


def test_blob_id_pattern_rejects_guesses():
    assert BLOB_ID.match("blb_0123456789ab")
    for bad in ("blb_", "blb_xyz", "blb_0123456789abcdef", "0123456789ab", "blb_0123456789AB"):
        assert not BLOB_ID.match(bad), bad


# -- purity --------------------------------------------------------------------------------------

def test_the_rules_import_nothing_that_can_do_io():
    """The test that keeps this module pure, which is what keeps its tests fast and deterministic."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "api" / "domain" / "blob.py"
    tree = ast.parse(src.read_text())
    banned = {"os", "time", "pathlib", "io", "requests", "httpx", "asyncio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, f"blob.py must not import {a.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned, f"blob.py must not import {node.module}"
