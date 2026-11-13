"""Canonical native-operation states shared by services and API projections."""

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "rejected", "not_started"})
ACTIVE = ("submitting", "running", "unobserved", "unknown", "cancelling")
