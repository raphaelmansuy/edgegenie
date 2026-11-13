"""Build child environments from an explicit allow list, never a parent copy."""
import os
from pathlib import Path

SYSTEM_VARIABLES = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")


def child_env(extra: dict[str, str] | None = None, *, home: str | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in SYSTEM_VARIABLES if key in os.environ}
    env.update(extra or {})
    if home:
        Path(home).mkdir(parents=True, exist_ok=True, mode=0o700)
        env.update(HOME=home, XDG_CONFIG_HOME=f"{home}/config", XDG_DATA_HOME=f"{home}/data",
                   XDG_CACHE_HOME=f"{home}/cache", XDG_STATE_HOME=f"{home}/state")
    env["NODE_NO_WARNINGS"] = "1"
    return env
