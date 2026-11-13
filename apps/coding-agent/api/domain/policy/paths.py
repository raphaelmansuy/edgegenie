"""Workspace paths: reject traversal before normalizing, then compare whole segments."""

import posixpath


def normalize(path: str) -> str:
    value = posixpath.normpath(path.replace("\\", "/").strip("`\"'"))
    # Native Query definitions return /Workspace while Workspace APIs accept the shorter alias.
    if value == "/Workspace":
        return "/"
    return value[len("/Workspace") :] if value.startswith("/Workspace/") else value


def inside(path: str, folder: str) -> bool:
    raw = path.replace("\\", "/")
    base = folder.replace("\\", "/")
    if ".." in raw.split("/") or ".." in base.split("/"):
        return False
    if any(ord(c) < 32 for c in raw + base):
        return False
    p, f = normalize(raw), normalize(base).rstrip("/")
    return bool(f and f != "." and p.startswith("/") and f.startswith("/") and p.startswith(f + "/"))
