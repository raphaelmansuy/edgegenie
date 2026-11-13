#!/usr/bin/env python3
"""Compare declared and deployed user scopes. Read names only, never credentials."""
import json
import sys
from pathlib import Path
import yaml


def check(live: dict, bundle: dict, name: str) -> tuple[set[str], set[str]]:
    declared = set(bundle['resources']['apps'][name].get('user_api_scopes') or [])
    deployed = set(live.get('user_api_scopes') or [])
    return declared - deployed, deployed - declared


if __name__ == '__main__':
    source = Path(__file__).resolve().parents[3] / 'databricks.yml'
    name = sys.argv[1] if len(sys.argv) > 1 else 'coding-agent'
    live, bundle = json.load(sys.stdin), yaml.safe_load(source.read_text())
    declared = set(bundle["resources"]["apps"][name].get("user_api_scopes") or [])
    if len(sys.argv) > 2 and sys.argv[2] and set(sys.argv[2].split()) != declared:
        sys.exit("Deployment environment scopes differ from databricks.yml")
    missing, extra = check(live, bundle, name)
    ineffective = declared - set(live.get("effective_user_api_scopes") or [])
    if ineffective:
        sys.exit("App scopes are not effective: " + ",".join(sorted(ineffective)))
    if missing or extra:
        print('App user scopes differ: missing=' + ','.join(sorted(missing)) + '; extra=' + ','.join(sorted(extra)))
        sys.exit(1)
    print('App user scopes match the bundle')
