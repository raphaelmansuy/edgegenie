# UX, UI and navigation

[Product outcomes](01-product.md) → [API](04-persistence-api.md) → this interaction design → [visual evidence](e2e/README.md).

## Navigation and screen wireframes

The existing Conversations rail is the mission index. It gains All / Running / Needs attention filters and explicit state text per row. Selecting a conversation uses the existing `#/session/<id>` deep link and existing transcript renderer. No competing mission application or duplicate composer is introduced.

```ascii
+--------------------------------------------------------------------------------------------------+
| OpenGenie    Conversations / Notebook / Assistant                                                |
|                                                                                                  |
| CONVERSATIONS             WORKSPACE                 ASSISTANT                                    |
| [All] [Running] [Needs attention]                                                                |
| Revenue review            Open notebook             Working on the server                        |
|   Running                                           You can close this tab.                      |
| Pipeline repair                                     Progress saved                               |
|   Needs approval                                    [Copy return link] [Stop work]               |
| Yesterday                                                                                        |
| Quality checks                                      Tool calls and saved progress                |
|   Completed                                         appear in the conversation.                  |
|                                                                                                  |
|                                                     [Ask a follow-up...]                         |
+--------------------------------------------------------------------------------------------------+
```

A server restart is different from losing browser connectivity. The recovery banner explains saved progress and offers a concrete restore operation without promising automatic execution of the interrupted prompt.

```ascii
+----------------------------------------------------------------------------+
| ASSISTANT / Revenue review                                                 |
|                                                                            |
| Your progress is saved                                                     |
| Restore the agent, then review progress before continuing.                 |
| Unfinished actions were not repeated.                                      |
| Progress saved       [Copy return link] [Restore agent]                    |
|                                                                            |
| Earlier prompt, partial answer and tool evidence                           |
| Interrupted: server restarted                                              |
|                                                                            |
| [Composer disabled until the agent is restored]                            |
+----------------------------------------------------------------------------+
```

At narrow widths the existing assistant drawer remains user controlled. The same status component is also available in the full conversation when the dock is hidden. Actions wrap instead of truncating their labels.

```ascii
+--------------------------------------+
| < Conversations        OpenGenie     |
|                                      |
| Revenue review                       |
| Working on the server                |
| You can close this tab.              |
| Return here to review progress.      |
|                                      |
| PROGRESS SAVED                       |
| [Copy return link]  [Stop work]      |
|                                      |
| Tool results / answer                |
|                                      |
| [Ask a follow-up...]                 |
+--------------------------------------+
```

## State copy and behavior

| Situation | Heading | Action / implication |
|---|---|---|
| Live turn | Working on the server | Copy return link; Stop work; closing tab is allowed |
| Supervisor verification | Checking the work | Evidence remains in the same transcript |
| Pending permission | Waiting for your decision | Inline offered decisions; no automatic approval |
| Offline | You’re offline | Explain independent execution; disable server mutation controls |
| Stream retry | Reconnecting to your session | Catch up on saved progress; do not claim a fresh execution status |
| Restart / unloaded agent | Your progress is saved | Restore agent, then review before continuing |
| Completed | Ready for your review | Show actual answer/tool evidence; no invented success percentage |
| User stopped | Work stopped | Explain stopped queue; completed changes remain |
| Volatile demo | Temporary history | Explicitly says history lasts until the server restarts |

## Visual and interaction rules

Reuse existing semantic ink, border, blue and surface tokens in both themes. A small geometric state mark accompanies words; color never carries state alone. The banner is outside the scrolling dock transcript so it remains visible without covering code. Dense typography follows the existing shell. Buttons preserve their size across hover/focus; no pulsing animation is necessary.

One atomic status announcement explains state changes. Keyboard focus stays on the user's control; restore and clipboard failures remain inline, actionable and readable. Copy return link points to the application conversation, not a provider or Databricks URL containing credentials. The same account is required to reopen it. Server mutations are disabled while offline; explicit pending feedback and errors accompany restore.

No permission is inferred from reconnecting, returning focus, opening a deep link or pressing Escape. Existing inline approval controls are retained, with offered option kinds validated server-side. History polling is visibility-aware and does not refetch the full model catalogue. See [edge cases](07-edge-cases-tests.md) and the [inspection log](e2e/README.md) for tested widths and themes.
