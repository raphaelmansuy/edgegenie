# Interaction and visual design

Contracts: [TM-01–10](01-requirements.md). Mechanisms: [03 Architecture](03-architecture.md). Verification: [05 Matrix](05-test-matrix.md).

## Wireframes

Wide editor; controls occupy their own area and never overlay a tab close target:

```ascii
+----------------------------------------------------------------------------+
| [N revenue.py x] [F config.yml x] [T orders x]         [<] [>] [...] [3 v] |
+----------------------------------------------------------------------------+
| revenue.py     PYTHON                Ask v     Save                        |
|                                                                            |
| Document surface                                                           |
+----------------------------------------------------------------------------+
```

Overflow; labels keep width, the scrollbar remains draggable:

```ascii
+---------------------------------------------------------------------------------+
| ...[F databricks.yml x] [F package.json x] [F pyproject... [<] [>] [...] [+8 v] |
| ==================                                                              |
+---------------------------------------------------------------------------------+
| Document surface                                                                |
+---------------------------------------------------------------------------------+
```

Drag reorder; source stays in place until commit, marker previews destination:

```ascii
+-----------------------------------------------------------------------------+
| [A.py x] [B.py x] | [C.py x]                              [<] [>] [...] [v] |
| dragging C --+                                                              |
+-----------------------------------------------------------------------------+
| Escape cancels. Release outside the strip cancels.                          |
+-----------------------------------------------------------------------------+
```

Picker is anchored to the right, clamped to the viewport, independently scrollable:

```ascii
+---------------------------------------------------+
| Open documents                              12    |
| [Search open documents_______________________]    |
| > revenue.py          /Shared/analytics           |
| revenue.py          /Shared/experiments           |
| config.yml          /Repos/demo                   |
|                                                   |
| Drag tabs to reorder. Alt+Shift+Arrow also moves. |
+---------------------------------------------------+
```

## Navigation

| Input | Result |
|---|---|
| Click / Enter / Space | Activate document through App selection and binding |
| Left / Right / Home / End | Activate and focus tab; wrap Left/Right |
| Alt+Shift+Left / Right | Move focused tab one position, preserving active ID |
| Right-click / Shift+F10 | Tab actions menu; move, close, bulk close, reopen |
| Delete / Backspace / primary-modifier+W | Close current document; adjacent selection and focus |
| Middle click | Close targeted document without activating it first |
| Primary-modifier+Shift+T | Reopen last closed document at its former index |
| Wheel / Shift-wheel / horizontal trackpad | Scroll just the strip; no auto-reveal until next activation/resize |
| Drag near strip edge | Time-based continuous autoscroll, bounded by actual scroll extent |
| Escape / pointer cancel / outside release | Cancel reorder without committing |
| Open documents button | Search name/path; ArrowDown enters results; Escape restores trigger focus |

The visible **Tab actions** button opens actions for the active document (or the first document on Home), so touch and pointer users never need a drag gesture or right click.

Touch: swipe strip to scroll; hold a tab briefly before moving to reorder. Menu Move left/right also provides a tap-only alternative. The close control is excluded from drag initiation. Partial edge tabs are expected while manually scrolling; activation fully reveals the selected tab. A very narrow viewport can show a truncated tab and still retain fixed controls. Native browser external-file drops are not tab moves.

Use semantic theme tokens; no hardcoded light-only surfaces. Tab minimum hit height 34px; controls >=28px desktop and 36px coarse pointer. Reduced motion disables smooth movement. Focus outline must not be mistaken for selection. Icons distinguish notebook, file and table; dirty dot has an accessible text equivalent and is distinct from the close control.
