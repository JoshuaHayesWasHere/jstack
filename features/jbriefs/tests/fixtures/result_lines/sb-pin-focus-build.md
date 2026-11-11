# sb-pin-focus-build: a clicked hover pin hands focus back to its row, so the tree's arrow keys keep working
Green main: 2ee0b300117f8b090692af1807b46619ea68b386
Stacked on: main at 2ee0b300117f8b090692af1807b46619ea68b386
Task: finding F1 of #786's review (sb-pin-crew-build, left as a Consider): clicking the hover pin leaves focus on the pin button, which sits outside the row's [data-sidebar-row] and carries no data-sidebar-action-for, so the tree's key handler (lib/sidebarTree.ts onKeyDown, which returns unless the target is a row) ignores ArrowUp, ArrowDown and the rest until Tab or a click puts focus back on a row. The user's word 74ea1a77baa0: "Go everything don't wait on me"
Done when:
- after a click on a row's hover pin (pin or unpin), focus is on that row, and ArrowUp, ArrowDown and the tree's other keys act at once
- the root chevron, which follows the same pointer-only pattern, gets the same fix if it has the same gap
- a browser test clicks the hover pin, then presses ArrowDown and finds the next row focused; the existing pin tests and the axe check still pass
- the fork's checks pass (`env -u ELECTRON_RUN_AS_NODE vp run check:changed`) in a fresh fork worktree with every patch of main's `features/t3code-jstack/packaging/` applied, plus this commit
- the patch series on main carries it as its own numbered patch (0021), named in `_patches` with one more `'SKIP'` in `sha256sums`, `pkgver` names the series, and every patch applies to a clean `git archive` of tag `v0.1.5-nightly.20261029.3877`
- the check command (`$H/fresh-check`) passes
Proves it: the browser test pressing a key after a pin click, and the patch series applying to a clean archive of the tag
Size: S
Where: `features/t3code-jstack/packaging/` on main; in the fork `apps/web/src/components/sidebar/JstackTreeRows.tsx` (the hover pin and the root chevron) and `apps/web/src/lib/sidebarTree.ts` (onKeyDown)
Do not touch: `~/.t3/userdata`, `VITE_HTTP_URL`/`VITE_WS_URL`, the live jbus and home state, T3's own thread pins; never kill processes by pattern
Decisions: the user's word 74ea1a77baa0, 2026-10-29 21:57 EDT
Skills: none
Pull request: open one when done
Review: once
Playbook: feature
Home: sidebar
Thread: mcp:thread-7

## Result
Status: not done
Done when: every line holds but the pull request, which is not opened: the brief's base is not one the crew can read
- focus on the row after a hover pin click, pin or unpin, and the tree's keys act at once: holds
- the root chevron, same gap, same fix: holds
- a browser test clicks the pin, presses ArrowDown and finds the next row focused; existing pin tests and axe still pass: holds
- the fork's checks in a fresh fork worktree with every patch plus this commit: holds
- patch 0021 named in `_patches`, one more `'SKIP'`, `pkgver` names the series, every patch applies to a clean archive of the tag: holds
- `$H/fresh-check` passes: holds
Proof:
- red first: in fresh fork worktree ~/repos/t3code-wt/sb-pin-focus-build (tag v0.1.5-nightly.20261029.3877 plus 0001-0020 by `git am`), the two new tests failed at `toHaveFocus()` before the fix
- the browser tests: `vp test run --project browser src/components/sidebar/JstackTreeRows.browser.test.tsx` after the fix, 33 passed of 33, the axe checks and the three existing pin tests among them; "hands focus to the home's row once its pin is clicked" pins ops by its pin, finds ops focused, ArrowDown to ops-trim, ArrowUp back, unpins by the pin, ArrowDown to jview; "hands focus to the root's row once its chevron is clicked" clicks Fold jstack, finds the root focused, ArrowDown to tidy
- the fork's checks: `env -u ELECTRON_RUN_AS_NODE vp run check:changed` at fork commit a34c25a55a, every step pass (format, lint, knip, typecheck, test 28 files, react compiler)
- the series: all 21 patches applied with `patch -p1 --forward` to `git archive v0.1.5-nightly.20261029.3877`, no reject, and `diff -r` of apps/web/src against the fork commit is empty; `pkgver` is `.jstack.d3342fb3b6`, the sha256 of the patches in name order, and `sha256sums` has 22 `'SKIP'`
- the check: `make check-fast` with 49 selected test files, exit 0, 3702 passed
Branch: sb-pin-focus-build   Pull request: none
Changed: new patch `0021-jstack-tree-pin-focus.patch`: the hover pin and the root chevron each focus their row once clicked (`focusTreeRowSoon(row.key)`), with two browser tests; PKGBUILD names it, one more SKIP, series d3342fb3b6. lib/sidebarTree.ts unchanged: the fix stays at the two pointer-only buttons, not in T3's tree handler.
Playbook: features/crew/playbooks/feature.md; 1 done; 2 done: the row stays the one focus owner, a pointer-only button hands focus back to it; 3 done: per-button focusTreeRowSoon picked over teaching sidebarTree.ts onKeyDown to redirect keys from linked controls, which would change T3's own tree for every row control; 4 skip: size S; 5 done; 6 done; 7 done; 8 done; 9 skip: the base check printed no base, so no pull request is opened
Skills run: none
Steers: none
Left: the pull request: the base block printed "no base: the brief's Stacked on: line is not Stacked on: <slug> <branch>, and only jbus writes it" for the line `Stacked on: main at 2ee0b300117f8b090692af1807b46619ea68b386`; the branch is pushed and ready to open on main once the home gives the base

## Result, follow-up (2026-10-30, the home gave the base: main)
Status: done
Done when: every line holds
Proof:
- as the Result above: the two new browser tests red at `toHaveFocus()` before the fix, 33 of 33 after; fork `vp run check:changed` passed; all 21 patches apply to `git archive v0.1.5-nightly.20261029.3877` and match the fork commit; `make check-fast` exit 0, 3702 passed
- the base: origin/main had not moved from 2ee0b300117f8b090692af1807b46619ea68b386, so no rebase; the borders check passed with no label
Branch: sb-pin-focus-build   Pull request: https://github.com/JoshuaHayesWasHere/jstack/pull/787
Changed: new patch `0021-jstack-tree-pin-focus.patch`: the hover pin and the root chevron each focus their row once clicked; PKGBUILD names it, one more SKIP, series d3342fb3b6
Playbook: features/crew/playbooks/feature.md; 1 done; 2 done; 3 done: per-button focusTreeRowSoon over a redirect in sidebarTree.ts onKeyDown; 4 skip: size S; 5 done; 6 done; 7 done; 8 done; 9 done
Skills run: none
Steers: the sidebar home gave the base as main, and said the brief's Stacked on: line was its own and wrong in form
Left: none
Reviewer: mcp:thread-4 #1

## Review
By: claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: clean
Head: 8e4adee9dba3a8f173758c25341e4bcb7152b7a5   Unchanged by the review: yes
Patch-id: c4a2537880bbb4d5e1adda357fa9e1f2bcb3b023
Reviewers: 1, 0   Proof: sh /tmp/pr-review-sb-pin-focus-build.JJAp96/proof.sh (applies patches 0001-0021 to git archive of v0.1.5-nightly.20261029.3877, checks focusTreeRowSoon is defined once and called with row.key at the two new sites, diffs apps/web/src against the fork commit, checks pkgver is the series sha d3342fb3b6 and 22 SKIP), exit 0, pkgver names the series, 22 SKIP
Meets the brief: yes
In flight: none
Findings:
- none
Dropped: 0
Noted: 0
Dismissed: 0
Sent to: not sent, jbus tells the crew when it owes a line
