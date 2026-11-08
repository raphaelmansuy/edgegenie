"""Tests must not depend on the shell they run in.

An operator's provider keys live in `LLM_<PROVIDER>_KEY` environment variables, and the app now honours
them alongside saved keys. A developer who has one exported (to try a model by hand) would otherwise see
unrelated tests find a credential nobody put there.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _no_operator_keys(monkeypatch):
    for name in [n for n in os.environ if n.startswith("LLM_") and (n.endswith("_KEY") or n.endswith("_PROJECT"))]:
        monkeypatch.delenv(name, raising=False)
