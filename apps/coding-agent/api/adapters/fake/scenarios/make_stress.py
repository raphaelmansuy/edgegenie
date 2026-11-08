import json, random
random.seed(1)
ups=[]
ups.append({"sessionUpdate":"agent_thought_chunk","messageId":"t","content":{"type":"text","text":"Reasoning about the bakery KPI task. "*400}})
for i in range(60):
    cid=f"c{i}"
    ups.append({"sessionUpdate":"tool_call","toolCallId":cid,"title":"dbx_list_notebooks","kind":"other","status":"pending","rawInput":{}})
    ups.append({"sessionUpdate":"tool_call_update","toolCallId":cid,"status":"completed","rawInput":{"path":f"/Shared/e2e_{i}"},"content":{"type":"text","text":"x"*800}})
# a long markdown answer: unbalanced ` and ** inside ONE paragraph (no blank lines)
para=" ".join(("word `unclosed **bold and /Users/a/b/c%d.py path"%i) for i in range(1500))
answer=para[:30000]+"\n"*3000+"padding the model emitted"+"\n\n"+"\n".join(f"- item {i} with `code` and **bold**" for i in range(100))+"\n\nEVIDENCE\n\n| requirement | tool | summary |\n|---|---|---|\n| do the work | dbx_run_sql | 3 rows |\n"
json.dump({"models":["fake/model-a"],"turn":{"updates":ups,"answer":answer,"usage":{"inputTokens":1,"outputTokens":1,"cachedReadTokens":0,"totalTokens":2}}},
 open("api/adapters/fake/scenarios/stress.json","w"))
print(len(answer))
