Your coding agent should not need you to stay on the page.

OpenGenie now runs every agent session on the server. Close the tab, lose the Wi-Fi, or come back tomorrow: the work keeps going, and the answer is waiting for you.

THE PAIN POINT

A data agent runs for minutes, sometimes much longer. When the connection to the browser drops, most agent UIs leave you guessing. Is it still working? Did the write land? Should I ask again?

Asking again is the dangerous answer. A repeated prompt can create a second table or rerun a job. The disconnect behaviour of Genie Code was the motivation for this work. It is a motivation, not a benchmark: I have not compared the two side by side.

WHAT CHANGED

- Execution belongs to the server. The browser only watches and steers.
- Each message is written to a durable journal before the server answers. Lakebase or Postgres in production, SQLite locally.
- Reconnect, close the page, or restart the server: the viewer replays the journal in order. No duplicate messages.
- Pending approvals wait on the server too, so the question is still there when you return.
- A returning user sees the result and the plan that produced it, with a status that says what needs them: running, waiting for a decision, or ready for review.

WHAT IT DELIBERATELY DOES NOT DO

- A restart does not replay an uncertain write. The app marks the operation as interrupted and offers a restore. A Databricks write can succeed before its response is saved, so repeating it is the riskiest move available.
- It runs one active worker per journal. It is not a horizontally distributed scheduler.
- Long work still spends model budget. Durable does not mean free.

THE RULE UNDER THE FEATURE

A closed tab should never cancel a data change, and a restart should never silently repeat one. Those two rules are the whole design.

The specification, the failure cases and the browser evidence (disconnect, page close, restart, permissions, mobile) are in the repository:
https://github.com/raphaelmansuy/opengenie/tree/main/specs/010-long-running

OpenGenie is open source under Apache-2.0. Try it on your own workspace, and tell me where it breaks.

#Databricks #DataEngineering #AIAgents #OpenSource
