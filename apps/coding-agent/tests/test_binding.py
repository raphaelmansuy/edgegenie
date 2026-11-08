"""Cell bindings and the binding module: parse, validate, render, and get stale right.

The staleness case is the point of this file. A cell index is positional, so the file may have changed
between the click that selected it and the prompt that mentions it; answering about the old text would
make the agent edit code the user no longer has (spec 006 E-04).
"""

from __future__ import annotations

import pytest

from api.domain.binding import (
    BindingError, cell_text, content_sha, parse_cell_ref, render_cell,
)
from api.domain.context import Attachment, ContextError, parse


def test_parse_cell_ref_round_trips_and_is_one_based():
    assert parse_cell_ref("/Users/a/nb#3") == ("/Users/a/nb", 3)
    assert parse_cell_ref("  /a/b#1  ") == ("/a/b", 1)


@pytest.mark.parametrize("bad", ["/a/b", "/a/b#0", "/a/b#x", "/a/b#1.5", "#3", "", "/a/../b#2"])
def test_parse_cell_ref_refuses_what_it_cannot_trust(bad):
    with pytest.raises(BindingError):
        parse_cell_ref(bad)


class Cell:
    def __init__(self, source: str, language: str = "PYTHON") -> None:
        self.source, self.language = source, language


def test_cell_text_is_the_index_the_ui_shows():
    cells = [Cell("a"), Cell("b"), Cell("c")]
    assert cell_text(cells, 1) == ("a", "PYTHON")
    assert cell_text(cells, 3) == ("c", "PYTHON")


def test_a_cell_that_is_no_longer_there_is_an_error_not_an_empty_attachment():
    with pytest.raises(BindingError, match="no longer in this notebook"):
        cell_text([Cell("a")], 2)
    with pytest.raises(BindingError):
        cell_text([], 1)


def test_content_sha_is_short_stable_and_distinguishes_text():
    assert len(content_sha("x")) == 4
    assert content_sha("x") == content_sha("x")
    assert content_sha("x") != content_sha("y")


def test_render_cell_names_the_cell_and_says_when_it_changed():
    same = render_cell("/a/nb", 3, "print(1)", "PYTHON", sha="abcd", seen_sha="abcd")
    assert "cell 3 of /a/nb" in same and "sha abcd" in same and "changed" not in same
    stale = render_cell("/a/nb", 3, "print(2)", "PYTHON", sha="ffff", seen_sha="abcd")
    assert "changed after the user selected it" in stale
    assert "was sha abcd, now sha ffff" in stale
    assert "print(2)" in stale          # the CURRENT text, not the old one
    assert "print(1)" not in stale


def test_an_unbound_cell_has_no_staleness_notice():
    out = render_cell("/a/nb", 1, "x", "SQL", sha="aaaa", seen_sha="")
    assert "changed" not in out and "cell 1 of /a/nb" in out and "(sql)" in out


def test_parse_accepts_a_cell_and_keeps_its_sha():
    got = parse([{"kind": "cell", "ref": "/a/nb#2", "sha": "beef"}])
    assert got == [Attachment("cell", "/a/nb#2", "beef")]
    assert got[0].name == "nb · cell 2"


def test_parse_refuses_a_malformed_cell_reference():
    with pytest.raises(ContextError):
        parse([{"kind": "cell", "ref": "/a/nb"}])


def test_a_cell_and_its_notebook_are_different_attachments():
    got = parse([{"kind": "notebook", "ref": "/a/nb"}, {"kind": "cell", "ref": "/a/nb#1"}])
    assert len(got) == 2


# -- blob attachments (spec 009) -----------------------------------------------------------------
def test_a_blob_attachment_keeps_the_users_own_name():
    """[AFC-8]: the chip says `q3.csv`, not "attachment" — the transcript renders this on reload, and a
    generic label is a file the user cannot recognise."""
    from api.domain.context import parse

    a = parse([{"kind": "blob", "ref": "blb_0123456789ab", "name": "q3.csv"}])[0]
    assert a.name == "q3.csv"
    assert a.ref == "blb_0123456789ab"


def test_a_blob_label_cannot_carry_markup_or_newlines():
    from api.domain.context import parse

    a = parse([{"kind": "blob", "ref": "blb_0123456789ab", "name": "a\n<script>x</script>"}])[0]
    assert "\n" not in a.name
    assert a.name.startswith("a")


def test_a_blob_ref_that_is_not_an_id_is_refused():
    from api.domain.context import ContextError, parse

    for bad in ("../../etc/passwd", "blb_", "blb_zzzzzzzzzzzz", "/Users/me/x.png"):
        with pytest.raises(ContextError):
            parse([{"kind": "blob", "ref": bad}])


def test_a_blob_attachment_resolves_to_text_not_base64():
    """The prompt carries what the blob SAYS, never the bytes: base64 in a prompt is a wall the model
    cannot read and the user pays for (spec 009 [D8])."""
    import asyncio

    from api.adapters.blob import MemoryBlobStore
    from api.domain.blob import validate
    from api.domain.context import parse
    from api.services.blobs import BlobService
    from api.services.context import resolve

    store = MemoryBlobStore()
    svc = BlobService(store)
    raw = b"hour,trips\n18,42\n"
    spec = validate("t.csv", raw, "text/csv", model_sees_images=True)
    row = asyncio.run(store.put("s1", "u1", spec, raw))
    items = parse([{"kind": "blob", "ref": row.id, "name": "t.csv"}])
    out = asyncio.run(resolve(items, None, None, None, blobs=svc, user_id="u1"))
    assert out[0].error == ""
    assert "hour,trips" in out[0].text
    assert "aG91cix0cmlwcw" not in out[0].text     # no base64 of the same bytes


def test_a_missing_blob_is_reported_not_silently_dropped():
    """[AFC-15]: the agent must be TOLD it is missing, or it will answer as if it saw the file."""
    import asyncio

    from api.adapters.blob import MemoryBlobStore
    from api.domain.context import parse
    from api.services.blobs import BlobService
    from api.services.context import resolve

    svc = BlobService(MemoryBlobStore())
    items = parse([{"kind": "blob", "ref": "blb_000000000000", "name": "gone.csv"}])
    out = asyncio.run(resolve(items, None, None, None, blobs=svc, user_id="u1"))
    assert out[0].error, "a missing attachment must produce an error, not silence"
    assert out[0].text == ""
