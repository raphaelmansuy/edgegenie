"""Reusable revision-guarded definition lifecycle; API and bundle tiers share the same plans."""

import difflib
import json
import re
from ....domain.asset import AssetContent, AssetRef, Plan, WorkError, digest
from ....domain.edits import edit_ranges
from ....domain.policy.paths import inside
from .workspace import WorkspaceHandler


class DefinitionHandler:
    kind = ""
    scope = ""
    resource = ""

    def __init__(self, http, workspace, observations=None):
        self.http = http
        self.observations = observations
        self.files = WorkspaceHandler(workspace, "file")

    def api(self, who):
        return not who.delegated or self.scope in who.scopes

    def inside(self, ref, who):
        # IDs do not prove a fence. apply/remove re-check the actual definition's name.
        return (
            inside(ref.id, who.scope.folder)
            if ref.id.startswith("/")
            else bool(who.scope.folder and ref.id)
        )

    def name_inside(self, name, who):
        return bool(name and name.startswith(who.scope.job_prefix))

    async def probe(self, who):
        if self.api(who):
            await self.list_native(who, 1)
            return {
                "read": True,
                "change": True,
                "run": True,
                "tier": "api",
                "reason": "Uses your native API permissions; definitions and runs are checked again before dispatch.",
            }
        await self.files.probe(who)
        return {
            "read": True,
            "change": True,
            "run": False,
            "tier": "as-code",
            "reason": f"No {self.scope} user scope for this app. Definitions are written as bundles, not deployed.",
        }

    async def find(self, query, who, limit):
        if self.api(who):
            return await self.list_native(who, limit, query)
        return await self.files.find(query, who, limit)

    async def read(self, ref, who):
        if ref.id.startswith("/"):
            return await self.files.read(AssetRef("file", ref.id), who)
        if not self.api(who):
            raise PermissionError(
                "No native API scope for this app. Attach a bundle definition or inspect system-table observations."
            )
        row = await self.get_native(ref.id, who)
        text = json.dumps(row, sort_keys=True, indent=2, ensure_ascii=False)
        return AssetContent(ref, digest(row), text, "JSON", row)

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        return {
            "asset": value.ref.to_dict(),
            "revision": value.revision,
            "definition": value.metadata or json.loads(value.content),
            "tier": "api" if self.api(who) else "as-code",
        }

    async def plan(self, ref, base, ops, who, *, content=None):
        if not self.api(who):
            if not ref.id.startswith("/") or not ref.id.endswith("/databricks.yml"):
                raise WorkError(
                    "Define this asset inside the working folder as <name>/databricks.yml. It will be defined, not deployed.",
                    422,
                )
            if content is not None:
                spec = json.loads(content)
                if "resources" not in spec:
                    key = re.sub(r"\W", "_", spec.get("name", "agent_resource"))
                    spec = {"bundle": {"name": key}, "resources": {self.resource: {key: spec}}}
                content = json.dumps(spec, sort_keys=True, indent=2) + "\n"
            plan = await self.files.plan(AssetRef("file", ref.id), base, ops, who, content=content)
            return plan
        try:
            current = await self.read(ref, who)
        except LookupError:
            current = AssetContent(ref, "", "")
        if current.revision != base:
            raise WorkError(
                "Definition changed. Read the current revision and re-plan.", current=current.revision
            )
        after = content if content is not None else edit_ranges(current.content, ops)
        spec = json.loads(after)
        if not self.name_inside(spec.get("name", ""), who):
            raise WorkError("Definition name is outside this session prefix.", 403)
        if current.revision and not self.name_inside(current.metadata.get("name", ""), who):
            raise WorkError("The current resource is outside the session prefix.", 403)
        self.validate(spec, who)
        return Plan(
            ref,
            base,
            current.content,
            json.dumps(spec, sort_keys=True, indent=2),
            ops,
            "".join(
                difflib.unified_diff(
                    current.content.splitlines(True),
                    after.splitlines(True),
                    fromfile="current",
                    tofile="proposed",
                )
            )[:65536],
            language="JSON",
            effect="edit" if base else "create",
            undo_available=bool(base),
        )

    def validate(self, spec, who):
        configured = spec.get("run_as", {})
        if configured and configured != {"user_name": who.run_as}:
            raise WorkError("Agent definitions must run as the current user.", 403)

    async def apply(self, plan, who):
        if plan.ref.id.startswith("/"):
            result = await self.files.apply(plan, who)
            return result
        try:
            current = await self.read(plan.ref, who)
        except LookupError:
            current = AssetContent(plan.ref, "", "")
        if current.revision != plan.base:
            raise WorkError("Definition moved after approval.", current=current.revision)
        spec = json.loads(plan.after)
        self.validate(spec, who)
        if not self.name_inside(spec.get("name", ""), who):
            raise WorkError("Definition name is outside the session prefix.", 403)
        if current.revision and not self.name_inside(current.metadata.get("name", ""), who):
            raise WorkError("Resource moved outside the session prefix.", 403)
        native = await self.write_native(plan.ref.id, spec, current.metadata, who, create=not plan.base)
        return await self.read(AssetRef(self.kind, str(native)), who)

    async def restore(self, ref, expect, content, who, language="JSON"):
        plan = await self.plan(ref, expect, [], who, content=content)
        return await self.apply(plan, who)

    async def remove(self, ref, expect, who):
        if ref.id.startswith("/"):
            return await self.files.remove(AssetRef("file", ref.id), expect, who)
        current = await self.read(ref, who)
        if current.revision != expect:
            raise WorkError("Resource changed after creation.", current=current.revision)
        if not self.name_inside(current.metadata.get("name", ""), who):
            raise WorkError("Resource no longer has the session prefix.", 403)
        return await self.delete_native(ref.id, who)
