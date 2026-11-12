#!/usr/bin/env python3
"""The Pipelines API body, built and refused locally. Pure: no I/O, no environment.

A Lakeflow pipeline is one object with a spec, and four of that spec's fields are rules rather than
values: a serverless pipeline **requires** Unity Catalog, **rejects** `clusters`, needs an `edition` the
platform sells, and must name at least one library. Each rule, if broken, produces a platform `400` whose
text is accurate and hard to act on — `clusters` and `serverless` together, for instance, answers
*"Only one of clusters or serverless is supported"* without saying which one this product wants.

So the rules live here, as one function that returns a body or one sentence (spec 014 [TOOL-7]). The
tool server calls it before it makes a call; `tests/test_pipeline_body.py` holds it to a table. This is
the same shape as `job_graph.py`, and for the same reason: the rule must be testable without a
transport, and the refusal must cost nothing.

`libraries` is a list of `{notebook: {path}}`, `{file: {path}}` or `{glob: {include}}`. This product
writes notebooks and files, so both are accepted; `glob` is accepted because a bundle's pipeline uses it
and an agent that copies one should not be punished.
"""
from __future__ import annotations

from typing import Callable

#: The editions the platform sells. `ADVANCED` is required for expectations and for serverless.
EDITIONS: tuple[str, ...] = ("CORE", "PRO", "ADVANCED")

#: The library shapes a pipeline accepts.
LIBRARY_KINDS: tuple[str, ...] = ("notebook", "file", "glob")

#: The platform's own limit.
MAX_NAME = 200


class PipelineProblem(ValueError):
    """A spec the platform would refuse, as one sentence naming what to change."""


def build(
    name: str,
    notebooks: list[str] | None = None,
    files: list[str] | None = None,
    glob: str = "",
    catalog: str = "",
    schema: str = "",
    serverless: bool = True,
    edition: str = "ADVANCED",
    channel: str = "CURRENT",
    continuous: bool = False,
    development: bool = False,
    check_path: Callable[[str], None] | None = None,
) -> dict:
    """The create/update body, or raise `PipelineProblem`.

    `check_path` is the session's write fence, passed in rather than imported so this module stays pure —
    the caller supplies the rule and this function supplies the shape.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise PipelineProblem("a pipeline needs a name; it is what the rail and the page show")
    if len(clean_name) > MAX_NAME:
        raise PipelineProblem(f"a pipeline name is at most {MAX_NAME} characters; got {len(clean_name)}")

    libraries: list[dict] = []
    for path in notebooks or []:
        value = (path or "").strip()
        if not value:
            continue
        if not value.startswith("/"):
            raise PipelineProblem(
                f"a pipeline library notebook is an absolute workspace path; got {value!r}")
        if check_path:
            check_path(value)
        libraries.append({"notebook": {"path": value}})
    for path in files or []:
        value = (path or "").strip()
        if not value:
            continue
        if not value.startswith("/"):
            raise PipelineProblem(
                f"a pipeline library file is an absolute workspace path; got {value!r}")
        if check_path:
            check_path(value)
        libraries.append({"file": {"path": value}})
    if (glob or "").strip():
        libraries.append({"glob": {"include": glob.strip()}})

    if not libraries:
        raise PipelineProblem(
            "a pipeline needs at least one library: pass `notebooks` or `files` with the paths "
            "dbx_write_notebook / dbx_write_file returned")

    clean_edition = (edition or "ADVANCED").strip().upper()
    if clean_edition not in EDITIONS:
        raise PipelineProblem(
            f"edition is one of {', '.join(EDITIONS)}; got {edition!r}. "
            "ADVANCED is required for expectations and for serverless")

    body: dict = {
        "name": clean_name,
        "libraries": libraries,
        "edition": clean_edition,
        "channel": (channel or "CURRENT").strip().upper(),
        "continuous": bool(continuous),
        "development": bool(development),
    }

    if not serverless:
        raise PipelineProblem(
            "this tool creates serverless pipelines only. A classic pipeline needs `clusters`, which "
            "means choosing a node type and a worker count — build it in Databricks and open it here")

    # The documented requirement, and the reason this is refused rather than sent: a serverless pipeline
    # publishes to Unity Catalog, so a create without a catalog fails AFTER the round trip with a
    # sentence about catalogs that does not mention serverless (spec 014 [RB-8], [E-4]).
    clean_catalog = (catalog or "").strip()
    if not clean_catalog:
        raise PipelineProblem(
            "a serverless pipeline always publishes to Unity Catalog, so it needs a catalog. "
            "Pass catalog='main' (or the catalog the user named) and schema, then call again")
    clean_schema = (schema or "").strip()
    if not clean_schema:
        raise PipelineProblem(
            "a serverless pipeline publishes into a schema; pass schema='<name>'. "
            "It is created if it does not exist and the caller may create there")
    body["serverless"] = True
    body["catalog"] = clean_catalog
    body["schema"] = clean_schema
    # `clusters` is ABSENT, not empty: the platform rejects the field alongside serverless, and an empty
    # list reads as "classic compute with no settings".
    return body


def describe_libraries(body: dict) -> list[str]:
    """The library paths in a body, for a page and for a tool's result. One shape, one reader."""
    out: list[str] = []
    for library in body.get("libraries") or []:
        for kind in LIBRARY_KINDS:
            node = library.get(kind) or {}
            value = node.get("path") or node.get("include")
            if value:
                out.append(value)
    return out


def removed_libraries(before: dict, after: dict) -> list[str]:
    """The paths an edit removes. An edit that drops a library stops maintaining its tables, so it is
    reported rather than refused: the user may have asked for exactly that (spec 014 [E-18])."""
    had = describe_libraries(before)
    now = set(describe_libraries(after))
    return [path for path in had if path not in now]


def start_body(full_refresh: bool = False, validate_only: bool = False,
               refresh_selection: list[str] | None = None,
               full_refresh_selection: list[str] | None = None) -> dict:
    """The `POST …/updates` body.

    `full_refresh` is always sent as a boolean, never omitted and never defaulted by the platform: it is
    the difference between "re-read new data" and "re-read every source", which is the difference between
    seconds and an hour of compute (spec 014 [PIPE-3]).

    `full_refresh` and a selection are mutually exclusive on the platform; so are a selection and
    `validate_only`. This function refuses rather than sending both.
    """
    if full_refresh and (refresh_selection or full_refresh_selection):
        raise PipelineProblem(
            "full_refresh re-reads every source; a selection names some. Pass one, not both")
    if validate_only and (refresh_selection or full_refresh_selection):
        raise PipelineProblem(
            "validate_only checks the code without running it; a selection has no meaning")
    body: dict = {"full_refresh": bool(full_refresh)}
    if validate_only:
        body["validate_only"] = True
    if refresh_selection:
        body["refresh_selection"] = list(refresh_selection)
    if full_refresh_selection:
        body["full_refresh_selection"] = list(full_refresh_selection)
    return body
