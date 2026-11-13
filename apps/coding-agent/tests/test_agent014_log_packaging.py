"""The log reader's qualified CLI ships with the app and rejects unpinned archives."""

import hashlib
import importlib.util
import io
from pathlib import Path
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]


def installer():
    spec = importlib.util.spec_from_file_location(
        "cli_installer", ROOT / "scripts/install-databricks-cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_log_cli_checksum_failure_never_replaces_existing_binary(tmp_path):
    destination = tmp_path / "databricks"
    destination.write_bytes(b"old")
    with pytest.raises(ValueError, match="checksum mismatch"):
        installer().install_archive(b"untrusted", "0" * 64, destination)
    assert destination.read_bytes() == b"old"


def test_log_cli_install_reads_only_the_named_binary_and_is_executable(tmp_path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("databricks", b"qualified-binary")
        archive.writestr("../outside", b"never extract this")
    raw = output.getvalue()
    destination = tmp_path / ".bin/databricks"
    installer().install_archive(raw, hashlib.sha256(raw).hexdigest(), destination)
    assert destination.read_bytes() == b"qualified-binary"
    assert destination.stat().st_mode & 0o777 == 0o755
    assert not (tmp_path / "outside").exists()


def test_build_installs_the_qualified_log_cli_and_reader_prefers_it(tmp_path, monkeypatch):
    from api.adapters.databricks.app_logs import DatabricksAppLogs

    assert "python3 scripts/install-databricks-cli.py" in (ROOT / "scripts/prepare-app.sh").read_text()
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    assert DatabricksAppLogs().executable == str(ROOT / ".bin/databricks")
