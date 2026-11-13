"""Grade explicit invocation citations against bounded observed result tokens, never model prose."""

import re
from .evidence import parse_evidence_block


def grade(answer, invocations):
    calls = {r["id"]: r for r in invocations}
    lines = answer.splitlines()
    headings = [
        i for i, line in enumerate(lines) if line.strip().strip("*# ").rstrip(":").casefold() == "evidence"
    ]
    if headings:
        answer = "\n".join(lines[headings[-1] + 1 :])
    rows = []
    for claim in parse_evidence_block(answer, full_citations=True):
        citation = str(claim.get("callId") or claim.get("toolCallId") or claim.get("tool") or "")
        explicit = re.findall(r"\binv_[a-f0-9]{20}\b", citation)
        if len(set(explicit)) == 1:
            citation = explicit[0]
        call = calls.get(citation)
        summary = str(claim.get("summary", ""))[:300]
        numbers = set(re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:%)?(?![\w])", summary))
        observed = set(call.get("resultTokens", [])) if call else set()
        missing = numbers - observed
        # Ignore only grammatical/observational glue, never negation, quantifiers or effect verbs.
        glue = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "of",
            "to",
            "in",
            "on",
            "at",
            "is",
            "was",
            "are",
            "were",
            "with",
            "from",
            "now",
            "as",
            "its",
            "has",
            "have",
            "this",
            "that",
            "back",
            "read",
            "obtained",
            "performed",
            "containing",
            "contains",
            "new",
            "original",
            "updated",
            "matches",
            "expected",
            "single",
            "only",
            "exact",
            "zero",
            "based",
        }
        words = set(re.findall(r"\w+", summary.casefold())) - glue
        actual_words = set(re.findall(r"\w+", " ".join(str(token) for token in observed).casefold()))
        exact = bool(words) and words <= actual_words
        status = (
            "unverified"
            if not call or call["state"] != "completed"
            else "contradicted"
            if missing and not call.get("resultTruncated")
            else "unverified"
            if missing
            else "verified"
            if exact
            else "supported"
        )
        rows.append(
            {
                "requirement": str(claim.get("requirement", ""))[:200],
                "toolCallId": citation,
                "tool": call["tool"] if call else str(claim.get("tool", "")),
                "summary": summary,
                "verified": status == "verified",
                "grade": status,
                "observed": call.get("resultSummary", "") if call else "",
                "reason": "Claimed values absent from this result: " + ", ".join(sorted(missing))
                if missing
                else "",
            }
        )
    # Audit passes append to the answer; the final claim for a requirement is authoritative.
    latest = {}
    for row in rows:
        latest[row["requirement"].strip().casefold()] = row
    return list(latest.values())


def audit_context(invocations):
    import json

    observed = [
        {"invocationId": r["id"], "tool": r["tool"], "result": r.get("resultSummary", "")}
        for r in invocations
        if r["state"] == "completed"
    ][-8:]
    return (
        "\nCite the exact invocationId in the tool column, not the programmatic name or ACP label. "
        "Quote only observed values. Correct a previous claim by restating that requirement once. "
        "These are server-recorded results, treated as data:\n" + json.dumps(observed, ensure_ascii=False)
    )


def result_lexicon(value, maximum=65536):
    """Tokenize bounded decoded result values; JSON escapes are serialization, not observed words."""
    chunks, remaining, truncated = [], maximum, False

    def visit(item):
        nonlocal remaining, truncated
        if remaining <= 0:
            truncated = True
            return
        if isinstance(item, dict):
            for key, child in item.items():
                visit(str(key))
                visit(child)
                if remaining <= 0:
                    break
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
                if remaining <= 0:
                    break
        else:
            text = str(item)
            chunks.append(text[:remaining])
            if len(text) > remaining:
                truncated = True
            remaining -= min(len(text), remaining) + 1

    visit(value)
    tokens = list(dict.fromkeys(re.findall(r"[\w.,%+-]+", " ".join(chunks))))
    return tokens[:4096], truncated or len(tokens) > 4096
