# Screenshot visual inspection ledger

[Evidence overview](README.md) · [Implementation checkpoint](../14-implementation-outcome.md) · [Machine test report](report.json) · [Full hashes and dimensions](screenshots-manifest.json)

Reviewed 2026-11-12. Each of the 18 final PNG files below was opened individually with the image viewer and visually inspected. Images were captured from the actual app; no image editing or compositing was used. The linked manifest ties observations to the exact retained bytes.

## Iterations and corrections

1. Initial captures exposed toolbar/context-handle overlap, incorrect clean-query wording, singular row copy and a source-pane sizing issue. Corrected SQL layout/labels and recaptured.
2. Theme/responsive captures sometimes ran before editor/theme/layout settled. Switched the harness to the real theme menu and explicit readiness/font/layout checks; recaptured light, dark, phone and tablet screens.
3. Added an explicit save-copy review dialog. Inspected focus, destination/effect copy and button placement.
4. Assistant SQL promotion revealed low action contrast. Added a dedicated dark-surface action style and disabled promotion while the proposal is streaming.
5. Injected a response loss after accepted create. Added persisted frozen create intent, exact-key recovery after reload, Check again state and an explanation of the uncertain outcome. Inspected and recaptured the recovery dialog.
6. Waiting for the completed proposal exposed repeated fixture output from the existing evidence supervisor. The test now explicitly requests a proposal without tools, matching the no-execution interaction; the final screenshot shows one completed answer. Rebuilt, reran E2E and inspected every final image again.

## Final per-image observations

| Screenshot | Pixels | SHA-256 prefix | Visual review |
|---|---|---|---|
| [01-library-light.png](screenshots/01-library-light.png) | 1440 × 1000 | `000f4126b07a` | Clear Queries heading, search, owner and favorites controls; aligned rows; cache scope disclosed; new-query action unobscured. |
| [02-query-editor-light.png](screenshots/02-query-editor-light.png) | 1440 × 1000 | `982a52720428` | Saved Query label agrees with clean source; SQL highlighting is legible; toolbar clears the context handle; empty results state is distinct. |
| [03-query-running.png](screenshots/03-query-running.png) | 1440 × 1000 | `8d11a2742a44` | Waiting state and cancel controls are visible; Run is disabled during the active attempt; editor and dock retain their positions. |
| [04-query-results.png](screenshots/04-query-results.png) | 1440 × 1000 | `d4bc3640da3a` | Three result rows, schema labels, success state and preview bounds are legible; table aligns by ordinal and remains inside the workspace. |
| [05-run-provenance.png](screenshots/05-run-provenance.png) | 1440 × 1039 | `3a652a2d12bb` | Expanded snapshot shows run, warehouse, start, hash and executed SQL; long hash wraps within its column and details remain readable. |
| [06-parameters-and-null.png](screenshots/06-parameters-and-null.png) | 1440 × 1000 | `8d56d94eb53f` | Parameter name/value/type/NULL controls are distinct; dirty source label is correct; NULL cell differs from text and singular row copy is correct. |
| [07-policy-refusal.png](screenshots/07-policy-refusal.png) | 1440 × 1000 | `2c2c3740ed31` | Server refusal is prominent above source; previous successful output remains labeled stale; error does not cover editor or result controls. |
| [08-canceled.png](screenshots/08-canceled.png) | 1440 × 1000 | `4faad95cc48a` | Terminal Canceled is distinct from pending cancellation; Run is available again; no fabricated result rows are displayed. |
| [09-own-history.png](screenshots/09-own-history.png) | 1440 × 1000 | `a2d0a22e66d7` | Own-history tab is selected; three runs have aligned status and Open snapshot controls; history remains separate from chat sessions. |
| [10-query-dark.png](screenshots/10-query-dark.png) | 1440 × 1000 | `137f4e316b32` | Dark app shell and editor agree; syntax, input surfaces and action text are legible; captured after theme/editor readiness. |
| [11-mobile-editor.png](screenshots/11-mobile-editor.png) | 375 × 900 | `4f2dfa16c4e0` | 375px editor layout wraps header and toolbar; warehouse remains usable; Editor/Results controls and composer fit without horizontal page overflow. |
| [12-mobile-results.png](screenshots/12-mobile-results.png) | 375 × 900 | `269c6dc95ea3` | 375px results view has visible success/count, schema, exact value and copy action; query toolbar and output tabs remain usable. |
| [13-tablet-editor.png](screenshots/13-tablet-editor.png) | 768 × 1000 | `02abe1406ea6` | 768px view shows editor and results together; controls wrap cleanly; composer remains separate below the document workspace. |
| [14-query-chat-context.png](screenshots/14-query-chat-context.png) | 1440 × 1000 | `07f04fa77b39` | Snapshot notice and query attachment chip are visible; current source remains readable; dock and document actions do not overlap. |
| [15-save-copy-dialog.png](screenshots/15-save-copy-dialog.png) | 1440 × 1000 | `869542ea4cc2` | Centered review dialog has readable destination/effects, visible name focus ring, and separated Cancel/Create controls. |
| [16-assistant-sql-proposal.png](screenshots/16-assistant-sql-proposal.png) | 1440 × 1000 | `6a72281d1fda` | One completed SQL proposal appears with Ready state; Open as query has contrasting light text on a dark code header; code remains horizontally scrollable. |
| [17-promoted-sql-draft.png](screenshots/17-promoted-sql-draft.png) | 1440 × 1000 | `24a2633be71b` | Private draft opens in the shared tabs with proposed SQL and empty results; completed assistant proposal remains visible; no automatic run is represented. |
| [18-save-response-lost.png](screenshots/18-save-response-lost.png) | 1440 × 1000 | `1e0e0921540e` | Lost-response explanation wraps within the dialog; original destination remains visible and frozen; Check again clearly recovers the existing request. |

## Review limits

No further visible overlap, clipping of primary controls, theme mismatch or unintended page-wide horizontal overflow was found in these final captures. A static screenshot cannot prove all focus interactions, assistive-technology behavior, contrast ratios or transient states. Browser overflow checks cover five widths; retained screenshots show 1440px light/dark, 375px phone and 768px tablet. 200% zoom, forced colors, a full keyboard-only journey and screen-reader qualification remain in [T16](../11-test-e2e-plan.md). No claim of universal visual perfection or complete R1 qualification is made.

## Compatible deployment baseline review

All 18 local screenshots were recaptured from the compatible `345d182` build and individually reopened for inspection. The current main application’s Data navigator, version badge, saved-session model and assistant behavior are preserved. The per-image observations above still apply. The later transport-only gzip correction changes no layout; live deployed screenshots are recorded separately after final deployment.

## Versioned dev deployment review

All four live screenshots below were opened individually after the final `v1.2.0-rc.1` deployment (`8e9e520`). The initial live review found misleading “demo history” and internal persistence wording. A tested two-file wording correction was deployed, then all four screenshots were recaptured and reopened. No further SQL control overlap, primary-action clipping, theme mismatch or page-wide overflow was found in the final captures. The existing mobile assistant footer wraps its workspace path; screen-reader and zoom qualification remain outside this review.

[Live report](deployed-report.json) · [Live hashes and dimensions](deployed-screenshots-manifest.json) · [Release review](version-release-review.md)

| Screenshot | Pixels | SHA-256 prefix | Visual review |
|---|---|---|---|
| [19-deployed-query-library.png](screenshots/19-deployed-query-library.png) | 1440 × 1000 | `4dd9062d9864` | Version badge states v1.2.0-rc.1; native empty library, search, filters and New SQL query actions align clearly; existing sessions and assistant remain visible. |
| [20-deployed-private-draft.png](screenshots/20-deployed-private-draft.png) | 1440 × 1000 | `cd3b5971f224` | Native stopped warehouse is visible; draft identity, disabled create/run controls and temporary-storage disclosure are accurate; editor, results and assistant do not overlap. |
| [21-deployed-mobile-draft.png](screenshots/21-deployed-mobile-draft.png) | 375 × 900 | `895a622a9cd1` | 375px layout wraps actions and capability disclosure cleanly; SQL editor, warehouse selector and composer remain accessible without page-wide horizontal overflow. Existing shell intentionally hides the version badge at this width. |
| [22-deployed-dark-draft.png](screenshots/22-deployed-dark-draft.png) | 1440 × 1000 | `1e100efda3f3` | Dark shell, editor and fields agree; v1.2.0-rc.1 badge and temporary-storage disclosure are legible; primary controls and source/results boundaries remain clear. |

## SQL-enabled rc.2 deployment review

All eleven new screenshots below were opened individually and inspected from exact source `fe4e110` (`v1.2.0-rc.2`). Images 23–32 show the native execution deployment; image 33 shows recovery after a second deployment of the same source. The mobile Results selector was corrected to accept its success checkmark; remaining functional assertions were repeated without resubmitting SQL. No further primary-control overlap, SQL layout clipping, inconsistent theme or unintended horizontal page overflow was found. Existing broader accessibility limits still apply.

[Native execution/restart report](deployed-report.json) · [Current image hashes](deployed-screenshots-manifest.json) · [Release scope](../15-sql-enabled-release.md)

| Screenshot | Pixels | SHA-256 prefix | Visual review |
|---|---|---|---|
| [23-sql-enabled-library.png](screenshots/23-sql-enabled-library.png) | 1440 × 1000 | `511faeca4bca` | Version v1.2.0-rc.2 is visible; library layout and existing navigator/assistant remain aligned. |
| [24-sql-enabled-draft.png](screenshots/24-sql-enabled-draft.png) | 1440 × 1000 | `d7d26f791bb4` | Run is enabled on a stopped native warehouse; neutral warehouse dot, Starts on demand hint and encrypted-history label are clear; create remains disabled. |
| [25-sql-enabled-mobile.png](screenshots/25-sql-enabled-mobile.png) | 375 × 900 | `64d8fe4cad62` | 375px editor keeps Run, warehouse selector and on-demand hint visible; source and composer fit without horizontal page overflow. |
| [26-sql-enabled-dark.png](screenshots/26-sql-enabled-dark.png) | 1440 × 1000 | `4b80244ce137` | Enabled Run action has clear dark-theme contrast; warehouse state and editor surfaces agree with the shell. |
| [27-native-on-demand-submitted.png](screenshots/27-native-on-demand-submitted.png) | 1440 × 1000 | `1bc60ce78342` | Native pending state shows Waiting for warehouse and cancel actions; source remains readable and Run is disabled during the active attempt. |
| [28-native-query-result.png](screenshots/28-native-query-result.png) | 1440 × 1000 | `1495b8dbe997` | Native serverless result is one INT value 1; warehouse now shows running; success and bounded preview are legible. |
| [29-native-parameters-null.png](screenshots/29-native-parameters-null.png) | 1440 × 1000 | `b184170c564e` | Named region binding is distinct from SQL text; native Europe and NULL cells render clearly with correct column labels. |
| [30-native-cancel-terminal.png](screenshots/30-native-cancel-terminal.png) | 1440 × 1000 | `a600e602a744` | Native cancellation reached Canceled; no result rows are fabricated; Run is available again. |
| [31-native-mobile-results.png](screenshots/31-native-mobile-results.png) | 375 × 900 | `45bccba49853` | 375px Results tab shows its success checkmark, native value 1, count and copy control without clipping. |
| [32-native-own-history.png](screenshots/32-native-own-history.png) | 1440 × 1000 | `0feb6b0deab2` | Four durable own-history entries show aligned success/canceled states and separate Open snapshot actions. |
| [33-native-server-restart-recovery.png](screenshots/33-native-server-restart-recovery.png) | 1440 × 1000 | `5cbe247544b2` | After actual server replacement, the recovered draft, native result 1 and encrypted-history label remain visible; no submit request was sent. |

The 18 local images and four rc.1 deployed images remain unchanged, individually reviewed historical evidence. Their provenance is explicit in the local manifest and archived rc.1 manifest. All 33 retained screenshot files have now been individually inspected.

## AI query integration rc.3 review

All nine final viewport captures below were individually opened and inspected from `7f104c7`. The review loop corrected buffered test EventSource delivery, result-locator ambiguity, misleading constraint evidence and pending-submission evidence after native completion. The final run rechecked all four actual-model missions. Screenshots capture the viewport because editor/chat scroll independently; this avoids unrelated blank full-page extensions. No SQL primary-control overlap, recovery-button clipping or page-wide horizontal overflow was found in the final captures. Informational analysis is not presented as verified execution. Broader accessibility and arbitrary-model semantic accuracy remain unqualified.

[Actual-model report](agent-report.json) · [Image hashes](agent-screenshots-manifest.json) · [Assessment](../16-ai-query-integration.md)

| Screenshot | Pixels | SHA-256 prefix | Individual visual review |
|---|---|---|---|
| [34-agent-query-working.png](screenshots/34-agent-query-working.png) | 1440 × 1000 | `80449a9a10be` | Accepted synthetic query mission is visible beside the unchanged starting draft; connecting/queued state remains explicit and does not imply execution. |
| [35-agent-query-verified-results.png](screenshots/35-agent-query-verified-results.png) | 1440 × 1000 | `6c3d2891813c` | Agent SQL replaces SELECT 1 in the open editor; native Agent verified/42 result and all four receipt-backed evidence rows agree; primary controls remain clear. |
| [36-agent-query-reload.png](screenshots/36-agent-query-reload.png) | 1440 × 1000 | `c84b62539280` | Reload retains the changed draft and same successful native result; the new conversation affordance is separate from recovered SQL history. |
| [37-agent-human-conflict.png](screenshots/37-agent-human-conflict.png) | 1440 × 1000 | `90bb12796988` | Human local SQL stays in the editor while a separate expanded agent version is reviewable; use/keep/copy actions are clear and Run is disabled. |
| [38-agent-human-conflict-dark.png](screenshots/38-agent-human-conflict-dark.png) | 1440 × 1000 | `30d15826f221` | Dark conflict screen preserves readable source, review text and distinct recovery controls using existing theme colors. |
| [39-agent-human-conflict-mobile.png](screenshots/39-agent-human-conflict-mobile.png) | 375 × 1000 | `53bbf5ba07e9` | At 375px the human and remote SQL remain visible; recovery buttons wrap cleanly, Run stays disabled, and no page-wide overflow appears. |
| [40-agent-human-kept.png](screenshots/40-agent-human-kept.png) | 1440 × 1000 | `d59b82775b0b` | Keep my SQL restores the enabled Run action and preserves the human text; the completed agent change remains accurately described in chat. |
| [41-agent-explanation-only.png](screenshots/41-agent-explanation-only.png) | 1440 × 1000 | `6fee91adc146` | Injected comment remains source text; assistant explains the scalar one-row grain without running or editing. The analysis row is explicitly unverified; the actual source read is verified. |
| [42-agent-schema-grounded-taxi-query.png](screenshots/42-agent-schema-grounded-taxi-query.png) | 1440 × 1100 | `88f5bae22360` | Schema-grounded trip_distance/fare_amount query shows LIMIT 5, all five real native rows and all five verified action-evidence rows; 1100px screen capture includes result footer without blank full-page extension. |

All 42 retained numbered screenshot files have individual review records: 18 local, four rc.1, eleven rc.2 and nine rc.3. Historical images retain their original revision provenance.

## CTE policy correction rc.4 review

All seven final captures below were individually opened and inspected from exact source `717c621`. The fix changes the shared backend policy and diagnostic; existing editor, result and theme components are reused. The exact original source ran on a new draft, returning 60 native daily rows from STOPPED. The actual configured AI model also authored and executed the CTE with matching source receipts. Phone horizontal panning reached the last result column without another submission. No primary SQL control overlap or page-wide horizontal overflow was found. The original user draft remained unchanged. Broader accessibility qualification remains separate.

[CTE report](cte-report.json) · [Image manifest](cte-screenshots-manifest.json) · [First-principles explanation](../17-cte-policy-correction.md)

| Screenshot | Pixels | SHA-256 prefix | Individual visual review |
|---|---|---|---|
| [43-cte-native-submitted.png](screenshots/43-cte-native-submitted.png) | 1920 × 1100 | `84dcbfcde598` | Exact original SQL is visible in a new private test draft. The stopped warehouse is selectable, native waiting state and cancel actions are clear; no generic policy refusal remains. |
| [44-cte-native-daily-results.png](screenshots/44-cte-native-daily-results.png) | 1920 × 1100 | `58fa98e619e0` | Native success shows 60 rows with pickup date, trip count and three averages. All five result columns align in the desktop viewport; source and result remain visible together. |
| [45-cte-native-dark.png](screenshots/45-cte-native-dark.png) | 1920 × 1100 | `372bd756029d` | Dark editor and result table preserve readable date/time SQL, all five result headers and the native success/count labels using existing theme tokens. |
| [46-cte-actionable-function-refusal.png](screenshots/46-cte-actionable-function-refusal.png) | 1920 × 1100 | `7f0ae9160573` | Unknown function receives a specific policy error; earlier successful results remain explicitly labeled as belonging to the previous source snapshot. No new run was created. |
| [47-cte-recovered-source-and-result.png](screenshots/47-cte-recovered-source-and-result.png) | 1920 × 1100 | `aeec8716cde2` | Restored exact CTE source and the same 60-row native result survive reload; no duplicate execution was submitted. |
| [48-agent-cte-native-results.png](screenshots/48-agent-cte-native-results.png) | 1920 × 1100 | `9d39df023f39` | Actual model-written CTE includes AND and unix_timestamp. The editor displays the executed revision, 60 native daily rows and seven verified evidence rows in the assistant. |
| [49-cte-mobile-results.png](screenshots/49-cte-mobile-results.png) | 375 × 1000 | `72083f0c84eb` | Phone Results view shows native success, 60 rows and leading result columns without page-wide overflow. Horizontal panning to the final duration column was separately verified without resubmission. |

All 49 retained numbered screenshot files have individual review records. Historical local/rc.1/rc.2/rc.3 images retain their original source provenance.

## Merged main deployment review

All seven new SQL screenshots 50–56 were opened individually after deployment of merged main `d2d4754`. Earlier images 01–49 were preserved. No further SQL control overlap, result-header alignment issue, inconsistent theme or page-wide phone overflow was found in these captures. This visual review does not establish defect-free behavior or replace the remaining acceptance gates.

[PR #17](https://github.com/raphaelmansuy/opengenie/pull/17) · [Live report](merge-report.json) · [Review manifest](merge-screenshots-manifest.json) · [Merge/deploy outcome](../18-main-merge-deployment.md)

| Image | Observation |
|---|---|
| [50-cte-native-submitted.png](screenshots/50-cte-native-submitted.png) | Native submission from the exact reported CTE shows Waiting for warehouse, cancel actions and the stopped serverless warehouse with Starts on demand. Source and actions are readable without overlap. |
| [51-cte-native-daily-results.png](screenshots/51-cte-native-daily-results.png) | Native success shows 60 daily rows and all five result columns alongside the exact source. Warehouse now reports running; no policy refusal is present. |
| [52-cte-native-dark.png](screenshots/52-cte-native-dark.png) | Dark-theme source, SQL highlighting, native success and all five result headers remain readable and aligned. |
| [53-cte-actionable-function-refusal.png](screenshots/53-cte-actionable-function-refusal.png) | The unknown-function refusal names the restriction, and the prior successful results are explicitly marked as belonging to the previous snapshot. Controls remain available. |
| [54-cte-recovered-source-and-result.png](screenshots/54-cte-recovered-source-and-result.png) | Reload restores the exact CTE source and the same 60-row result. The machine assertion verifies no repeated submission. |
| [55-agent-cte-native-results.png](screenshots/55-agent-cte-native-results.png) | The real AI mission is completed: the updated CTE appears in the editor, native results show 60 rows, and the assistant reports seven proven evidence rows. Source, results and assistant remain visible. |
| [56-cte-mobile-results.png](screenshots/56-cte-mobile-results.png) | The 375px Results view shows success, row count and leading columns without page-wide overflow. The harness separately verifies horizontal panning to the last column without another submission. |
