"""Single app-side tool authority: computed catalogue, policy, effects and invocation evidence."""

import asyncio
import json
import secrets
import time
from uuid import uuid4
from ..domain.asset import AssetRef, WorkError, digest, public_record
from ..domain.edits import operation_schema
from ..domain.invocation_evidence import result_lexicon

READS = {
    "dbx_capabilities",
    "dbx_find",
    "dbx_describe",
    "dbx_read",
    "dbx_grep",
    "dbx_change",
    "dbx_operation",
    "dbx_skill",
}
# Compatibility aliases retire after the spec 014 app-path exam gate, no earlier than 2027-02-13.
ALIASES = {
    "dbx_whoami": "dbx_capabilities",
    "dbx_read_notebook": "dbx_read",
    "dbx_grep_notebook": "dbx_grep",
    "dbx_describe_table": "dbx_describe",
    "dbx_search_tables": "dbx_find",
    "dbx_list_notebooks": "dbx_find",
    "dbx_run_job": "dbx_run",
    "dbx_job_run_status": "dbx_operation",
    "dbx_run_notebook": "dbx_run",
    "dbx_run_notebook_status": "dbx_operation",
    "dbx_write_notebook": "dbx_create",
    "dbx_write_file": "dbx_create",
}
# Required/optional arguments form one per-tool schema; irrelevant fields are never advertised.
ARGUMENTS = {
    "dbx_capabilities": ((), ()),
    "dbx_skill": ((), ("name",)),
    "dbx_find": (("kind",), ("query", "limit")),
    "dbx_describe": (("kind", "id"), ()),
    "dbx_read": (("kind", "id"), ("offset", "cell")),
    "dbx_grep": (("kind", "id", "pattern"), ()),
    "dbx_edit": (("kind", "id", "base", "ops"), ()),
    "dbx_create": (("kind", "id", "content"), ()),
    "dbx_define": (("kind", "id", "spec"), ("base",)),
    "dbx_run": (("kind", "id"), ("params",)),
    "dbx_run_sql": (("sql",), ("parameters", "warehouse_id", "wait_seconds")),
    "dbx_change": (("id",), ("undo", "reconcile")),
    "dbx_operation": (("id",), ("cancel", "chunk")),
    "dbx_cleanup": ((), ("cursor",)),
}
DESCRIPTIONS = {
    "dbx_capabilities": "Identity, fence, autonomy mode and available asset capabilities.",
    "dbx_find": "Find accessible assets of kind with a bounded query.",
    "dbx_describe": "Read the asset definition, schema and revision before making any change.",
    "dbx_read": "Read a source page and revision; follow next_offset until the selected source is read. For a focused notebook edit, pass zero-based cell to read just that cell's raw source and SHA without echoing all other cells. cellOnly explicitly identifies a partial notebook read.",
    "dbx_grep": "Search source lines by pattern; no_matches means retry with a looser pattern.",
    "dbx_edit": "Propose operations against base revision. Cell ops use zero-based index (not cell_index), sha from dbx_read, and source including original surrounding whitespace. File replace_range uses zero-based character start/end, sha and text. Review never writes without a decision.",
    "dbx_create": "Propose a new asset; existing assets require dbx_edit and a base revision.",
    "dbx_define": "Propose a job, pipeline or app definition. As-code tiers are defined, not deployed.",
    "dbx_run": "Submit one durable operation as the user. Repeated arguments return the existing operation.",
    "dbx_run_sql": "Execute SQL through the shared SQL service; returns an operation handle quickly.",
    "dbx_change": "Read a change, optionally reconcile unknown outcome or request undo.",
    "dbx_operation": "Read/poll an operation, optionally cancel; never resubmit a pending operation.",
    "dbx_cleanup": "Review deletion of resources recorded as created by this session.",
    "dbx_skill": "List or load bounded playbooks and user/workspace skills.",
}


class Toolbox:
    def __init__(
        self, registry, store, events, changes, operations, sessions, capabilities, actor, skills=None
    ):
        self.registry, self.store, self.events = registry, store, events
        self.changes, self.operations, self.sessions, self.capabilities = (
            changes,
            operations,
            sessions,
            capabilities,
        )
        self.actor, self.skills = actor, skills
        self._keys = {}
        self._locks = {}

    def issue(self, sid):
        return self._keys.setdefault(sid, secrets.token_urlsafe(32))

    def verify(self, sid, key):
        return bool(key and sid in self._keys and secrets.compare_digest(self._keys[sid], key))

    def revoke(self, sid):
        self._keys.pop(sid, None)

    def catalogue(self, sid):
        kinds = [r["kind"] for r in self.capabilities.rows(sid) if r.get("read")]
        change = [r["kind"] for r in self.capabilities.rows(sid) if r.get("change")]
        run = [r["kind"] for r in self.capabilities.rows(sid) if r.get("run")]
        names = set(READS)
        if self.sessions.mode(sid) != "plan":
            if change:
                names.update({"dbx_edit", "dbx_create", "dbx_define", "dbx_cleanup"})
            if run:
                names.add("dbx_run")
            if "statement" in run:
                names.add("dbx_run_sql")
        result = []
        for name in sorted(names):
            allowed = (
                change
                if name in ("dbx_edit", "dbx_create", "dbx_define")
                else run
                if name == "dbx_run"
                else kinds
            )
            schema = {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": allowed},
                    "id": {"type": "string"},
                    "query": {"type": "string"},
                    "pattern": {"type": "string"},
                    "base": {"type": "string"},
                    "ops": {"type": "array", "maxItems": 100, "items": operation_schema()},
                    "content": {"type": "string"},
                    "spec": {"type": "object"},
                    "params": {"type": "object"},
                    "sql": {"type": "string"},
                    "parameters": {"type": "array", "items": {"type": "object"}},
                    "warehouse_id": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "cell": {"type": "integer", "minimum": 0},
                    "cursor": {"type": "string", "maxLength": 4096},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    "wait_seconds": {"type": "integer", "minimum": 0, "description": "Compatibility option: SQL always returns a durable handle immediately. The effective wait is zero; observe with dbx_operation."},
                    "undo": {"type": "boolean"},
                    "cancel": {"type": "boolean"},
                    "reconcile": {"type": "boolean"},
                    "chunk": {"type": "integer", "minimum": 0, "maximum": 10000},
                    "name": {"type": "string"},
                },
                "additionalProperties": False,
            }
            required, optional = ARGUMENTS[name]
            schema["properties"] = {key: schema["properties"][key] for key in (*required, *optional)}
            schema["required"] = list(required)
            result.append({"name": name, "description": DESCRIPTIONS[name], "inputSchema": schema})
        return result

    def canonical(self, name, args):
        alias = name
        name = ALIASES.get(name, name)
        args = dict(args)
        inferred = {
            "dbx_read_notebook": "notebook",
            "dbx_grep_notebook": "notebook",
            "dbx_list_notebooks": "notebook",
            "dbx_describe_table": "table",
            "dbx_search_tables": "table",
            "dbx_run_job": "job",
            "dbx_run_notebook": "notebook",
            "dbx_write_notebook": "notebook",
            "dbx_write_file": "file",
        }
        if alias in inferred:
            args.setdefault("kind", inferred[alias])
        for field in ("path", "full_name", "job_id", "run_id", "handle"):
            if field in args:
                args.setdefault("id", str(args.pop(field)))
        if "source" in args:
            args.setdefault("content", args.pop("source"))
        if args.get("overwrite"):
            # Alias must not silently restore whole-document overwrite behavior.
            raise WorkError("Legacy overwrite is refused. Read the base revision and use dbx_edit.", 422)
        args.pop("overwrite", None)
        return name, args

    async def dispatch(self, sid, tid, name, args):
        name, args = self.canonical(name, args)
        await self.sessions.prepare(sid)
        if name not in {t["name"] for t in self.catalogue(sid)}:
            raise WorkError("This tool is unavailable in the current capability or autonomy mode.", 403)
        self.sessions.check(sid)
        who = self.actor(sid, tid)
        if "kind" in args:
            verb = (
                "change"
                if name in ("dbx_edit", "dbx_create", "dbx_define")
                else "run"
                if name == "dbx_run"
                else "read"
            )
            if not self.capabilities.allows(sid, args["kind"], verb):
                raise WorkError(
                    "This asset capability is unavailable for your session. Re-check permissions before continuing.",
                    403,
                )
        inv = {
            "id": "inv_" + uuid4().hex[:20],
            "sessionId": sid,
            "owner": who.user_id,
            "turnId": tid,
            "tool": name,
            "argsDigest": digest(args),
            "asset": {
                "kind": args.get("kind", "statement" if name == "dbx_run_sql" else ""),
                "id": str(args.get("id", "")),
            },
            "actionClass": "read" if name in READS else "change",
            "state": "running",
            "createdAt": time.time(),
        }
        inv = await self.store.put("invocation", inv)
        try:
            result = await asyncio.wait_for(self._execute(sid, tid, name, args, inv["id"]), 28)
            if name in ("dbx_edit", "dbx_create", "dbx_define", "dbx_run", "dbx_run_sql") and result.get(
                "state"
            ) in ("refused", "failed", "conflicted", "rejected"):
                raise WorkError(
                    result.get("reason", "Change refused"), 403 if result["state"] == "refused" else 409
                )
            encoded = json.dumps(result, ensure_ascii=False, default=str)
            observed = encoded[:65536]
            result_tokens, tokens_truncated = result_lexicon(result)
            inv = {
                **inv,
                "asset": result.get("asset", inv["asset"]) if isinstance(result, dict) else inv["asset"],
                "observedRevision": result.get("revision", "") if isinstance(result, dict) else "",
                "effectState": result.get("state", "") if isinstance(result, dict) else "",
                "state": "completed",
                "resultDigest": digest(encoded),
                "resultSummary": observed[:1200],
                "resultTokens": result_tokens[:4096],
                "resultTruncated": len(encoded) > 65536 or tokens_truncated,
                "finishedAt": time.time(),
            }
            await self.store.put("invocation", inv, inv["version"])
            return (
                {**result, "invocationId": inv["id"]}
                if isinstance(result, dict)
                else {"result": result, "invocationId": inv["id"]}
            )
        except Exception as exc:
            await self.store.put(
                "invocation",
                {**inv, "state": "failed", "reason": str(exc)[:300], "finishedAt": time.time()},
                inv["version"],
            )
            if isinstance(exc, PermissionError) and args.get("kind"):
                await self.capabilities.downgrade(sid, args["kind"], str(exc))
            raise

    async def proposal(self, sid, tid, name, args, invocation="", *, force_review=False):
        if not self.capabilities.allows(sid, args.get("kind", ""), "change"):
            raise WorkError("This identity cannot change this asset kind.", 403)
        key = digest([sid, tid, name, args])
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # A native approval and the following facade call must find the same change.
            record, fresh = await self.store.reserve(
                "approval",
                key,
                {
                    "id": "grant_" + uuid4().hex[:20],
                    "sessionId": sid,
                    "owner": self.actor(sid, tid).user_id,
                    "turnId": tid,
                    "state": "planning",
                    "createdAt": time.time(),
                    "tool": name,
                    "argsDigest": digest(args),
                },
            )
            if record.get("changeId"):
                return (
                    await self.changes.bind_invocation(sid, record["changeId"], invocation)
                    if invocation
                    else public_record(await self.changes.get(sid, record["changeId"]))
                )
            if not fresh:
                raise WorkError("The proposal outcome is unknown; do not repeat the write.")
            ref = AssetRef(args.get("kind", ""), str(args.get("id", "")))
            content = args.get("content")
            if name == "dbx_define":
                content = json.dumps(args.get("spec", {}), sort_keys=True, indent=2)
            result = await self.changes.propose(
                sid,
                tid,
                invocation,
                ref,
                args.get("base", ""),
                args.get("ops", []),
                content,
                force_review=force_review,
            )
            await self.store.put(
                "approval", {**record, "changeId": result["id"], "state": "linked"}, record["version"]
            )
            return result

    def run_request(self, name, args):
        if name == "dbx_run_sql":
            return AssetRef("statement", digest(args.get("sql", ""))), {
                k: args[k] for k in ("sql", "parameters", "warehouse_id") if k in args
            }
        return AssetRef(args.get("kind", ""), str(args.get("id", ""))), args.get("params", {})

    async def _execute(self, sid, tid, name, args, invocation):
        who = self.actor(sid, tid)
        if name == "dbx_capabilities":
            return {
                "identity": who.user_id,
                "mode": self.sessions.mode(sid),
                "fence": {"folder": who.scope.folder, "schema": who.scope.schema},
                "capabilities": self.capabilities.rows(sid),
                "toolCount": len(self.catalogue(sid)),
            }
        if name == "dbx_skill":
            return await self.skills.get(who, args.get("name", "")) if self.skills else {"skills": []}
        if name in ("dbx_edit", "dbx_create", "dbx_define"):
            return await self.proposal(sid, tid, name, args, invocation)
        if name == "dbx_change":
            cid = args.get("id", "")
            if args.get("undo"):
                if self.sessions.mode(sid) != "auto":
                    raise WorkError("Request undo from the Changes screen so it can be reviewed.")
                return await self.changes.undo(sid, cid, who.user_id)
            if args.get("reconcile"):
                return await self.changes.reconcile(sid, cid)
            return public_record(await self.changes.get(sid, cid))
        if name == "dbx_operation":
            if args.get("chunk") is not None:
                return await self.operations.result_page(sid, args["id"], args["chunk"])
            if args.get("cancel") and self.sessions.mode(sid) == "plan":
                raise WorkError("Plan mode cannot cancel workspace operations.", 403)
            return await (
                self.operations.cancel(sid, args["id"])
                if args.get("cancel")
                else self.operations.observe(sid, args["id"])
            )
        if name == "dbx_cleanup":
            page = await self.store.page(
                "resource",
                session_id=sid,
                states=("present", "cleanup_pending"),
                limit=100,
                cursor=args.get("cursor", ""),
            )
            return {
                "resources": [public_record(r) for r in page["items"]],
                "nextCursor": page["nextCursor"],
                "message": "Review cleanup in the Resources screen. Deletion always requires your decision.",
            }
        if name in ("dbx_run", "dbx_run_sql"):
            requested_wait = args.get("wait_seconds", 0)
            if name == "dbx_run_sql" and (isinstance(requested_wait, bool) or not isinstance(requested_wait, int) or requested_wait < 0):
                raise WorkError("wait_seconds must be a non-negative integer. SQL returns a handle immediately.", 422)
            ref, params = self.run_request(name, args)
            result = await self.run(sid, tid, invocation, ref, params)
            if name == "dbx_run_sql":
                result = {**result, "requestedWaitSeconds": requested_wait, "effectiveWaitSeconds": 0,
                          "waitClamped": requested_wait != 0,
                          "waitMessage": "SQL returns a durable handle without waiting. Observe it with dbx_operation; do not resubmit."}
            return result
        ref = AssetRef(args.get("kind", ""), str(args.get("id", "")))
        handler = self.registry.handler(ref.kind)
        if name == "dbx_find":
            return {
                "items": await handler.find(args.get("query", ""), who, min(args.get("limit", 25), 100))
            }
        if name == "dbx_describe":
            return await handler.describe(ref, who)
        value = await handler.read(ref, who)
        if name == "dbx_read":
            content, metadata = value.content, {}
            selector = getattr(handler, "read_fragment", None)
            if selector:
                content, metadata = selector(value, cell=args.get("cell"))
            elif "cell" in args:
                raise WorkError("This asset does not support cell selection.", 422)
            if len(value.content.encode()) <= 2 * 1024 * 1024:
                snapshot_id = digest([sid, ref.to_dict(), value.revision])
                await self.store.reserve(
                    "previous_content",
                    snapshot_id,
                    {
                        "id": snapshot_id,
                        "sessionId": sid,
                        "owner": who.user_id,
                        "asset": ref.to_dict(),
                        "state": "observed",
                        "createdAt": time.time(),
                        "revision": value.revision,
                        "language": value.language,
                        "_content": value.content,
                    },
                )
            offset = max(0, int(args.get("offset", 0)))
            size = 6000
            body = {
                "asset": ref.to_dict(),
                "revision": value.revision,
                "text": content[offset : offset + size],
                "offset": offset,
                "total": len(content),
                "next_offset": offset + size if offset + size < len(content) else None,
            }
            body.update(metadata)
            if metadata.get("cellOnly"):
                body["cells"][0].update(source=body["text"], truncated=bool(offset or body["next_offset"]))
            return body
        if name == "dbx_grep":
            pattern = args.get("pattern", "").casefold()
            matches = [
                {"line": i + 1, "text": line[:1000]}
                for i, line in enumerate(value.content.splitlines())
                if pattern in line.casefold()
            ]
            return {
                "revision": value.revision,
                "matches": matches[:100],
                "no_matches": not matches,
                "capped": len(matches) > 100,
            }
        if name == "dbx_cleanup":
            raise WorkError(
                "Use the resource ledger to review cleanup. No resource is deleted automatically."
            )
        raise WorkError("Unsupported tool.", 422)

    async def run(self, sid, tid, invocation, ref, params, *, force_review=False):
        if not self.capabilities.allows(sid, ref.kind, "run"):
            raise WorkError("This identity cannot run this asset.", 403)
        # Run authorization is durable and argument-bound, enforced again at dispatch.
        who = self.actor(sid, tid)
        key = digest([sid, tid, "run", ref.to_dict(), params])
        try:
            permit = await self.store.get("approval", "run_" + key)
        except WorkError:
            permit = None
        handler = self.registry.handler(ref.kind)
        needs_review = getattr(handler, "requires_review", lambda p: False)(params)
        if force_review or self.sessions.mode(sid) != "auto" or needs_review:
            if not permit or permit["state"] != "allowed":
                if not permit:
                    permit = await self.store.put(
                        "approval",
                        {
                            "id": "run_" + key,
                            "sessionId": sid,
                            "owner": who.user_id,
                            "turnId": tid,
                            "state": "pending",
                            "action": "run",
                            "asset": ref.to_dict(),
                            "arguments": params,
                            "_params": params,
                            "createdAt": time.time(),
                        },
                    )
                    await self.events.commit(
                        [], sid, tid, "run.review_required", {"review": public_record(permit)}, who.user_id
                    )
                return {
                    "state": "awaiting_review",
                    "reviewId": permit["id"],
                    "message": "A run needs your decision. End the turn; the server retains this request.",
                }
        return await self.operations.submit(sid, tid, "dbx_run", ref, params)

    async def decide_run(self, sid, rid, allow):
        row = await self.store.get("approval", rid)
        if row["sessionId"] != sid:
            raise WorkError("No such run review.", 404)
        if row["state"] == ("allowed" if allow else "rejected"):
            return (
                await self.operations.submit(
                    sid, row["turnId"], "dbx_run", AssetRef(**row["asset"]), row["_params"]
                )
                if allow
                else public_record(row)
            )
        if row["state"] != "pending":
            raise WorkError("This run request was already decided.")
        row = await self.store.put(
            "approval", {**row, "state": "allowed" if allow else "rejected"}, row["version"]
        )
        if not allow:
            return public_record(row)
        return await self.operations.submit(
            sid, row["turnId"], "dbx_run", AssetRef(**row["asset"]), row["_params"]
        )
