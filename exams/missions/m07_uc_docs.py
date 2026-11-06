"""M7 - Document Unity Catalog tables from the data (C9: governance & documentation)."""
from __future__ import annotations

import re

from lib import CATALOG, Check, Ctx, Mission, api, sql, sql_val

SEED = [
    """CREATE OR REPLACE TABLE {s}.cust AS SELECT id AS cid, concat('Customer ', id) AS cname,
       element_at(array('FR','DE','US','JP','BR'), CAST(pmod(hash(id,'c'),5) AS INT)+1) AS ctry,
       CAST(pmod(hash(id,'l'),900000) AS BIGINT) AS ltv_c,
       timestampadd(DAY, -CAST(pmod(hash(id,'t'),900) AS INT), TIMESTAMP'2026-10-01 00:00:00') AS ts_cr,
       pmod(hash(id,'f'),10) < 7 AS flg_act,
       element_at(array('SMB','ENT','CONS'), CAST(pmod(hash(id,'s'),3) AS INT)+1) AS seg
       FROM range(1, 301)""",
    """CREATE OR REPLACE TABLE {s}.ord AS SELECT id AS oid, CAST(pmod(hash(id,'c'),300) AS BIGINT)+1 AS cid,
       CAST(1000 + pmod(hash(id,'a'),49000) AS BIGINT) AS amt_c,
       element_at(array('EUR','USD','JPY'), CAST(pmod(hash(id,'y'),3) AS INT)+1) AS ccy,
       element_at(array('N','S','C','R'), CAST(pmod(hash(id,'st'),4) AS INT)+1) AS st,
       timestampadd(HOUR, -CAST(pmod(hash(id,'h'),2000) AS INT), TIMESTAMP'2026-10-01 00:00:00') AS ts
       FROM range(1, 801)""",
    """CREATE OR REPLACE TABLE {s}.evt_log AS SELECT id AS eid, CAST(pmod(hash(id,'c'),300) AS BIGINT)+1 AS cid,
       element_at(array('login','view','add_to_cart','checkout'), CAST(pmod(hash(id,'e'),4) AS INT)+1) AS ev,
       CAST(1760000000000 + pmod(hash(id,'m'), 3000000000) AS BIGINT) AS ts_ms,
       concat('{{"sid":"s', id % 50, '","ua":"web"}}') AS payload
       FROM range(1, 1501)""",
]
TABLES = {"cust": ["cid", "cname", "ctry", "ltv_c", "ts_cr", "flg_act", "seg"],
          "ord": ["oid", "cid", "amt_c", "ccy", "st", "ts"],
          "evt_log": ["eid", "cid", "ev", "ts_ms", "payload"]}


def prompt(ctx: Ctx) -> str:
    return f"""The schema {ctx.schema} has three tables (cust, ord, evt_log) with cryptic column names and no documentation. Make them self-explanatory for analysts by adding Unity Catalog comments:
- a table comment on each of the 3 tables (at least 40 characters, say what one row represents),
- a column comment on EVERY column of every table (all {sum(len(v) for v in TABLES.values())} columns).

Ground each comment in the actual data: look at value ranges and sample values first, and state units, formats and code lists when the data reveals them (for example what unit a numeric amount is in, whether a timestamp is a number of seconds or milliseconds, which codes a status column takes). Do not change any data or column definitions.

In your final answer, say which comments are inferences you could not fully verify from the data (so a human can confirm them), and report how you verified that all comments were applied."""


def setup(ctx: Ctx) -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {ctx.schema}")
    for q in SEED:
        sql(q.format(s=ctx.schema))
    ctx.extra["counts"] = {t: sql_val(f"SELECT count(*) FROM {ctx.schema}.{t}") for t in TABLES}


def reference(ctx: Ctx) -> str:
    s = ctx.schema
    tc = {
        "cust": "One row per customer account, with country, segment, lifetime value and activity flag.",
        "ord": "One row per customer order, with amount in minor currency units, currency and status code.",
        "evt_log": "One row per tracked customer behaviour event (login, view, cart, checkout) with a JSON payload.",
    }
    cc = {
        "cust.cid": "Customer id, unique key of the table.", "cust.cname": "Customer display name.",
        "cust.ctry": "Two-letter ISO country code (FR, DE, US, JP, BR).",
        "cust.ltv_c": "Customer lifetime value in cents (minor currency units), not whole currency.",
        "cust.ts_cr": "Timestamp when the customer account was created.",
        "cust.flg_act": "Boolean flag: true when the customer account is active.",
        "cust.seg": "Customer segment: SMB, ENT (enterprise) or CONS (consumer).",
        "ord.oid": "Order id, unique key of the table.", "ord.cid": "Customer id that placed the order, joins to cust.cid.",
        "ord.amt_c": "Order amount in cents (minor currency units) of the order currency.",
        "ord.ccy": "Currency code of the order: EUR, USD or JPY.",
        "ord.st": "Order status code: N, S, C, R (probably new, shipped, cancelled, returned; inferred).",
        "ord.ts": "Timestamp when the order was placed.",
        "evt_log.eid": "Event id, unique key of the table.", "evt_log.cid": "Customer id that generated the event.",
        "evt_log.ev": "Event type: login, view, add_to_cart or checkout.",
        "evt_log.ts_ms": "Event time as epoch milliseconds (not seconds).",
        "evt_log.payload": "JSON string with session id (sid) and user agent (ua).",
    }
    for t, c in tc.items():
        sql(f"COMMENT ON TABLE {s}.{t} IS '{c}'")
    for k, c in cc.items():
        t, col = k.split(".")
        sql(f"COMMENT ON COLUMN {s}.{t}.{col} IS '{c}'")
    return ("All 3 table comments and all 18 column comments applied; verified via information_schema.columns. "
            "Inferences I could not fully verify: ord.st status code meanings (N,S,C,R are assumed new, shipped, "
            "cancelled, returned) and that amounts are cents (assumed from magnitude).")


def grade(ctx: Ctx, answer: str) -> list[Check]:
    s_name, cat = ctx.schema_name, CATALOG
    out: list[Check] = []
    rows = sql(f"SELECT table_name, column_name, comment, data_type FROM {cat}.information_schema.columns "
               f"WHERE table_schema='{s_name}' ORDER BY table_name, ordinal_position")
    cm = {f"{r[0]}.{r[1]}": (r[2] or "").strip() for r in rows}
    expected = [f"{t}.{c}" for t, cols in TABLES.items() for c in cols]
    unchanged_cols = sorted(cm) == sorted(expected)
    counts_ok = ctx.extra.get("counts") == {t: sql_val(f"SELECT count(*) FROM {ctx.schema}.{t}") for t in TABLES}
    out.append(Check("data and column definitions unchanged", unchanged_cols and counts_ok, 2))
    tcm = {r[0]: (r[1] or "").strip() for r in sql(
        f"SELECT table_name, comment FROM {cat}.information_schema.tables WHERE table_schema='{s_name}'")}
    out.append(Check("3 table comments, each >= 40 chars", all(len(tcm.get(t, "")) >= 40 for t in TABLES), 2,
                     str({t: len(tcm.get(t, "")) for t in TABLES})))
    have = [k for k in expected if len(cm.get(k, "")) >= 8]
    out.append(Check(f"every column has a real comment ({len(expected)} columns)", len(have) == len(expected), 3,
                     f"{len(have)}/{len(expected)}"))
    echo = [k for k in expected if cm.get(k, "").lower() in (k.split(".")[1].lower(), f"the {k.split('.')[1].lower()}")]
    out.append(Check("no comment merely echoes the column name", not echo, 1, str(echo)))

    def c(k: str) -> str:
        return cm.get(k, "").lower()

    out.append(Check("ltv_c documented as cents / minor units", bool(re.search(r"cent|minor", c("cust.ltv_c"))), 2, c("cust.ltv_c")))
    out.append(Check("amt_c documented as cents / minor units", bool(re.search(r"cent|minor", c("ord.amt_c"))), 2, c("ord.amt_c")))
    out.append(Check("ts_ms documented as epoch MILLISECONDS", bool(re.search(r"milli|\bms\b", c("evt_log.ts_ms"))), 2, c("evt_log.ts_ms")))
    out.append(Check("st lists its codes (>= 3 of N,S,C,R)", sum(1 for x in "nscr" if re.search(rf"\b{x}\b", c("ord.st"))) >= 3, 2, c("ord.st")))
    out.append(Check("seg lists SMB/ENT/CONS", all(x in c("cust.seg") for x in ("smb", "ent", "cons")), 1, c("cust.seg")))
    out.append(Check("ctry mentions ISO / country code", bool(re.search(r"iso|country", c("cust.ctry"))), 1, c("cust.ctry")))
    out.append(Check("payload identified as JSON", "json" in c("evt_log.payload"), 1, c("evt_log.payload")))
    out.append(Check("flg_act identified as boolean/active", bool(re.search(r"activ", c("cust.flg_act"))), 1, c("cust.flg_act")))
    a = (answer or "").lower()
    out.append(Check("flags what is inferred/unverified (epistemic honesty)",
                     bool(re.search(r"infer|assum|could not (fully )?verify|unverified|probably|confirm", a)), 2))
    out.append(Check("reports how application was verified",
                     bool(re.search(r"information_schema|describe|show|verif", a)), 1))
    return out


MISSION = Mission(
    id="M7", title="Governance: document UC tables from the data", capability="C9", difficulty=2,
    prompt=prompt, setup=setup, grade=grade, reference=reference, max_minutes=10,
)
