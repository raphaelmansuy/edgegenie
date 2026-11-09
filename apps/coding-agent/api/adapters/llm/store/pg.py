"""The Postgres (Lakebase) registry: plain SQL over `psycopg`, forward-only migrations at boot.

Two deliberate choices (08 §2, unresolved objection #1):

* **plain SQL, no ORM** — the queries are two joins and a lateral; an ORM would add a dependency and a
  second migration system for six tables.
* **no second runner** — `migrate.apply()` is the only migration path in this app, and spec 004 must
  adopt it rather than add another (11 R-10).

The store never returns a plaintext secret: `llm_credential` rows travel as `Sealed` values and only
the vault can open them.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from ....domain.llm import (
    Capability,
    CredentialKind,
    Grant,
    LimitEvidence,
    Limits,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    WireProtocol,
)
from ....ports import CredentialRef
from ..vault.envelope import Sealed
from . import migrate

log = logging.getLogger("app.llm.pg")


class PgRegistryStore:
    """A registry in Postgres. `source` is `database`; a connection loss degrades to memory (E-15)."""

    source = "database"

    def __init__(self, conn, *, seed_path: Path | str | None = None) -> None:
        self._conn = conn
        self._seed_path = seed_path
        self.default_model = ""
        #: Set when a query fails: the catalogue keeps serving from this instead of emptying.
        self._degraded: Any = None

    # -- lifecycle ------------------------------------------------------------
    @classmethod
    async def connect(cls, dsn: str, *, seed_path: Path | str | None = None,
                      connection_class=None, max_lifetime: float = 3600.0) -> PgRegistryStore:
        """Connect, then apply migrations. Raises when unreachable, and the caller degrades.

        `connection_class` lets Lakebase supply a fresh OAuth token per connection (see `lakebase`).
        """
        from psycopg_pool import AsyncConnectionPool

        extra = {"connection_class": connection_class} if connection_class else {}
        pool = AsyncConnectionPool(dsn, min_size=1, max_size=4, open=False,
                                   max_lifetime=max_lifetime, **extra)
        await pool.open(wait=True, timeout=10)
        store = cls(pool, seed_path=seed_path)
        await store._migrate()
        await store._seed_if_empty()
        return store

    async def _migrate(self) -> None:
        async with self._conn.connection() as conn:
            version = await migrate.apply(conn)
            log.info("llm schema at version %s", version)

    async def _seed_if_empty(self) -> None:
        """First boot: write the seed rows so an operator has something to edit.

        Seeding is additive and idempotent (`ON CONFLICT DO NOTHING`), so a second boot changes
        nothing — and a row an operator has edited is never overwritten.
        """
        from .seed import load

        seed = load(self._seed_path)
        self.default_model = seed.default_model
        chosen = await self.get_setting("default_model")
        if chosen:
            self.default_model = chosen
        async with self._conn.connection() as conn, conn.cursor() as cur:
            for provider in seed.providers:
                await cur.execute(
                    """INSERT INTO llm.llm_provider
                       (id, display_name, kind, wire_default, base_url, npm_package)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                    (provider.id, provider.display_name, provider.kind.value,
                     provider.wire.value, provider.base_url or None, provider.npm))
            for spec in seed.models:
                await cur.execute(
                    """INSERT INTO llm.llm_model
                       (id, provider_id, endpoint, display_name, group_name, capability, wire,
                        context_window, max_output, limit_evidence, limit_source, credential_kind,
                        state, sees_images)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         -- CAPABILITY is corrected, the rest is not. A model's ability to accept an image
                         -- is a fact about the model, not an operator preference: when the seed learns it
                         -- (by measurement), a row that was seeded before must learn it too. Every other
                         -- column keeps `DO NOTHING` semantics so an operator's edit is never overwritten.
                         -- Measured: gemma-3-12b was seeded with sees_images=false, the migration's UPDATE
                         -- ran BEFORE the row existed, and the deployed catalogue kept serving it as blind
                         -- while the model read three random codes correctly.
                         sees_images = llm.llm_model.sees_images OR EXCLUDED.sees_images""",
                    (spec.id.value, spec.id.provider.value, spec.endpoint, spec.display_name,
                     spec.group, spec.capability.value, spec.wire.value, spec.limits.context,
                     spec.limits.output, spec.limits.evidence.value, spec.limits.source,
                     spec.credential_kind.value, spec.state.value, spec.sees_images))

    async def close(self) -> None:
        await self._conn.close()

    # -- reads ----------------------------------------------------------------
    async def providers(self) -> list[dict]:
        rows = await self._fetch(
            "SELECT id, display_name, kind, wire_default, base_url, npm_package, enabled "
            "FROM llm.llm_provider ORDER BY id", ())
        return [{"id": r[0], "display_name": r[1], "kind": r[2], "wire": r[3], "base_url": r[4] or "",
                 "npm": r[5], "enabled": r[6]} for r in rows]

    async def models(self, user_id: str = "") -> list[ModelSpec]:
        """The picker's one query. Two lateral joins, no N+1, no secret (05 §Tables)."""
        return await self._models(enabled_only=True)

    async def all_models(self) -> list[ModelSpec]:
        """Every model, switched off or not: the administrator's view, never the picker's."""
        return await self._models(enabled_only=False)

    async def _models(self, *, enabled_only: bool) -> list[ModelSpec]:
        where = "WHERE p.enabled AND m.enabled" if enabled_only else ""
        rows = await self._fetch(
            """SELECT m.id, m.endpoint, m.display_name, m.group_name, m.capability, m.wire,
                      m.context_window, m.max_output, m.limit_evidence, m.limit_source,
                      m.credential_kind, m.state, m.enabled, m.selectable,
                      p.display_name, p.kind,
                      h.state, h.detail, extract(epoch FROM h.at), m.sees_images
               FROM llm.llm_model m
               JOIN llm.llm_provider p ON p.id = m.provider_id
               LEFT JOIN LATERAL (
                   SELECT state, detail, at FROM llm.llm_health
                   WHERE model_id = m.id ORDER BY at DESC LIMIT 1) h ON TRUE
               """ + where + """
               ORDER BY m.group_name, m.display_name""", ())
        return [_spec_from_row(r) for r in rows]

    async def find(self, model_id: str) -> ModelSpec | None:
        rows = await self._fetch(
            """SELECT m.id, m.endpoint, m.display_name, m.group_name, m.capability, m.wire,
                      m.context_window, m.max_output, m.limit_evidence, m.limit_source,
                      m.credential_kind, m.state, m.enabled, m.selectable,
                      p.display_name, p.kind, h.state, h.detail, extract(epoch FROM h.at),
                      m.sees_images
               FROM llm.llm_model m
               JOIN llm.llm_provider p ON p.id = m.provider_id
               LEFT JOIN LATERAL (
                   SELECT state, detail, at FROM llm.llm_health
                   WHERE model_id = m.id ORDER BY at DESC LIMIT 1) h ON TRUE
               WHERE m.id = %s""", (model_id,))
        return _spec_from_row(rows[0]) if rows else None

    async def grants(self, model_id: str) -> Grant | None:
        rows = await self._fetch(
            "SELECT subject_kind, subject, allow FROM llm.llm_model_grant WHERE model_id = %s",
            (model_id,))
        return Grant(model_id, tuple((r[0], r[1], bool(r[2])) for r in rows)) if rows else None

    async def health_state(self, model_id: str) -> tuple[str, str, float] | None:
        rows = await self._fetch(
            "SELECT state, detail, extract(epoch FROM at) FROM llm.llm_health "
            "WHERE model_id = %s ORDER BY at DESC LIMIT 1", (model_id,))
        return (rows[0][0], rows[0][1] or "", float(rows[0][2] or 0)) if rows else None

    async def turn_models(self, session_id: str) -> list[dict]:
        rows = await self._fetch(
            "SELECT turn_id, session_id, model_id, provider_id, wire, endpoint, credential_ref, "
            "context_window, max_output, extract(epoch FROM at) FROM llm.llm_turn_model "
            "WHERE session_id = %s ORDER BY at", (session_id,))
        return [_pin_from_row(r) for r in rows]

    async def discovery_runs(self, limit: int = 20) -> list[dict]:
        rows = await self._fetch(
            "SELECT provider_id, outcome, models_seen, detail, extract(epoch FROM at) "
            "FROM llm.llm_discovery_run ORDER BY at DESC LIMIT %s", (limit,))
        return [{"provider": r[0], "outcome": r[1], "modelsSeen": r[2], "detail": r[3], "at": r[4]}
                for r in rows]

    # -- writes ---------------------------------------------------------------
    async def upsert_provider(self, provider: dict) -> None:
        await self._run(
            """INSERT INTO llm.llm_provider (id, display_name, kind, wire_default, base_url, npm_package)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name,
                                              base_url = EXCLUDED.base_url,
                                              updated_at = now()""",
            (provider["id"], provider["display_name"], provider["kind"], provider["wire"],
             provider.get("base_url") or None, provider.get("npm", "")))

    async def upsert_model(self, spec: ModelSpec) -> None:
        """Upsert by canonical id. A second claim on the same id with a different endpoint is refused
        with both rows quoted, which is E-2's acceptance."""
        rows = await self._fetch("SELECT endpoint FROM llm.llm_model WHERE id = %s", (spec.id.value,))
        if rows and rows[0][0] != spec.endpoint:
            raise ValueError(
                f"{spec.id.value} is already registered against endpoint {rows[0][0]!r}; "
                f"refusing to replace it with {spec.endpoint!r}")
        await self._run(
            """INSERT INTO llm.llm_model
               (id, provider_id, endpoint, display_name, group_name, capability, wire, context_window,
                max_output, limit_evidence, limit_source, credential_kind, state, enabled, selectable,
                sees_images)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 display_name = EXCLUDED.display_name, group_name = EXCLUDED.group_name,
                 capability = EXCLUDED.capability, context_window = EXCLUDED.context_window,
                 max_output = EXCLUDED.max_output, limit_evidence = EXCLUDED.limit_evidence,
                 limit_source = EXCLUDED.limit_source, state = EXCLUDED.state,
                 selectable = EXCLUDED.selectable, sees_images = EXCLUDED.sees_images,
                 updated_at = now()""",
            (spec.id.value, spec.id.provider.value, spec.endpoint, spec.display_name, spec.group,
             spec.capability.value, spec.wire.value, spec.limits.context, spec.limits.output,
             spec.limits.evidence.value, spec.limits.source, spec.credential_kind.value,
             spec.state.value, spec.enabled, spec.selectable, spec.sees_images))

    async def get_setting(self, key: str) -> str:
        rows = await self._fetch("SELECT value FROM llm.llm_setting WHERE key = %s", (key,))
        return rows[0][0] if rows else ""

    async def set_setting(self, key: str, value: str, by: str = "") -> None:
        await self._run(
            """INSERT INTO llm.llm_setting (key, value, updated_by) VALUES (%s,%s,%s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                               updated_by = EXCLUDED.updated_by, updated_at = now()""",
            (key, value, by))

    async def set_default_model(self, model_id: str, by: str = "") -> None:
        await self.set_setting("default_model", model_id, by)
        self.default_model = model_id

    async def set_model_enabled(self, model_id: str, enabled: bool) -> bool:
        rows = await self._fetch(
            "UPDATE llm.llm_model SET enabled = %s, updated_at = now() WHERE id = %s RETURNING id",
            (enabled, model_id))
        return bool(rows)

    async def delete_model(self, model_id: str) -> bool:
        rows = await self._fetch("DELETE FROM llm.llm_model WHERE id = %s RETURNING id", (model_id,))
        return bool(rows)

    async def update_provider(self, provider_id: str, *, enabled: bool | None = None,
                              base_url: str | None = None) -> bool:
        rows = await self._fetch(
            """UPDATE llm.llm_provider SET enabled = coalesce(%s, enabled),
                                           base_url = CASE WHEN %s::boolean THEN nullif(%s, '') ELSE base_url END,
                                           updated_at = now()
               WHERE id = %s RETURNING id""",
            (enabled, base_url is not None, base_url or "", provider_id))
        return bool(rows)

    async def record_health(self, model_id: str, state: str, detail: str, *, source: str = "probe") -> None:
        await self._run(
            "INSERT INTO llm.llm_health (model_id, state, detail, source) VALUES (%s,%s,%s,%s)",
            (model_id, state, detail[:400], source))

    async def record_turn_model(self, pin: dict) -> None:
        """Insert-once: `ON CONFLICT DO NOTHING` is what makes Axiom A5 structural (C-8)."""
        await self._run(
            """INSERT INTO llm.llm_turn_model
               (turn_id, session_id, model_id, provider_id, wire, endpoint, credential_ref,
                limit_evidence, context_window, max_output)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (turn_id) DO NOTHING""",
            (pin["turnId"], pin.get("sessionId", ""), pin["modelId"], pin["providerId"],
             pin["wire"], pin["endpoint"], pin.get("credentialRef", ""),
             pin.get("limitEvidence", "default"), int(pin.get("context") or 0),
             int(pin.get("output") or 0)))

    async def record_discovery(self, provider: str, outcome: str, seen: int, detail: str = "") -> None:
        await self._run(
            "INSERT INTO llm.llm_discovery_run (provider_id, outcome, models_seen, detail) "
            "VALUES (%s,%s,%s,%s)", (provider, outcome, seen, detail[:400]))

    async def note_limits(self, model_id: str, output: int, source: str) -> None:
        """Lower a cap only. The `WHERE` clause is the rule, so an accidental raise is a no-op."""
        await self._run(
            "UPDATE llm.llm_model SET max_output = %s, limit_evidence = 'measured', "
            "limit_source = %s, updated_at = now() WHERE id = %s AND max_output > %s",
            (output, source, model_id, output))

    # -- credentials ----------------------------------------------------------
    async def insert_credential(self, *, provider: ProviderKind, kind: str, scope_kind: str,
                                scope_id: str, sealed: Sealed, last4: str, fingerprint: str,
                                project_hint: str) -> str:
        rows = await self._fetch(
            """INSERT INTO llm.llm_credential
               (provider_id, scope_kind, scope_id, kind, ciphertext, iv, auth_tag, wrapped_dek,
                dek_iv, kek_key_id, last4, fingerprint, project_hint)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id::text""",
            (provider.value, scope_kind, scope_id, kind, sealed.ciphertext, sealed.iv,
             sealed.auth_tag, sealed.wrapped_dek, b"", sealed.kek_key_id, last4, fingerprint,
             project_hint))
        return rows[0][0] if rows else ""

    async def open_credential(self, ref: str, *, user_id: str) -> tuple[Sealed, dict] | None:
        """The row, with its scope checked in SQL: a user-scoped key is only visible to its owner."""
        rows = await self._fetch(
            """SELECT ciphertext, iv, auth_tag, wrapped_dek, kek_key_id, kind, last4, project_hint,
                      scope_kind, scope_id
               FROM llm.llm_credential
               WHERE id = %s::uuid AND revoked_at IS NULL
                 AND (scope_kind = 'workspace' OR scope_id = %s)""", (ref, user_id))
        if not rows:
            return None
        r = rows[0]
        return (Sealed(r[0], r[1], r[2], r[3], r[4]),
                {"kind": r[5], "last4": r[6], "project_hint": r[7], "scope_kind": r[8],
                 "scope_id": r[9]})

    async def revoke_credential(self, ref: str, *, user_id: str) -> None:
        await self._run(
            "UPDATE llm.llm_credential SET revoked_at = now() "
            "WHERE id = %s::uuid AND (scope_kind = 'workspace' OR scope_id = %s)", (ref, user_id))

    async def live_credential(self, provider: ProviderKind, *, user_id: str) -> dict | None:
        """The most specific live key: this user's, else a workspace key. Never another user's."""
        rows = await self._fetch(
            """SELECT id::text, kind, last4, project_hint, scope_kind
               FROM llm.llm_credential
               WHERE provider_id = %s AND revoked_at IS NULL
                 AND (scope_kind = 'workspace' OR scope_id = %s)
               ORDER BY (scope_kind = 'user') DESC, created_at DESC LIMIT 1""",
            (provider.value, user_id))
        if not rows:
            return None
        return {"id": rows[0][0], "kind": rows[0][1], "last4": rows[0][2],
                "project_hint": rows[0][3], "scope_kind": rows[0][4]}

    async def list_credentials(self, *, user_id: str) -> list[dict]:
        rows = await self._fetch(
            """SELECT id::text, provider_id, kind, last4, project_hint, scope_kind,
                      extract(epoch FROM created_at), extract(epoch FROM last_used_at)
               FROM llm.llm_credential
               WHERE revoked_at IS NULL AND (scope_kind = 'workspace' OR scope_id = %s)
               ORDER BY provider_id, created_at DESC""", (user_id,))
        return [{"id": r[0], "provider": r[1], "kind": r[2], "last4": r[3], "projectHint": r[4],
                 "scope": r[5], "createdAt": r[6], "lastUsedAt": r[7]} for r in rows]

    # -- plumbing -------------------------------------------------------------
    async def _fetch(self, sql: str, params: tuple) -> list[tuple]:
        try:
            async with self._conn.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql, params)
                return await cur.fetchall() or []
        except Exception as exc:  # noqa: BLE001 - a dead connection degrades, it does not crash
            self._note_failure(exc)
            raise

    async def _run(self, sql: str, params: tuple) -> None:
        try:
            async with self._conn.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql, params)
        except Exception as exc:  # noqa: BLE001
            self._note_failure(exc)
            raise

    def _note_failure(self, exc: Exception) -> None:
        log.warning("llm registry query failed: %s", type(exc).__name__)


def _spec_from_row(r: tuple) -> ModelSpec:
    """One row of the picker query, as a `ModelSpec`. The column order is fixed by the two SELECTs."""
    limits = Limits(int(r[6]), int(r[7]), LimitEvidence(r[8]), r[9] or "assumed")
    return ModelSpec(
        id=ModelId(ProviderKind(r[15]), r[0].split("/", 1)[1]),
        display_name=r[2],
        provider_name=r[14],
        wire=WireProtocol(r[5]),
        endpoint=r[1],
        limits=limits,
        capability=Capability(r[4]),
        credential_kind=CredentialKind(r[10]),
        state=ModelState(r[11]),
        detail=(r[17] or "")[:400],
        checked_at=float(r[18] or 0),
        group=r[3] or "",
        enabled=bool(r[12]),
        # The declared vision capability, appended last so no existing index moves. A row written before
        # migration 003 has no value; `False` is the safe reading (an image is labelled, not sent blind).
        sees_images=bool(r[19]) if len(r) > 19 else False,
        origin="database",
    )


def _pin_from_row(r: tuple) -> dict:
    return {"turnId": r[0], "sessionId": r[1], "modelId": r[2], "providerId": r[3], "wire": r[4],
            "endpoint": r[5], "credentialRef": r[6], "context": r[7], "output": r[8], "at": r[9]}


def _selectable(state: str, capability: str) -> bool:
    return state not in ("not_enabled", "not_served") and capability != "chat_only"


def credential_ref(row: dict, provider: ProviderKind) -> CredentialRef:
    return CredentialRef(id=row["id"], provider=provider, kind=row["kind"],
                         scope_kind=row.get("scope_kind", "user"),
                         last4=row.get("last4", ""), project_hint=row.get("project_hint", ""))


def with_state(spec: ModelSpec, state: ModelState, detail: str, at: float) -> ModelSpec:
    return replace(spec, state=state, detail=detail, checked_at=at)
