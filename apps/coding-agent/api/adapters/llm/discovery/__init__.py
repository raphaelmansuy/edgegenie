"""Discovery adapters: what a provider serves, right now."""

from __future__ import annotations

from .databricks import DatabricksDiscovery, DiscoveryResult

__all__ = ["DatabricksDiscovery", "DiscoveryResult"]
