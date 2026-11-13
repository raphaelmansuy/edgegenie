"""Session autonomy, capability state and budgets. No adapter imports or private runtime access."""

import asyncio
import math
import time
from uuid import uuid4
from functools import wraps


def serialized(method):
    @wraps(method)
    async def call(self, sid, *args, **kwargs):
        async with self._locks.setdefault(sid, asyncio.Lock()):
            return await method(self, sid, *args, **kwargs)

    return call


from ..domain.asset import WorkError, digest
from ..domain.policy.verdict import Mode


class WorkSessions:
    def __init__(
        self,
        store,
        events,
        capabilities,
        actor,
        *,
        token_ceiling=1000000,
        money_ceiling=10,
        max_pass_cost=0,
    ):
        self.store, self.events, self.capabilities, self.actor = store, events, capabilities, actor
        self.token_ceiling, self.money_ceiling = token_ceiling, money_ceiling
        self._settings = {}
        self._locks = {}
        self.max_pass_cost = max_pass_cost

    async def prepare(self, sid):
        who = self.actor(sid, "")
        try:
            row = await self.store.get("session", sid)
        except WorkError:
            try:
                pref = await self.store.get("preference", digest(who.user_id))
            except WorkError:
                pref = {}
            row = await self.store.put(
                "session",
                {
                    "id": sid,
                    "sessionId": sid,
                    "owner": who.user_id,
                    "mode": pref.get("mode", "review"),
                    "state": "open",
                    "maxPassCost": self.max_pass_cost,
                    "budget": None,
                    "usedTokens": 0,
                    "usedCost": 0,
                    "currency": "",
                    "createdAt": time.time(),
                    "updatedAt": time.time(),
                },
            )
        self._settings[sid] = row
        if not self.capabilities.rows(sid):
            await self.capabilities.probe(sid)
        return row

    def mode(self, sid):
        return self._settings.get(sid, {}).get("mode", "review")

    def settings(self, sid):
        return self._settings.get(sid, {})

    def forget(self, sid):
        self._settings.pop(sid, None)
        self._locks.pop(sid, None)

    @serialized
    async def set_mode(self, sid, mode, user):
        Mode(mode)
        row = await self.prepare(sid)
        pid = digest(user)
        try:
            old = await self.store.get("preference", pid)
        except WorkError:
            old = None
        saved = await self.events.commit(
            [
                ("session", {**row, "mode": mode, "updatedAt": time.time()}, row["version"]),
                (
                    "preference",
                    {
                        "id": pid,
                        "sessionId": "",
                        "owner": user,
                        "mode": mode,
                        "createdAt": old["createdAt"] if old else time.time(),
                    },
                    old["version"] if old else None,
                ),
            ],
            sid,
            None,
            "mode.changed",
            {"mode": mode},
            user,
        )
        self._settings[sid] = saved[0]
        return {"mode": mode}

    @serialized
    async def budget(self, sid, limit, unit):
        row = await self.prepare(sid)
        if (
            unit not in ("tokens", "money")
            or not isinstance(limit, (int, float))
            or isinstance(limit, bool)
            or not math.isfinite(limit)
            or limit <= 0
        ):
            raise WorkError("Enter a positive token or money budget.", 422)
        if limit > (self.token_ceiling if unit == "tokens" else self.money_ceiling):
            raise WorkError("Budget exceeds the owner ceiling.", 422)
        if unit == "tokens" and row.get("usageUncertain"):
            raise WorkError(
                "Prior token usage is unknown. Set the budget on a new session before its first turn.", 422
            )
        if unit == "money" and row.get("costUncertain"):
            raise WorkError("The reported cost unit changed. Use a token budget.", 422)
        if unit == "money" and not row.get("maxPassCost"):
            raise WorkError("No verified maximum pass cost is configured. Use a token budget.", 422)
        if unit == "money" and not row.get("currency"):
            raise WorkError("Cost is unknown. Use a token budget until the agent reports money.", 422)
        budget = {"limit": limit, "unit": unit}
        saved = await self.events.commit(
            [("session", {**row, "budget": budget, "updatedAt": time.time()}, row["version"])],
            sid,
            None,
            "budget.updated",
            {"budget": budget, "usedTokens": row["usedTokens"], "usedCost": row["usedCost"]},
            row["owner"],
        )
        self._settings[sid] = saved[0]
        return budget

    def check(self, sid, reserve=0):
        row = self.settings(sid)
        budget = row.get("budget")
        if not budget:
            return
        if (
            row.get("usageUncertain")
            and budget["unit"] == "tokens"
            or row.get("costUncertain")
            and budget["unit"] == "money"
        ):
            raise WorkError(
                "Budget usage is unknown. Work stopped before another pass; review the usage source.", 429
            )
        used = row.get("usedTokens", 0) + reserve if budget["unit"] == "tokens" else row.get("usedCost", 0)
        if used > budget["limit"] if reserve else used >= budget["limit"]:
            raise WorkError("Budget reached. Raise the budget before continuing.", 429)

    def check_pass(self, sid, prompt, output):
        row = self.settings(sid)
        budget = row.get("budget")
        if not budget:
            return
        self.check(sid)
        if budget["unit"] == "tokens":
            self.check(sid, int(row.get("contextUsed", 0)) + len(prompt.encode()) + 2048 + output)
        elif not row.get("maxPassCost") or row.get("usedCost", 0) + row["maxPassCost"] > budget["limit"]:
            raise WorkError("Budget reached: the remaining money budget cannot cover another pass.", 429)

    @serialized
    async def record_pass(self, sid, tid, usage, pass_no):
        row = await self.prepare(sid)
        values = [usage.get(k) for k in ("inputTokens", "outputTokens")]
        known = all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
            for v in values
        )
        tokens = sum(int(v) for v in values) if known else 0
        record = {
            "id": f"{tid}:{pass_no}",
            "sessionId": sid,
            "owner": row["owner"],
            "turnId": tid,
            "pass": pass_no,
            "usage": usage,
            "createdAt": time.time(),
        }
        saved = await self.store.batch(
            [
                ("usage_pass", record, None),
                (
                    "session",
                    {
                        **row,
                        "usedTokens": row["usedTokens"] + tokens,
                        "usageUncertain": row.get("usageUncertain", False) or not known,
                        "updatedAt": time.time(),
                    },
                    row["version"],
                ),
            ]
        )
        self._settings[sid] = saved[1]

    @serialized
    async def meter(self, sid, usage, epoch=""):
        row = await self.prepare(sid)
        cost = usage.get("cost") or {}
        next_row = {**row, "contextUsed": usage.get("used", 0), "contextSize": usage.get("size", 0)}
        amount = cost.get("amount")
        if (
            isinstance(amount, (int, float))
            and not isinstance(amount, bool)
            and math.isfinite(amount)
            and amount >= 0
        ):
            currency = str(cost.get("currency", ""))[:32]
            if row.get("currency") and currency != row["currency"]:
                next_row.update(costUncertain=True, currency="")
            elif not row.get("costUncertain"):
                previous = row.get("epochCost", 0) if row.get("costEpoch") == epoch else 0
                next_row.update(
                    usedCost=row.get("usedCost", 0) + max(0, amount - previous),
                    epochCost=amount,
                    costEpoch=epoch,
                    currency=currency,
                )
        if next_row.get("costUncertain"):
            next_row["currency"] = ""
        row = await self.store.put("session", next_row, row["version"])
        self._settings[sid] = row
        return {
            "used": usage.get("used", 0),
            "size": usage.get("size", 0),
            **(
                {"cost": {"amount": row["usedCost"], "currency": row["currency"]}}
                if row.get("currency")
                else {}
            ),
        }
