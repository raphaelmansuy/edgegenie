"""An unknown permission boundary is never a qualified execution identity."""
import importlib.util
from pathlib import Path
import pytest
from api.domain.run_identity import RunIsolation
from api.config import Settings


@pytest.mark.parametrize("principal,secret,database", [
    ("app", False, False), ("runner", True, False), ("runner", False, True),
    ("runner", None, False), ("runner", False, None), ("", False, False),
])
def test_run_isolation_refuses_app_identity_readable_or_unknown_grants(principal, secret, database):
    with pytest.raises(PermissionError):
        RunIsolation(principal, "app", secret, database).require_isolated()


def test_an_unqualified_run_identity_cannot_boot_or_pass_the_deployment_check():
    from api.main import build
    with pytest.raises(ValueError, match="S13"):
        build(Settings(agent_run_identity="separate-runner"))
    path = Path(__file__).resolve().parents[1] / "scripts/check-run-identity.py"
    spec = importlib.util.spec_from_file_location("run_identity_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check({"env": []}, {})
    with pytest.raises(ValueError):
        module.check({"env": [{"name": "APP_AGENT_RUN_IDENTITY", "value": "runner"}]}, {})
    with pytest.raises(ValueError):
        module.check({"env": []}, {"APP_AGENT_RUN_IDENTITY": "runner"})
