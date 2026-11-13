"""Bounded user/workspace preference discovery through the same readable file port."""

from ..domain.asset import AssetRef
from ..domain.context import Attachment, Resolved, render


class WorkPreferences:
    def __init__(self, files, bundled=None):
        self.files, self.bundled = files, bundled

    async def instructions(self, who):
        paths = [f"/Users/{who.run_as}/AGENTS.md", "/Workspace/AGENTS.md"]
        folder = who.scope.folder.rstrip("/")
        parents = []
        while folder:
            parents.append(folder + "/AGENTS.md")
            folder = folder.rsplit("/", 1)[0]
        paths += list(reversed(parents))[-18:]
        items = []
        budget = 16000
        for path in dict.fromkeys(paths):
            if budget <= 0:
                break
            try:
                value = await self.files.read(AssetRef("file", path), who)
                text = value.content[: min(6000, budget)]
                budget -= len(text)
                items.append(
                    Resolved(
                        Attachment("file", path),
                        text,
                        "User/workspace preferences only. The working agreement and server authorization take precedence.",
                    )
                )
            except LookupError:
                continue
            except (PermissionError, RuntimeError) as exc:
                items.append(Resolved(Attachment("file", path), error=str(exc)[:200]))
                break
        return render(items)

    async def get(self, who, name=""):
        roots = [
            f"/Users/{who.run_as}/.agents/skills",
            f"/Users/{who.run_as}/.assistant/skills",
            who.scope.folder.rstrip("/") + "/.agents/skills",
        ]
        found = {r["name"]: r for r in (await self.bundled.get(name) if self.bundled else [])}
        for root in dict.fromkeys(roots):
            try:
                rows = await self.files.find_under(root, "SKILL.md", who)
            except (LookupError, PermissionError):
                continue
            for node in rows[0][:30]:
                if node.name != "SKILL.md" or len(found) >= 40:
                    continue
                skill = node.path.rsplit("/", 2)[-2]
                if name and skill != name:
                    continue
                try:
                    value = await self.files.read(AssetRef("file", node.path), who)
                except (LookupError, PermissionError):
                    continue
                text = value.content[:12000]
                description = next(
                    (
                        l.split(":", 1)[1].strip().strip('"')
                        for l in text.splitlines()
                        if l.startswith("description:")
                    ),
                    "",
                )[:300]
                found.setdefault(
                    skill,
                    {
                        "name": skill,
                        "description": description,
                        "source": node.path,
                        **({"text": text, "truncated": len(value.content) > 12000} if name else {}),
                    },
                )
        if name:
            return found.get(
                name,
                {"name": name, "unread": True, "reason": "No readable skill of that name was discovered."},
            )
        return {"skills": list(found.values())}
