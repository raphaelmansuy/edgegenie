"""Spec 015 source completeness and caller-scoped media. No live workspace or SQL."""
import asyncio
import base64
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from api.domain import notebook
from api.domain.markdown_media import MAX_BYTES, validate_raster
from api.adapters.databricks.workspace import WorkspaceBrowser


def source(count=1, body="# Heading"):
    return "# Databricks notebook source\n" + "\n\n# COMMAND ----------\n\n".join(
        "# MAGIC %md " + body for _ in range(count)) + "\n"


@pytest.mark.parametrize("count,partial", [(399, False), (400, False), (401, True)])
def test_cell_count_has_explicit_completeness(count, partial):
    cells, reasons = notebook.read_completeness(source(count))
    assert len(cells) == min(count, 400)
    assert ("cell_count" in reasons) is partial


@pytest.mark.parametrize("size,partial", [(19999, False), (20000, False), (20001, True)])
def test_unicode_limit_is_server_codepoints(size, partial):
    cells, reasons = notebook.read_completeness(source(body="😀" * size))
    assert cells[0].source == "😀" * min(size, 20000)
    assert bool(reasons) is partial


class Http:
    def __init__(self, text):
        self.text = text
        self.calls = []

    async def get(self, endpoint, token, params=None):
        self.calls.append((endpoint, token, params))
        if endpoint.endswith("get-status"):
            return {"object_type": "NOTEBOOK", "language": "PYTHON", "modified_at": 1}
        return {"content": base64.b64encode(self.text.encode()).decode()}

    async def get_bytes(self, endpoint, token, **kwargs):
        self.calls.append((endpoint, token, kwargs))
        return b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 2, 2)


def test_reader_promotes_count_and_cell_truncation_to_document():
    for text in [source(401), source(body="x" * 20001), source(body="x" * 400001)]:
        browser = WorkspaceBrowser("https://example.cloud.databricks.com", lambda: "app-token", http=Http(text))
        obj = asyncio.run(browser.read("/Users/me/demo", "user-token"))
        assert obj.truncated and obj.incomplete_reasons
        assert obj.to_dict()["incompleteReasons"] == obj.incomplete_reasons


def test_save_guard_refuses_original_hidden_tail_and_incoming_overflow():
    http = Http(source(401))
    browser = WorkspaceBrowser("https://example.cloud.databricks.com", lambda: "app-token", http=http)
    with pytest.raises(ValueError, match="original notebook"):
        asyncio.run(browser.ensure_complete_notebook("/Users/me/demo", source(), "PYTHON", "user", existing=True))
    with pytest.raises(ValueError, match="cell count"):
        asyncio.run(browser.ensure_complete_notebook("/Users/me/demo", source(401), "PYTHON", "user", existing=False))
    assert all("import" not in call[0] and "delete" not in call[0] for call in http.calls)


def test_media_never_falls_back_to_app_credentials():
    http = Http("")
    browser = WorkspaceBrowser("https://example.cloud.databricks.com", lambda: "privileged", http=http)
    with pytest.raises(PermissionError):
        asyncio.run(browser.markdown_image("/Users/me/image.png", ""))
    assert http.calls == []
    data, mime = asyncio.run(browser.markdown_image("/Volumes/c/s/v/image.png", "caller"))
    assert mime == "image/png" and data
    assert http.calls[0][0] == "/api/2.0/fs/files/Volumes/c/s/v/image.png"
    assert http.calls[0][1] == "caller"


@pytest.mark.parametrize("path", ["https://tracker.test/x", "/Users/me/../other.png", "/etc/passwd"])
def test_media_paths_are_not_a_general_url_proxy(path):
    http = Http("")
    browser = WorkspaceBrowser("https://example.cloud.databricks.com", lambda: "privileged", http=http)
    with pytest.raises(ValueError):
        asyncio.run(browser.markdown_image(path, "caller"))
    assert not http.calls


def test_raster_limits_precede_image_decoding():
    with pytest.raises(ValueError, match="valid PNG"):
        validate_raster(b"<svg onload='alert(1)'/>")
    with pytest.raises(ValueError, match="5 MiB"):
        validate_raster(b"x" * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="megapixel"):
        validate_raster(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 100000, 100000))


def test_partial_notebook_route_refuses_before_import():
    from test_api import make_client
    from test_save_path import SaveBrowser, SCRATCH
    class IncompleteBrowser(SaveBrowser):
        async def ensure_complete_notebook(self, *args, **kwargs):
            raise ValueError("original notebook is incomplete")
    c = make_client()
    c.app.state.workspace = IncompleteBrowser()
    session = c.post("/api/sessions", json={"folder": SCRATCH, "model": "fake/model-a"}).json()["id"]
    r = c.post("/api/workspace/save", json={"path": SCRATCH + "/demo", "text": source(),
               "language": "PYTHON", "sessionId": session, "version": ""})
    assert r.status_code == 422, r.text
    assert c.app.state.workspace.imports == []


def test_media_route_requires_user_authorization():
    from test_api import make_client
    c = make_client()
    r = c.get("/api/workspace/markdown-image", params={"path": "/Users/me/image.png"})
    assert r.status_code == 401, r.text
