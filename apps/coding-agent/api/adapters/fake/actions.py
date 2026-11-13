"""Scripted-agent actions call the real MCP facade, never fabricate successful workspace results."""

import json
import re
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def resolve(value, results, folder):
    if isinstance(value, dict):
        return {k: resolve(v, results, folder) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, results, folder) for v in value]
    if not isinstance(value, str):
        return value
    if value == "$folder":
        return folder
    if value.startswith("$") and re.fullmatch(r"\$[\w.]+", value):
        current = results
        for part in value[1:].split("."):
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current

    def replacement(match):
        return str(resolve("$" + match.group(1), results, folder))

    return re.sub(r"\$\{([\w.]+)\}", replacement, value).replace("$folder/", folder.rstrip("/") + "/")


async def run_actions(url, sid, actions, answer, folder, send, permit, epoch, variables=None):
    results = dict(variables or {})
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            for index, step in enumerate(actions):
                name = step["tool"]
                args = resolve(step.get("arguments", {}), results, folder)
                cid = f"fixture_{epoch}_{index}"

                def update(value):
                    send(
                        {
                            "jsonrpc": "2.0",
                            "method": "session/update",
                            "params": {"sessionId": sid, "update": value},
                        }
                    )

                update(
                    {
                        "sessionUpdate": "tool_call",
                        "toolCallId": cid,
                        "name": name,
                        "title": "db_" + name,
                        "kind": "other",
                        "status": "pending",
                        "rawInput": {},
                    }
                )
                if step.get("ask"):
                    allowed = await permit(cid, name, args, update)
                    if not allowed:
                        update(
                            {
                                "sessionUpdate": "tool_call_update",
                                "toolCallId": cid,
                                "status": "failed",
                                "rawOutput": {
                                    "error": "The user rejected permission to use this specific tool call"
                                },
                            }
                        )
                        return "", True
                else:
                    update(
                        {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": cid,
                            "status": "in_progress",
                            "rawInput": args,
                        }
                    )
                result = await client.call_tool(name, args)
                text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
                try:
                    body = json.loads(text)
                except ValueError:
                    body = {"text": text}
                results[step.get("id", str(index))] = body
                update(
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": cid,
                        "status": "failed" if result.isError else "completed",
                        "rawOutput": {"error": text} if result.isError else {"output": text},
                        "content": [{"type": "content", "content": {"type": "text", "text": text}}],
                    }
                )
                if result.isError:
                    break
    return resolve(answer, results, folder), False
