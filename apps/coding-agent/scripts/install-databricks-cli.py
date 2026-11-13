#!/usr/bin/env python3
"""Install the qualified app-log client into this app's build output, with a release SHA pin.

SHA256 values are the official GitHub release asset digests for databricks/cli v0.289.1.
Only the named binary is read from the zip; archive paths are never extracted.
"""
import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import urllib.request
import zipfile

VERSION = "0.289.1"
RELEASE = "https://github.com/databricks/cli/releases/download/v" + VERSION
CHECKSUMS = {
    "darwin_amd64": "755733ce6d970c40c6be325ddd07dcc45553f19af95d8d645e93b9211d1c457c",
    "darwin_arm64": "14c03750c367ad77247d9e8edecaa974f3a8802fb09afa1e2c3ee9333993404e",
    "linux_amd64": "301b805094f5c5e9c88208687a326b47c3a4282e33324899b34f31846a4145aa",
    "linux_arm64": "ec6390943887f1f9bbd2755e596b1577e3c112f702c11e265d5b7b67e1d8dc67",
}
MAX_ARCHIVE = 100 * 1024 * 1024


def install_archive(raw, expected, destination):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Databricks CLI release checksum mismatch; existing binary was kept")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo("databricks")
        if info.file_size > MAX_ARCHIVE or info.is_dir():
            raise ValueError("Invalid Databricks CLI binary entry")
        binary = archive.read(info)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="databricks-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(binary)
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    machine = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    target = platform.system().lower() + "_" + str(machine)
    if target not in CHECKSUMS:
        raise SystemExit("Unsupported app-log CLI platform: " + target)
    url = RELEASE + f"/databricks_cli_{VERSION}_{target}.zip"
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Databricks CLI archive exceeds its build limit")
    destination = Path(__file__).resolve().parents[1] / ".bin/databricks"
    install_archive(raw, CHECKSUMS[target], destination)
    version = subprocess.check_output([str(destination), "--version"], text=True, timeout=10).strip()
    if version != "Databricks CLI v" + VERSION:
        raise RuntimeError("Unexpected installed Databricks CLI version")
    print("[prepare] " + version + " pinned and checksum-verified")


if __name__ == "__main__":
    main()
