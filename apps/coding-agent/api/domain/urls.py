"""Canonical workspace URL normalization."""


def normalize_host(host: str | None) -> str:
    """Databricks Apps may provide DATABRICKS_HOST as a bare hostname; every client needs a URL."""
    h = (host or "").strip().rstrip("/")
    if h and not h.startswith(("http://", "https://")):
        h = f"https://{h}"
    return h
