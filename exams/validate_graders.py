#!/usr/bin/env python3
"""Validate every grader: a no-op must fail, the reference solution must score 100%.

    python validate_graders.py [M1 M2 ...]
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import Ctx, delete_path, score, sql  # noqa: E402
from missions import all_missions  # noqa: E402


def teardown(ctx: Ctx) -> None:
    try:
        sql(f"DROP SCHEMA IF EXISTS {ctx.schema} CASCADE")
    except Exception as e:  # noqa: BLE001
        print("  teardown schema:", e)
    delete_path(ctx.home)


def main() -> int:
    want = set(sys.argv[1:])
    bad = 0
    for mid, m in all_missions().items():
        if want and mid not in want:
            continue
        ctx = Ctx(run_id="v" + uuid.uuid4().hex[:5], mission=mid)
        print(f"== {mid} {m.title}  (run {ctx.run_id})")
        try:
            m.setup(ctx)
            noop = m.grade(ctx, "")
            ns, nt = score(noop)
            print(f"  no-op        : {ns}/{nt}  {'OK (fails)' if ns < nt else 'BAD: no-op passes!'}")
            if ns >= nt:
                bad += 1
            ans = m.reference(ctx)
            ref = m.grade(ctx, ans)
            rs, rt = score(ref)
            print(f"  reference    : {rs}/{rt}  {'OK' if rs == rt else 'BAD: reference fails'}")
            for c in ref:
                if not c.passed:
                    print(f"     x {c.name}: {c.detail}")
                    bad += 1
        except Exception as e:  # noqa: BLE001
            print("  ERROR:", repr(e)[:400])
            bad += 1
        finally:
            m.cleanup(ctx)
            teardown(ctx)
    print("grader validation:", "ALL GOOD" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
