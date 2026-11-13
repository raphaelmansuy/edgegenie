"""App log reads are bounded, credential-minimal and independent of definition revisions."""

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from api.adapters.databricks.app_logs import DatabricksAppLogs, AppLogFailure, classify_failure
from api.adapters.databricks.handlers.app import AppHandler
from api.domain.asset import Actor, AssetRef
from api.domain.scope import Scope


@pytest.fixture
def who():
    return Actor(
        "s",
        "opaque",
        "t",
        Scope.for_session("s", "/scratch", None),
        workspace="https://workspace.test",
        token="user-token",
        username="alice",
    )


def cli(tmp_path, source):
    path = tmp_path / "databricks"
    path.write_text("#!" + sys.executable + "\n" + source)
    path.chmod(0o700)
    return str(path)


async def test_log_cli_sees_only_user_credential_and_returns_redacted_bounded_output(
    tmp_path, monkeypatch, who
):
    monkeypatch.setenv("APP_AGENT_KEY", "parent-secret")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "parent-sp-secret")
    executable = cli(
        tmp_path,
        """import os,sys,json
assert sys.argv[1:] == ['apps','logs','app-one','--tail-lines','200']
assert 'DATABRICKS_TOKEN' not in os.environ
assert os.environ['DATABRICKS_AUTH_TYPE']=='databricks-cli'
path=os.path.join(os.environ['HOME'],'.databricks','token-cache.json')
cache=json.load(open(path))['tokens']['https://workspace.test']
assert cache['access_token']=='user-token' and 'refresh_token' not in cache
assert os.stat(path).st_mode & 0o777 == 0o600
assert 'APP_AGENT_KEY' not in os.environ and 'DATABRICKS_CLIENT_SECRET' not in os.environ
assert os.environ['DATABRICKS_HOST']=='https://workspace.test'
print('app started')
print('sk-'+'x'*30)
""",
    )
    result = await DatabricksAppLogs(executable=executable).read("app-one", who)
    assert result["state"] == "observed" and result["ranAs"] == "alice"
    assert "app started" in result["text"] and "sk-" not in result["text"] and not result["capped"]


async def test_oversized_log_stream_is_killed_at_the_byte_cap(tmp_path, who):
    executable = cli(tmp_path, "import sys\nsys.stdout.write('x'*1000000)\nsys.stdout.flush()\n")
    result = await DatabricksAppLogs(executable=executable, maximum=4096).read("app-one", who)
    assert result["capped"] and len(result["text"]) <= 4096


async def test_silent_stream_hits_deadline_and_is_reaped(tmp_path, who):
    executable = cli(tmp_path, "import time\ntime.sleep(10)\n")
    with pytest.raises(TimeoutError):
        await DatabricksAppLogs(executable=executable, timeout=0.05).read("app-one", who)


async def test_refused_log_stream_never_exposes_cli_error_or_uses_another_identity(tmp_path, who):
    executable = cli(tmp_path, "import sys\nprint('sensitive body')\nsys.exit(1)\n")
    with pytest.raises(AppLogFailure, match="exited before"):
        await DatabricksAppLogs(executable=executable).read("app-one", who)
    with pytest.raises(PermissionError):
        await DatabricksAppLogs(executable=executable).read("app-one", replace(who, token=None))
    with pytest.raises(ValueError):
        await DatabricksAppLogs(executable=executable).read("--profile=other", who)


async def test_describe_includes_logs_without_weakening_revision_guards(who):
    class Http:
        async def get(self, *args):
            return {"name": "app-one", "compute_status": {"state": "ACTIVE"}}

    class Logs:
        async def read(self, name, actor):
            return {"state": "observed", "text": "actual log"}

    handler = AppHandler(Http(), None, logs=Logs())
    ref = AssetRef("app", "app-one")
    before = await handler.read(ref, who)
    described = await handler.describe(ref, who)
    assert described["logs"]["text"] == "actual log" and described["revision"] == before.revision

    class Denied:
        async def read(self, *args):
            raise PermissionError("not readable by you")

    handler.logs = Denied()
    denied = await handler.describe(ref, who)
    assert denied["logs"]["state"] == "unreadable" and denied["revision"] == before.revision


@pytest.mark.parametrize(
    "body,code,state,status",
    [
        (b"Error: websocket: bad handshake (HTTP 302 Found)", "AUTH_REDIRECT", "unreadable", 302),
        (b"Error: websocket: bad handshake (HTTP 403 Forbidden)", "ACCESS_REFUSED", "unreadable", 403),
        (b"Error: certificate signed by unknown authority", "TLS_FAILED", "unavailable", None),
        (b"Error: default auth cannot get access token", "AUTH_UNAVAILABLE", "unreadable", None),
        (b"Error: websocket: bad handshake", "HANDSHAKE_FAILED", "unavailable", None),
    ],
)
def test_log_failures_preserve_only_safe_categories(body, code, state, status):
    failure = classify_failure(body + b" secret-body-must-not-escape")
    assert (failure.code, failure.state, failure.http_status) == (code, state, status)
    assert "secret-body" not in str(failure)


async def test_large_error_stream_cannot_deadlock_or_escape(tmp_path, who):
    executable = cli(
        tmp_path, "import sys\nsys.stderr.write('secret'*200000)\nsys.stderr.flush()\nsys.exit(1)\n"
    )
    with pytest.raises(AppLogFailure) as failure:
        await asyncio.wait_for(DatabricksAppLogs(executable=executable).read("app-one", who), 2)
    assert failure.value.code == "CLIENT_FAILED" and "secret" not in str(failure.value)


async def test_log_client_failure_does_not_hide_readable_app_definition(who):
    class Http:
        async def get(self, *args):
            return {"name": "app-one", "compute_status": {"state": "ACTIVE"}}

    class Logs:
        async def read(self, *args):
            raise classify_failure(b"Error: websocket: bad handshake (HTTP 302 Found)")

    described = await AppHandler(Http(), None, logs=Logs()).describe(AssetRef("app", "app-one"), who)
    assert described["logs"]["code"] == "AUTH_REDIRECT"
    assert described["logs"]["httpStatus"] == 302 and described["revision"]


def test_native_service_outage_is_never_reported_as_user_permission_failure():
    failure = classify_failure(b'Error: websocket: bad handshake (HTTP 503 Service Unavailable)')
    assert (failure.code, failure.state, failure.http_status) == ('SERVICE_UNAVAILABLE', 'unavailable', 503)
    assert 'temporarily unavailable' in str(failure)
