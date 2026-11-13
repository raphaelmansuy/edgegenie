"""AG-55: one cell changed in-place, 59 SOURCE segments byte-identical; no compute required."""

from lib import Check, Ctx, Mission, export_nb, import_nb, mkdirs

SEPARATOR = "# COMMAND ----------\n"
SEED = "# Databricks notebook source\n" + ("\n" + SEPARATOR).join(
    f"# CELL {i}: preserve this exact cell\n# "
    + ("preserve " * 18)
    + f'\nprint("cell-{i}-{("BROKEN" if i == 37 else "unchanged")}")\n'
    for i in range(60)
)


def path(ctx):
    return ctx.home + "/long_notebook"


def setup(ctx: Ctx):
    mkdirs(ctx.home)
    import_nb(path(ctx), SEED)
    ctx.extra["longNotebookBase"] = export_nb(path(ctx))


def prompt(ctx):
    return f"""- Fix the literal BROKEN to FIXED in zero-based cell 37 of notebook {path(ctx)}.

For the target source use dbx_read with kind=notebook and cell=37, which returns its raw source, SHA and whole-notebook revision without echoing the other cells.

Constraints: keep every other cell and all separators byte-identical. Read the revision and SHA,
propose one revision-bound replace_cell operation, and read back the produced revision after approval.
Do not run code or SQL. Quote actual result values and exact invocation IDs in Evidence."""


def reference(ctx):
    current = export_nb(path(ctx))
    if current != ctx.extra["longNotebookBase"]:
        raise RuntimeError(
            "The isolated fixture changed before its reference solution."
        )
    parts = current.split(SEPARATOR)
    parts[37] = parts[37].replace("BROKEN", "FIXED")
    import_nb(path(ctx), SEPARATOR.join(parts))
    assert export_nb(path(ctx)) == SEPARATOR.join(parts)
    return "Cell 37 contains FIXED; the other 59 SOURCE segments are byte-identical."


def grade(ctx, answer):
    before = (ctx.extra["longNotebookBase"] or "").split(SEPARATOR)
    source = export_nb(path(ctx))
    after = (source or "").split(SEPARATOR)
    same_shape = len(before) == len(after) == 60
    changed = [i for i in range(60) if not same_shape or before[i] != after[i]]
    return [
        Check("same notebook path and 60 cells", bool(source) and same_shape, 1),
        Check("exactly cell 37 changed", changed == [37], 3, str(changed)),
        Check(
            "target replacement only",
            same_shape and after[37] == before[37].replace("BROKEN", "FIXED"),
            3,
        ),
        Check(
            "all other 59 raw segments byte-identical",
            same_shape and all(before[i] == after[i] for i in range(60) if i != 37),
            3,
        ),
    ]


MISSION = Mission(
    id="M9",
    title="One-cell edit in a long notebook",
    capability="AG-55",
    difficulty=3,
    prompt=prompt,
    setup=setup,
    reference=reference,
    grade=grade,
    uses_schema=False,
)
