#!/usr/bin/env python3
"""Reject an unqualified execution identity in build/deployment configuration; read no secrets."""
import os
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.domain.run_identity import check_declaration


def check(app_config, environment):
    check_declaration(environment.get("APP_AGENT_RUN_IDENTITY", ""))
    for entry in app_config.get("env", []):
        if entry.get("name") == "APP_AGENT_RUN_IDENTITY":
            if entry.get("valueFrom"):
                raise ValueError("Execution identity is indirect and unverified; qualify S13 before deployment.")
            check_declaration(str(entry.get("value", "")))


if __name__ == "__main__":
    try:
        check(yaml.safe_load((Path(__file__).resolve().parents[1] / "app.yaml").read_text()), os.environ)
    except ValueError as error:
        raise SystemExit(str(error))
    print("Agent execution identity: user only; no separate identity declared or app-SP fallback enabled")
