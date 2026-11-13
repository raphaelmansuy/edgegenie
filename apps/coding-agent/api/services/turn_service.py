"""TurnService owns one part of the orchestrator lifecycle; it depends on domain values and ports."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import logging
import time

from ..domain import supervisor
from ..domain.query_intent import attached_query, query_explanation_only
from ..domain.events import (
    Event,
    approval_decided,
    evidence_proposed,
    turn_auditing,
    turn_blocked,
    turn_completed,
    turn_ended,
    turn_started,
    tool_updated,
)
from ..domain.evidence import DEMO_MARKER, extract_requirements, is_read_only, says_no_tools
from ..domain.redact import redact_labelled
from ..domain.session import (
    DomainError,
    SessionStatus,
    Turn,
    TurnStatus,
    title_from,
    updated,
)


from .session_state import Live, MAX_TURNS


class TurnService:
    async def cancel(self, session_id: str) -> None:
        live = self.get(session_id)
        async with live.lock:
            # Stop means the entire accepted queue stops. It must not launch another write next.
            live.cancel = True
            await self._cancel_agent_sql(live)
            if self.work:
                await self.work.expire(session_id)
            live.extra["stopping"] = True
            for turn in list(live.state.turns):
                if turn.status is TurnStatus.QUEUED:
                    live.state.update(turn.finish(TurnStatus.CANCELLED))
                    await self._emit(turn_ended(session_id, turn.id, "cancelled"))
            await self._expire_prompts(live, "cancelled")
            if live.handle:
                await self._rt.cancel(live.handle)
            if live.task and not live.task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(live.task), 2)
                except TimeoutError:
                    live.task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await live.task
                    if live.handle:
                        live.extra["agent_session_id"] = live.handle.session_id
                        await self._rt.close(live.handle)
                        live.handle = None
                    for active in list(live.state.turns):
                        if active.status in (TurnStatus.RUNNING, TurnStatus.AUDITING):
                            live.state.update(active.finish(TurnStatus.CANCELLED))
                            await self._emit(turn_ended(session_id, active.id, "cancelled"))
                    live.state.session = updated(
                        live.state.session, status=SessionStatus.BLOCKED, requires_resume=True
                    )
                    await self._emit(
                        Event(session_id, "session.recovery_required", {"requiresResume": True})
                    )
            if not live.task or live.task.done():
                live.cancel = False
                live.extra["stopping"] = False

    async def submit(
        self,
        session_id: str,
        text: str,
        context: str = "",
        attachments: list[dict] | None = None,
        user_token: str | None = None,
        request_key: str = "",
        request_hash: str = "",
    ) -> Turn:
        live = self.get(session_id)
        async with live.lock:
            if request_key:
                previous = next((t for t in live.state.turns if t.request_key == request_key), None)
                if previous:
                    if previous.request_hash != request_hash:
                        raise DomainError("this retry key was already used for another message")
                    return previous
            return await self._submit(
                live, text, context, attachments, user_token, request_key, request_hash
            )

    async def _submit(
        self,
        live: Live,
        text: str,
        context: str,
        attachments,
        user_token,
        request_key: str,
        request_hash: str,
    ) -> Turn:
        session_id = live.state.session.id
        if live.state.session.status is SessionStatus.ARCHIVED:
            raise DomainError("this session is archived")
        if live.state.session.requires_resume:
            raise DomainError("restore this session before sending a new message")
        if live.state.session.status not in (
            SessionStatus.READY,
            SessionStatus.STREAMING,
            SessionStatus.BLOCKED,
        ):
            raise DomainError("this session is not ready")
        if len(live.state.turns) >= self._max_turns:
            raise DomainError(f"this session reached its limit of {self._max_turns} turns")
        if live.extra.get("stopping"):
            raise DomainError("the agent is stopping; wait before sending another message")
        self._write_token(live, user_token, keep_in_app=bool(self.work))
        live.cancel = False
        running = live.state.running()
        if self.work:
            for previous in list(live.state.turns):
                if previous.status is TurnStatus.PAUSED:
                    live.state.update(previous.finish(TurnStatus.COMPLETED))
                    await self._emit(turn_completed(session_id, previous.id, "continued", {}, 0))
        asked = text
        text = DEMO_MARKER.sub(" ", text).strip()  # never store a demo hint as the user's words
        # A key pasted into a prompt is a user error the app must survive (S12/E-8): the stored
        # payload is redacted and labelled, and the turn continues.
        stored_text = redact_labelled(text)
        # The reference agent still needs the hint: it is how one demo server plays every behaviour.
        # It goes in `context`, which is sent but is not the user's words — stripping it from `prompt`
        # alone had quietly stopped the start cards from choosing (the "investigate a number" card
        # answered with a notebook).
        hint = DEMO_MARKER.search(asked) if self._demo else None
        turn = live.state.new_turn(
            stored_text,
            f"{context} {hint.group(0).strip()}" if hint else context,
            # References, not content: the transcript renders these chips on reload, and a blob is one id.
            [
                {"kind": a.get("kind", ""), "ref": a.get("ref", ""), "name": a.get("name", "")}
                for a in (attachments or [])
            ],
        )
        turn = updated(
            turn, request_key=request_key, request_hash=request_hash, context=redact_labelled(turn.context)
        )
        live.state.update(turn)
        if not live.state.turns[:-1] and live.state.session.title == "New session":
            live.state.session = updated(live.state.session, title=title_from(stored_text))
        # The pin is written BEFORE the prompt and never updated (Axiom A5, C-8).
        await self._pin_turn(live, turn)
        # The accepted prompt, retry receipt, and queue entry are one commit before HTTP 202.
        try:
            await self._emit(
                turn_started(session_id, turn.id, stored_text, live.state.session.model, attachments)
            )
        except Exception:
            live.state.turns.remove(turn)
            raise
        if running is not None:
            await self._emit(Event(session_id, "turn.queued", {}, turn_id=turn.id))
        if running is None:
            live.task = asyncio.create_task(self._run_turn(live, turn.id))
        return turn

    async def _interrupt_pending(self, live: Live, reason: str) -> None:
        for queued in list(live.state.turns):
            if queued.status is TurnStatus.QUEUED:
                live.state.update(queued.finish(TurnStatus.INTERRUPTED, error=reason))
                await self._emit(turn_ended(live.state.session.id, queued.id, "interrupted", reason))

    async def _run_turn(self, live: Live, turn_id: str) -> None:
        if next(t for t in live.state.turns if t.id == turn_id).status is TurnStatus.CANCELLED:
            live.cancel = False
            live.extra["stopping"] = False
            return
        try:
            async with self._slots:
                expiry = live.extra.get("token_expires_at")
                budget = (
                    min(self._max_run_seconds, max(0, expiry - time.time() - 15))
                    if expiry
                    else self._max_run_seconds
                )
                loop = asyncio.get_running_loop()
                live.extra["absolute_deadline"] = loop.time() + self._max_run_seconds
                async with asyncio.timeout(budget) as deadline:
                    live.extra["deadline"] = deadline
                    if live.handle is None:
                        await self._provision(live)
                    await self._execute_turn(live, turn_id)
        except TimeoutError:
            live.cancel = True
            await self._expire_prompts(live)
            if live.handle:
                await self._rt.close(live.handle)
                live.extra["agent_session_id"] = live.handle.session_id
                live.handle = None
            turn = next(t for t in live.state.turns if t.id == turn_id)
            live.state.update(
                turn.finish(
                    TurnStatus.INTERRUPTED, error="The runtime or delegated credential limit was reached."
                )
            )
            live.state.session = updated(
                live.state.session, status=SessionStatus.BLOCKED, requires_resume=True
            )
            await self._emit(
                turn_ended(
                    live.state.session.id,
                    turn_id,
                    "interrupted",
                    "The runtime or delegated credential limit was reached. Restore with a fresh sign-in and review progress before continuing.",
                )
            )
            await self._interrupt_pending(
                live, "Queued work was not started because the preceding turn was interrupted."
            )
            await self._emit(
                Event(live.state.session.id, "session.recovery_required", {"requiresResume": True})
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("app.runner").exception("session journal or worker failed; closing agent")
            if live.handle:
                live.extra["agent_session_id"] = live.handle.session_id
                await self._rt.close(live.handle)
                live.handle = None
            live.state.session = updated(
                live.state.session, status=SessionStatus.BLOCKED, requires_resume=True
            )

        finally:
            live.extra.pop("deadline", None)
            live.extra.pop("absolute_deadline", None)

    async def _execute_turn(self, live: Live, turn_id: str) -> None:
        sid = live.state.session.id
        candidate = next(t for t in live.state.turns if t.id == turn_id)
        if candidate.status is TurnStatus.CANCELLED or live.state.session.status is SessionStatus.ARCHIVED:
            live.cancel = False
            live.extra["stopping"] = False
            return
        if self.work:
            await self.work.prepare(sid)
            try:
                self.work.sessions.check_pass(
                    sid,
                    candidate.context + candidate.prompt,
                    live.resolved.output if live.resolved else 4000,
                )
            except Exception as exc:
                self._finish(live, candidate.finish(TurnStatus.BLOCKED, error=str(exc)))
                live.state.session = updated(live.state.session, status=SessionStatus.BLOCKED)
                await self._emit(Event(sid, "budget.reached", {"reason": str(exc)}, turn_id=turn_id))
                await self._emit(turn_blocked(sid, turn_id, str(exc), [], []))
                return
        turn = live.state.claim(turn_id)
        live.state.session = live.state.session.transition(SessionStatus.STREAMING)
        self._rt.set_turn(sid, turn.id)
        live.state.calls.clear()  # evidence is scoped to THIS turn
        await self._emit(Event(sid, "turn.retrying", {}, turn_id=turn.id))
        started = time.time()
        parts: list[str] = []
        ended: dict = {"error": "no result"}
        usage: dict = {}
        try:
            # Bind the blobs to this turn BEFORE the prompt: refcount is what protects them from the
            # sweeper, and until this was called every attached blob had refcount 0 — so a transcript chip
            # would survive 24 hours and then point at bytes that no longer existed ([AFC-8], [BLB-3]).
            # It is also where a blob uploaded before a session existed adopts the session.
            await self._bind_blobs(live, turn)
            images = await self._images_for(live, turn)
            await self._rt.prompt_in_background(  # type: ignore[attr-defined]
                live.handle, turn.context + turn.prompt, images
            )
            ended, usage, new_text = await self._drain(live)
            parts.append(new_text)
            if live.cancel:
                ended = {"stop": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - a runtime failure must not escape
            ended = {"error": str(exc)[:400]}
        await self._settle(live, turn, "".join(parts), ended, usage, time.time() - started)

    async def _bind_blobs(self, live: Live, turn) -> None:
        """Record that this turn references these blobs. Best-effort: never fail a turn over bookkeeping."""
        if self._blobs is None or not turn.attachments:
            return
        for att in turn.attachments:
            if att.get("kind") != "blob":
                continue
            ref = att.get("ref") or ""
            try:
                await self._blobs.store.mark_attached(
                    ref, turn.id, att.get("name") or "", live.state.session.id
                )
            except Exception:  # noqa: BLE001 - provenance must not block a turn
                pass

    async def _images_for(self, live: Live, turn) -> list[dict]:
        """The image attachments this turn carries, as ACP image blocks.

        Only images: everything else is already text in `render()`, and sending a CSV twice would double
        the prompt for no benefit. A blob that has gone missing is skipped here and was already reported to
        the model by `render()` as unavailable, so this adds nothing to say.
        """
        if self._blobs is None or not turn.attachments:
            return []
        out: list[dict] = []
        for att in turn.attachments:
            if att.get("kind") != "blob":
                continue
            try:
                row = await self._blobs.store.meta(att.get("ref", ""), live.state.session.user_id)
                if not str(row.mime).startswith("image/"):
                    continue
                raw = await self._blobs.store.bytes_for(att["ref"], live.state.session.user_id)
            except (LookupError, KeyError):
                continue
            out.append(
                {
                    "data": base64.b64encode(raw).decode(),
                    "mimeType": row.mime,
                    "name": att.get("name") or row.original_name,
                }
            )
        return out

    async def _drain(self, live: Live) -> tuple[dict, dict, str]:
        """Consume one turn's events. Returns (end, usage, answer text)."""
        assert live.handle
        ended: dict = {"error": "no result"}
        usage: dict = {}
        parts: list[str] = []
        async for item in self._rt.events(live.handle):
            if live.cancel:  # set by /cancel while this turn was streaming
                ended = {"stop": "cancelled"}
                break
            if isinstance(item, tuple):
                kind, value = item
                if kind == "end":
                    ended, usage = {"stop": value.stop_reason}, value.usage
                else:
                    ended = {"error": str(value)}
                break
            if item.type == "question.requested":
                live.extra.setdefault("questions", {})[item.payload["id"]] = item.payload
            if item.type == "tool_call.updated" and item.payload.get("callId") in live.extra.get(
                "declined_calls", set()
            ):
                # The protocol reports rejection as failed. Preserve the owner's actual decision,
                # including late updates, without inventing an execution failure.
                item = dataclasses.replace(
                    item,
                    payload={
                        **item.payload,
                        "status": "declined",
                        "summary": "Not executed: rejected by your decision.",
                        "error": "",
                    },
                )
            if item.type == "approval.requested":
                live.extra.setdefault("approvals", {})[item.payload["approvalId"]] = item.payload
            if item.type == "tool_call.updated" and item.payload.get("rawInput"):
                raw = item.payload["rawInput"]
                if isinstance(raw, dict):
                    for request in list(live.extra.get("approvals", {}).values()):
                        if request.get("callId") == item.payload["callId"]:
                            request.update(
                                input=raw,
                                argumentsKnown=True,
                                target=str(
                                    next(
                                        (
                                            raw[k]
                                            for k in ("path", "id", "full_name", "name", "sql")
                                            if raw.get(k)
                                        ),
                                        "Tool input",
                                    )
                                ),
                            )
            if self.work:
                if item.type == "usage.updated":
                    item = dataclasses.replace(
                        item,
                        payload={
                            "usage": await self.work.sessions.meter(
                                live.state.session.id, item.payload.get("usage", {}), live.handle.session_id
                            )
                        },
                    )
                if item.type == "approval.requested":
                    await self._link_native_proposal(live, item.turn_id, item.payload)
                elif item.type == "tool_call.updated" and item.payload.get("rawInput"):
                    for request in list(live.extra.get("approvals", {}).values()):
                        if (
                            request.get("callId") == item.payload["callId"]
                            and not request.get("changeId")
                            and not request.get("runReviewId")
                        ):
                            await self._link_native_proposal(live, item.turn_id, request)
            await self._emit(item)
            for request in list(live.extra.get("approvals", {}).values()):
                invalid = request.pop("_validationFailure", "")
                if invalid and hasattr(self._rt, "fail_permission"):
                    await self._rt.fail_permission(live.handle, request["approvalId"], invalid)
                    live.extra["approvals"].pop(request["approvalId"], None)
                    await self._emit(
                        approval_decided(
                            live.state.session.id, item.turn_id, request["approvalId"], "invalid", "app"
                        )
                    )
                    continue
                outcome = request.pop("_recordedOutcome", None)
                if outcome:
                    kind = "reject_once" if outcome == "deny" else "allow_once"
                    option = next(
                        (o["optionId"] for o in request.get("options", []) if o["kind"] == kind), None
                    )
                    await self.approve(
                        live.state.session.id,
                        request["approvalId"],
                        outcome,
                        option,
                        live.state.session.user_id,
                    )
            if item.type == "message.delta":
                parts.append(item.payload.get("text", ""))
            elif item.type == "tool_call.started":
                live.record(item.payload["callId"], item.payload["name"], "running")
            elif item.type == "tool_call.updated":
                live.record(
                    item.payload["callId"],
                    "",
                    item.payload.get("status", ""),
                    item.payload.get("summary", ""),
                    item.payload.get("args", ""),
                    proof=item.payload.get("proof"),
                )
        return ended, usage, "".join(parts)

    async def _expire_prompts(self, live, state="expired"):
        sid = live.state.session.id
        for aid in list(live.extra.get("approvals", {})):
            del live.extra["approvals"][aid]
            await self._emit(approval_decided(sid, None, aid, state, "app"))
        for question in live.extra.get("questions", {}).values():
            if question.get("state") == "pending":
                question["state"] = state
                await self._emit(Event(sid, "question.decided", {"id": question["id"], "state": state}))

    async def _link_native_proposal(self, live, tid, request):
        from ..domain.asset import WorkError

        try:
            await self.work.native_proposal(live.state.session.id, tid, request)
        except (WorkError, ValueError, PermissionError) as exc:
            # Invalid input must not crash the ACP reader or close a live permission channel.
            # Keep the native rejection surface; dispatch cannot receive a write grant.
            request["validationError"] = str(exc)[:300]
            request["argumentsKnown"] = False
            request["_validationFailure"] = str(exc)[:300]

    async def _settle(
        self,
        live: Live,
        turn: Turn,
        answer: str,
        ended: dict,
        usage: dict,
        seconds: float,
        continuations: int = 0,
        audits: int = 0,
    ) -> None:
        sid = live.state.session.id
        if self.work:
            await self.work.sessions.record_pass(sid, turn.id, usage, continuations + audits + 1)
        if live.cancel or ended.get("stop") == "cancelled":
            live.cancel = False
            live.extra["stopping"] = False
            self._finish(live, turn.finish(TurnStatus.CANCELLED))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            await self._emit(turn_ended(sid, turn.id, "cancelled"))
            self._start_next(live)
            return
        if "error" in ended:
            await self._expire_prompts(live)
            if self.work:
                await self.work.expire(sid)
            await self._classify_failure(live, ended["error"], turn.id)
            self._finish(live, turn.finish(TurnStatus.FAILED, error=ended["error"][:400]))
            live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
            if live.handle:
                live.extra["agent_session_id"] = live.handle.session_id
                await self._rt.close(live.handle)
                live.handle = None
            live.state.session = updated(live.state.session, requires_resume=True)
            await self._emit(turn_ended(sid, turn.id, "failed", ended["error"][:400]))
            await self._emit(Event(sid, "session.recovery_required", {"requiresResume": True}))
            await self._interrupt_pending(
                live, "Queued work was not started because the preceding turn failed."
            )
            return

        passes = live.extra.setdefault("usage_passes", {})
        totals = passes.setdefault(turn.id, {})
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
        usage = dict(totals)
        declined = live.extra.pop("declined_call", None)
        stop = ended.get("stop")
        if declined or stop in ("refusal", "max_tokens", "max_turn_requests"):
            status = (
                TurnStatus.DECLINED
                if declined
                else TurnStatus.REFUSED
                if stop == "refusal"
                else TurnStatus.TRUNCATED
            )
            reason = (
                f"Stopped by your decision: rejected {declined}."
                if declined
                else "The model declined to continue."
                if stop == "refusal"
                else f"The model stopped at {stop}."
            )
            self._finish(live, turn.finish(status, stop or "end_turn", usage, error=reason))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            await self._emit(
                Event(sid, "turn." + status.value, {"reason": reason, "usage": usage}, turn_id=turn.id)
            )
            await self._interrupt_pending(live, reason)
            return

        if self.work:
            waiting = await self.work.pending(sid, turn.id)
            if any(waiting.values()):
                live.state.update(
                    updated(
                        turn,
                        status=TurnStatus.PAUSED,
                        input_tokens=int(usage.get("inputTokens", 0)),
                        output_tokens=int(usage.get("outputTokens", 0)),
                        cached_tokens=int(usage.get("cachedReadTokens", 0)),
                    )
                )
                live.state.session = live.state.session.transition(SessionStatus.READY)
                await self._emit(Event(sid, "turn.paused", {"waiting": waiting}, turn_id=turn.id))
                self._start_next(live)
                return
            try:
                self.work.sessions.check(sid)
            except Exception as exc:
                self._finish(live, turn.finish(TurnStatus.BLOCKED, error=str(exc)))
                live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
                await self._emit(Event(sid, "budget.reached", {"reason": str(exc)}, turn_id=turn.id))
                await self._emit(turn_blocked(sid, turn.id, str(exc), [], []))
                return

        requirements = extract_requirements(turn.prompt)
        invocation_rows = None
        invocation_calls = []
        observation_missing = []
        observed_effects = False
        if self.work and getattr(self.work, "evidence_enabled", False):
            from ..domain.invocation_evidence import grade

            invocation_calls = await self.work.evidence_calls(sid, turn.id)
            invocation_rows = tuple(grade(answer, invocation_calls))
            related = turn.request_key.split(":", 1) if ":" in turn.request_key else []
            observation = await self.work.observation_proof(
                sid,
                turn.id,
                related[1] if related and related[0] == "change" else "",
                related[1] if related and related[0] == "operation" else "",
            )
            observation_missing = observation["missing"]
            observed_effects = bool(observation["effects"] and not observation_missing)
        decision = supervisor.decide(
            supervisor.State(
                requirements=requirements,
                query_target=attached_query(turn.attachments),
                evidence_rows=invocation_rows,
                proof_floor=invocation_rows is not None and not says_no_tools(turn.prompt),
                observed_effects=observed_effects,
                read_only=is_read_only(requirements, bool(turn.context)) or says_no_tools(turn.prompt)
                    or bool(attached_query(turn.attachments) and query_explanation_only(turn.prompt)),
                calls=live.tool_calls(),
                answer=answer,
                continuations=continuations,
                audits=audits,
            )
        )

        if observation_missing and decision.verdict is supervisor.Verdict.DONE:
            decision = supervisor.Decision(
                supervisor.Verdict.AUDIT if audits < supervisor.MAX_AUDITS else supervisor.Verdict.BLOCKED,
                "Observe the changed asset or native operation before claiming completion. "
                + "; ".join(observation_missing),
                tuple(observation_missing),
                decision.evidence,
            )
        if invocation_rows is not None and decision.verdict in (
            supervisor.Verdict.CONTINUE,
            supervisor.Verdict.AUDIT,
        ):
            from ..domain.invocation_evidence import audit_context

            decision = dataclasses.replace(
                decision, message=decision.message + audit_context(invocation_calls)
            )
        if self.work and decision.verdict in (supervisor.Verdict.CONTINUE, supervisor.Verdict.AUDIT):
            try:
                self.work.sessions.check_pass(
                    sid, decision.message, live.resolved.output if live.resolved else 4000
                )
            except Exception as exc:
                decision = supervisor.Decision(
                    supervisor.Verdict.BLOCKED, str(exc), decision.missing, decision.evidence
                )
                await self._emit(Event(sid, "budget.reached", {"reason": str(exc)}, turn_id=turn.id))
        if decision.verdict is supervisor.Verdict.CONTINUE:
            await self._nudge(live, turn, decision.message, answer, continuations + 1, audits)
            return
        if decision.verdict is supervisor.Verdict.AUDIT:
            live.state.update(updated(turn, status=TurnStatus.AUDITING))
            await self._emit(turn_auditing(sid, turn.id, audits + 1, list(decision.missing)))
            await self._nudge(live, turn, decision.message, answer, continuations, audits + 1)
            return
        if decision.evidence:  # recorded once, with the outcome, never per audit pass
            if invocation_rows is not None:
                await self._emit(
                    Event(
                        sid,
                        "evidence.proposed",
                        {
                            "rows": list(invocation_rows),
                            "sources": [
                                {
                                    "callId": r["id"],
                                    "name": r["tool"],
                                    "status": r["state"],
                                    "summary": r.get("resultSummary", ""),
                                }
                                for r in invocation_calls
                            ],
                        },
                        turn_id=turn.id,
                    )
                )
            else:
                await self._emit(evidence_proposed(sid, turn.id, list(decision.evidence)))
        if decision.verdict is supervisor.Verdict.DONE:
            self._finish(live, turn.finish(TurnStatus.COMPLETED, ended.get("stop", "end_turn"), usage))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            # committed above, so _start_next sees no running turn
            await self._emit(turn_completed(sid, turn.id, ended.get("stop", "end_turn"), usage, seconds))
            self._start_next(live)
            return
        self._finish(live, turn.finish(TurnStatus.BLOCKED, error=decision.message))
        attempted = [
            {"tool": c["name"], "status": c.get("status", ""), "summary": c.get("summary", "")}
            for c in live.state.calls.values()
        ][:8]
        live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
        await self._emit(turn_blocked(sid, turn.id, decision.message, list(decision.missing), attempted))
        await self._interrupt_pending(
            live, "Queued work was not started because the preceding turn needs attention."
        )

    def _finish(self, live: Live, turn: Turn) -> None:
        live.state.update(turn)

    def _start_next(self, live: Live) -> None:
        """Run the next queued turn, if any.

        Called from inside the running turn's own task, so "is something running?" cannot be
        answered by `live.task` (that is this very task). The question that matters is whether any
        OTHER turn is already running.
        """
        if (
            self._shutting_down
            or live.cancel
            or live.state.session.requires_resume
            or live.state.session.status is SessionStatus.ARCHIVED
        ):
            return
        nxt = next((t for t in live.state.turns if t.status is TurnStatus.QUEUED), None)
        if nxt is None:
            return
        # Every caller has already committed this turn's terminal status, so any RUNNING/AUDITING
        # turn here belongs to a different turn that is genuinely in flight.
        if any(t.status in (TurnStatus.RUNNING, TurnStatus.AUDITING) for t in live.state.turns):
            return
        # Schedule on the loop after this turn's own settle returns, so states are consistent.
        live.task = asyncio.get_running_loop().create_task(self._run_turn(live, nxt.id))

    async def _nudge(
        self, live: Live, turn: Turn, prompt: str, previous: str, continuations: int, audits: int
    ) -> None:
        assert live.handle
        started = time.time()
        try:
            if self.work:
                self.work.sessions.check(live.state.session.id)
            if previous:
                await self._emit(
                    Event(live.state.session.id, "message.delta", {"text": "\n\n"}, turn_id=turn.id)
                )
            await self._rt.prompt_in_background(live.handle, prompt)
            ended, usage, text = await self._drain(live)
        except Exception as exc:  # noqa: BLE001
            ended, usage, text = {"error": str(exc)[:400]}, {}, ""
        await self._settle(
            live,
            turn,
            (previous + "\n" + text).strip(),
            ended,
            usage,
            time.time() - started,
            continuations,
            audits,
        )

    async def approve(
        self, session_id: str, approval_id: str, outcome: str, option_id: str | None, user_id: str
    ) -> None:
        live = self.get(session_id)
        async with live.lock:
            pending = live.extra.get("approvals", {})
            request = pending.get(approval_id)
            if request is None or live.handle is None:
                raise DomainError("this approval expired or was already decided")
            if outcome != "deny" and request.get("argumentsKnown") is False:
                raise DomainError("The tool arguments are unknown; only rejection is available.")
            # Match the selected option to the kind offered by the agent, server-side.
            offered = request.get("options", [])
            expected = {"allow_once": "allow_once", "allow_session": "allow_always"}.get(outcome)
            selected = (
                next(
                    (o for o in offered if o.get("optionId") == option_id and o.get("kind") == expected),
                    None,
                )
                if expected
                else None
            )
            if outcome != "deny" and selected is None:
                raise DomainError("the selected permission option was not offered")
            if outcome == "deny":
                selected = next(
                    (o for o in offered if o.get("kind") == "reject_once"),
                    next((o for o in offered if o.get("kind") == "reject_always"), None),
                )
                live.extra["declined_call"] = request.get("target") or request.get("action")
                call_id = request.get("callId")
                if call_id:
                    live.extra.setdefault("declined_calls", set()).add(call_id)
                    await self._emit(
                        tool_updated(
                            session_id,
                            live.state.running().id if live.state.running() else None,
                            call_id,
                            status="declined",
                            summary="Not executed: rejected by your decision.",
                        )
                    )
            del pending[approval_id]
            turn = live.state.running()
            await self._emit(
                approval_decided(session_id, turn.id if turn else None, approval_id, outcome, user_id)
            )
            await self._rt.respond_permission(
                live.handle, approval_id, selected["optionId"] if selected else None
            )

    async def answer_question(self, sid, qid, action, content):
        live = self.get(sid)
        question = live.extra.get("questions", {}).get(qid)
        if not live.handle or not question or question["state"] != "pending":
            raise ValueError("This question is no longer pending")
        await self._rt.respond_question(live.handle, qid, action, content)
        question["state"] = "answered" if action == "accept" else action
        await self._emit(Event(sid, "question.decided", {"id": qid, "state": question["state"]}))
        return {"id": qid, "state": question["state"]}
