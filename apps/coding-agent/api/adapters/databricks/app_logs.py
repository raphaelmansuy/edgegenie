"""Bounded, user-authenticated app logs through the platform's supported CLI.

The SDK has no log-stream API. The official CLI owns that protocol:
https://docs.databricks.com/aws/en/dev-tools/cli/reference/apps-commands#databricks-apps-logs
"""

import asyncio
from contextlib import suppress
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from ..child_env import child_env
from ...domain.redact import redact


class AppLogFailure(RuntimeError):
    """Safe diagnostics, with no retained CLI error or response body."""

    def __init__(self, code, state, reason, http_status=None):
        super().__init__(reason)
        self.code, self.state, self.http_status = code, state, http_status


def classify_failure(error: bytes):
    text = error.decode("utf-8", "replace").casefold()
    match = re.search(r"\bhttp[ /]+(\d{3})\b", text)
    status = int(match[1]) if match else None
    if status is not None and status >= 500:
        return AppLogFailure("SERVICE_UNAVAILABLE", "unavailable", "The native log service is temporarily unavailable. Observe again later; no alternate identity was used.", status)
    if status in (401, 403) or re.search(
        r"\b(permission_denied|permission denied|unauthorized|forbidden)\b", text
    ):
        return AppLogFailure(
            "ACCESS_REFUSED",
            "unreadable",
            "The log service refused your identity. No alternate identity was used.",
            status,
        )
    if status in (301, 302, 303, 307, 308):
        return AppLogFailure(
            "AUTH_REDIRECT",
            "unreadable",
            "The log service requested interactive authentication. Sign in again; no alternate identity was used.",
            status,
        )
    if any(word in text for word in ("certificate", "tls handshake", "unknown authority")):
        return AppLogFailure(
            "TLS_FAILED",
            "unavailable",
            "The app host could not establish a trusted log-service connection.",
            status,
        )
    if any(word in text for word in ("oauth", "default auth", "token expired", "cannot get access token")):
        return AppLogFailure(
            "AUTH_UNAVAILABLE",
            "unreadable",
            "The log client could not use your delegated credential. Sign in again; no alternate identity was used.",
            status,
        )
    if "bad handshake" in text:
        return AppLogFailure(
            "HANDSHAKE_FAILED", "unavailable", "The log service did not establish a log stream.", status
        )
    return AppLogFailure(
        "CLIENT_FAILED", "unavailable", "The log client exited before a log stream was observed.", status
    )


async def bounded_error(reader):
    chunks, remaining = [], 4096
    while part := await reader.read(16384):
        if remaining:
            chunks.append(part[:remaining])
            remaining = max(0, remaining - len(part))
    return b"".join(chunks)


class DatabricksAppLogs:
    def __init__(self, *, executable=None, timeout=12, maximum=65536):
        bundled = Path(__file__).resolve().parents[3] / ".bin/databricks"
        self.executable = executable or (str(bundled) if bundled.is_file() else shutil.which("databricks"))
        self.timeout, self.maximum = timeout, maximum

    async def read(self, name, who, limit=200):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
            raise ValueError("Choose a native app name for logs.")
        if not who.token:
            raise PermissionError("Sign in again to read app logs as your identity.")
        if not self.executable:
            return {
                "state": "unavailable",
                "reason": "The Databricks CLI is not installed on this app host. Open the app's Logs tab in Databricks.",
                "source": "app-log-stream",
            }
        limit = min(max(int(limit), 1), 200)
        with tempfile.TemporaryDirectory(prefix="agent-app-logs-") as home:
            # Apps logs requires the CLI's OAuth-token interface, not its PAT interface.
            # Give it only this forwarded access token in an isolated, short-lived cache.
            # There is no refresh token, profile inheritance or service-principal fallback.
            host = who.workspace.rstrip("/")
            expiry = min(who.expires_at or time.time() + 60, time.time() + 60)
            cache = {
                "version": 1,
                "tokens": {
                    host: {
                        "access_token": who.token,
                        "token_type": "Bearer",
                        "expiry": datetime.fromtimestamp(expiry, timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "expires_in": max(0, int(expiry - time.time())),
                    }
                },
            }
            folder = Path(home) / ".databricks"
            folder.mkdir(mode=0o700)
            cache_file = folder / "token-cache.json"
            with os.fdopen(os.open(cache_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                json.dump(cache, stream)
            env = child_env(
                {
                    "DATABRICKS_HOST": host,
                    "DATABRICKS_AUTH_TYPE": "databricks-cli",
                    "DATABRICKS_CLI_PATH": self.executable,
                    "NO_COLOR": "1",
                },
                home=home,
            )
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "apps",
                "logs",
                name,
                "--tail-lines",
                str(limit),
                env=env,
                cwd=home,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            errors = asyncio.create_task(bounded_error(process.stderr))
            capped = False
            try:
                async with asyncio.timeout(self.timeout):
                    chunks, size = [], 0
                    while size <= self.maximum:
                        part = await process.stdout.read(min(16384, self.maximum + 1 - size))
                        if not part:
                            break
                        chunks.append(part)
                        size += len(part)
                    raw = b"".join(chunks)
                    capped = len(raw) > self.maximum
                    if not capped:
                        await process.wait()
                    if process.returncode not in (0, None):
                        raise classify_failure(await errors)
            finally:
                errors.cancel()
                with suppress(asyncio.CancelledError):
                    await errors
                if process.returncode is None:
                    process.kill()
                    # A killed writer can still leave a full pipe. Drain it before waiting;
                    # asyncio's process waiter otherwise waits forever for the paused reader.
                    await asyncio.wait_for(process.communicate(), 2)
        text = re.sub(r"\x1b\[[0-9;]*m", "", raw[: self.maximum].decode("utf-8", "replace"))
        lines = text.splitlines()
        return {
            "state": "observed",
            "source": "app-log-stream",
            "ranAs": who.run_as,
            "lastRefreshedAt": time.time(),
            "text": redact("\n".join(lines[-limit:])),
            "capped": capped or len(lines) > limit,
            "limit": limit,
            "retention": "Live app compute logs; Databricks does not retain them after compute stops.",
        }
