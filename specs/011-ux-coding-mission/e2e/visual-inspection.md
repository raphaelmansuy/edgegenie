# Screenshot inspection ledger

Every retained screenshot was opened and visually inspected. Earlier iterations are retained to show the defects and refinements; accepted images are the mission acceptance and durable-session regression evidence. SHA-256 and dimensions are recorded in [visual-inspection.json](visual-inspection.json).

| Image | Review | Observation |
|---|---|---|
| [iteration-01/01-running-desktop.png](iteration-01/01-running-desktop.png) | baseline | Objective, current state, plan and source-backed results are legible; desktop hierarchy retained. |
| [iteration-01/02-achieved-dark.png](iteration-01/02-achieved-dark.png) | improved | Dark palette is legible; results were too far below the plan. Completed missions now lead with outcome and outputs. |
| [iteration-01/03-mobile-light.png](iteration-01/03-mobile-light.png) | improved | Repeated status card and full composer consumed too much phone height. Removed completed-state duplication and compacted the centre composer. |
| [iteration-01/04-long-mobile-dark.png](iteration-01/04-long-mobile-dark.png) | improved | Long objective occupied seven lines. Phone titles now clamp at three lines and retain a complete request disclosure. |
| [iteration-02/01-running-desktop.png](iteration-02/01-running-desktop.png) | baseline | Real stream renders an honest incomplete plan and empty result placeholders; no clipped controls. |
| [iteration-02/02-offline.png](iteration-02/02-offline.png) | improved | Hover made copied text disappear on a light background; changed mission copy controls to the existing quiet variant and verified hover contrast in the final run. |
| [iteration-03/01-running-desktop.png](iteration-03/01-running-desktop.png) | accepted | Running objective and reported plan have a clear hierarchy; empty outputs/evidence remain explicit. |
| [iteration-03/02-offline.png](iteration-03/02-offline.png) | accepted | Offline wording preserves last-known execution; copied feedback is readable after the hover fix; remote controls are disabled. |
| [iteration-03/03-return-completed.png](iteration-03/03-return-completed.png) | accepted | Completed explanation is presented as ready for review, with outcome first and no invented proof. |
| [iteration-03/04-stopped-queue.png](iteration-03/04-stopped-queue.png) | accepted | Stopped queue is explicit; accepted follow-up remains selectable; no active-work claim is displayed. |
| [iteration-03/05-achieved-desktop.png](iteration-03/05-achieved-desktop.png) | accepted | Achieved outcome, generated notebook and three verified requirements fit the desktop work area; plan follows results. |
| [iteration-03/06-evidence-source.png](iteration-03/06-evidence-source.png) | accepted | Expanded evidence shows its exact input and result; screenshot scroll was adjusted so the complete source body can be inspected. |
| [iteration-03/07-approval.png](iteration-03/07-approval.png) | accepted | Approval state is clear; the offered decision controls, target and reason are visible in the dock. |
| [iteration-03/08-recovery.png](iteration-03/08-recovery.png) | accepted | Restore is explicit, saved progress is visible and input is disabled; prior plan is retained as reported. |
| [iteration-03/09-wide-dark.png](iteration-03/09-wide-dark.png) | accepted | 1920px dark view keeps a readable content measure with legible output and evidence sections. |
| [iteration-03/10-tablet-light.png](iteration-03/10-tablet-light.png) | accepted | 1024px view retains the mission, outcome and output with the assistant hidden and compact centre composition. |
| [iteration-03/11-mobile-light.png](iteration-03/11-mobile-light.png) | accepted | 390px light view places achieved outcome and notebook output ahead of the completed plan; controls fit. |
| [iteration-03/12-mobile-dark.png](iteration-03/12-mobile-dark.png) | accepted | 375px dark view preserves a three-line title, readable summary and independent scrolling above the compact composer. |
| [iteration-03/13-mobile-320.png](iteration-03/13-mobile-320.png) | accepted | 320px light view wraps metadata and body text without horizontal overflow; title remains bounded with full request available. |
| [iteration-03/14-last-achieved.png](iteration-03/14-last-achieved.png) | accepted | Historical achieved mission is explicitly labelled Mission history; current work stays visible in the dock and return action is clear. |
| [iteration-03/15-history-activity.png](iteration-03/15-history-activity.png) | accepted | Activity tab shows only the selected historical turn, with its prompt, reported plan and actual tool cards. |
| [iteration-03/16-blocked.png](iteration-03/16-blocked.png) | accepted | Blocked state exposes missing permission and failed-call count; both overview and dock agree that only one of two requirements is proven. |
| [iteration-03/17-failed.png](iteration-03/17-failed.png) | accepted | Failed state reports the reason and retains saved work; dock now says Work failed rather than claiming ongoing execution. |
| [iteration-03/18-archived.png](iteration-03/18-archived.png) | accepted | Archived state is consistent in overview and dock; read-only composition has no Retry, restore or suggested-send actions. |
| [iteration-03/19-empty.png](iteration-03/19-empty.png) | accepted | Empty ready session says No mission yet and invites an instruction; disabled picker never invents an accepted mission. |
| [iteration-03/20-checking.png](iteration-03/20-checking.png) | accepted | Auditing state says Checking work and preserves the incomplete reported plan; proof is independent of execution completion. |
| [iteration-03/21-long-request-dark.png](iteration-03/21-long-request-dark.png) | accepted | Long unicode request is fully available in a wrapped disclosure while the phone heading stays within three visible lines. |
| [iteration-03/22-invalid-source-dark.png](iteration-03/22-invalid-source-dark.png) | accepted | Long output name wraps; written/read references stay distinct; unresolved proof has an explicit source warning and unknown plan text remains visible. |
| [iteration-03/23-webkit-mobile.png](iteration-03/23-webkit-mobile.png) | accepted | WebKit dark phone view now uses a consistent 44px mission picker; outcome, text contrast and composer fit the viewport. |
| [regression/screenshots/01-server-running-light.png](regression/screenshots/01-server-running-light.png) | accepted | Return-link success feedback is visible; a plan not yet streamed is explicitly unavailable. |
| [regression/screenshots/02-offline.png](regression/screenshots/02-offline.png) | accepted | Offline observation state is distinct from running work; disabled stop remains visible. |
| [regression/screenshots/03-reconnected.png](regression/screenshots/03-reconnected.png) | accepted | Reconnection restores live wording and enabled actions without changing the accepted objective. |
| [regression/screenshots/04-return-after-page-close.png](regression/screenshots/04-return-after-page-close.png) | accepted | Fresh browser return restores the completed response and recorded duration; no fabricated achievement. |
| [regression/screenshots/05-queued-work.png](regression/screenshots/05-queued-work.png) | accepted | Queued message stays in the conversation while Mission 1 remains foreground; queue count and composer focus are visible. |
| [regression/screenshots/06-stopped-queue.png](regression/screenshots/06-stopped-queue.png) | accepted | Stopped state retains both cancelled instructions with honest empty results for the selected follow-up. |
| [regression/screenshots/07-waiting-for-approval.png](regression/screenshots/07-waiting-for-approval.png) | accepted | Pending permission target and all offered decisions are legible; mission overview does not authorize it automatically. |
| [regression/screenshots/08-return-and-approve.png](regression/screenshots/08-return-and-approve.png) | accepted | Explicit session permission decision completes the demonstration; response remains ready for review without tool proof. |
| [regression/screenshots/09-server-restarted.png](regression/screenshots/09-server-restarted.png) | accepted | Server restart preserves mission and plan and presents a prominent restore action. |
| [regression/screenshots/10-agent-restored.png](regression/screenshots/10-agent-restored.png) | accepted | Restored session retains Interrupted status and incomplete-plan note while composition becomes available again. |
| [regression/screenshots/11-wide-dark.png](regression/screenshots/11-wide-dark.png) | accepted | Dark desktop completed response and empty evidence placeholders are readable and separated by quiet borders. |
| [regression/screenshots/12-narrow-light.png](regression/screenshots/12-narrow-light.png) | accepted | 760px view shows the completed response with accessible conversation navigation and compact centre composer. |
| [regression/screenshots/13-mobile-dark.png](regression/screenshots/13-mobile-dark.png) | accepted | 390px dark view wraps the completed explanation and preserves a usable composer below the independently scrolling result. |
