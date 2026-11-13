"""Read-only bounded access to shipped playbooks; user skills use workspace file permissions."""

from pathlib import Path


class BundledSkills:
    def __init__(self, directory):
        self.directory = Path(directory)

    async def get(self, name=""):
        paths = {p.stem: p for p in sorted(self.directory.glob("*.md"))[:40]}
        rows = []
        for key, path in paths.items():
            if name and name != key:
                continue
            text = path.read_text()[:12000]
            rows.append(
                {
                    "name": key,
                    "description": text.splitlines()[0].lstrip("# ")[:300] if text else "",
                    "source": "Built-in playbook",
                    **({"text": text, "truncated": path.stat().st_size > 12000} if name else {}),
                }
            )
        return rows
