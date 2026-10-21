# jmerge says ready, wait or hold

`jmerge` prints one line for each open pull request: `ready` when it is reviewed, fixed and green, `wait` with the reason when it is short of that, and `hold` when it touches a path only the user merges. With `--check` it prints the decision and merges nothing. `jmerge --claims` prints the files each brief still out holds.

Paths:
- `src/jmerge/`
- `features/jsettings/`
- `docs/jmerge.md`
Tests: none

## Sub-features

- `decision-no-review` waits on a green pull request whose brief has no review.
- `decision-ready` is ready at the head a clean review names.
- `decision-hold` holds a pull request that changes a protected path, for the user.
- `decision-gate` holds a ready pull request whose repo's merge gate fails, prints the gate's output under the line, and merges nothing.
- `decision-review-after` is ready on green alone when the brief says `Review: after`, before and after its review lands.
- `decision-review-twice` waits for the second review of a `Review: twice` brief, is ready once it is written whatever it found, and `jbus cleanup` files its `warning` finding as a queue row.
- `decision-red` waits while the check named `check` has not passed.
- `decision-tool-follows` reinstalls the tool after a merge that changes pyproject.toml's package list, and says so on the `merged` line (not reachable from a sandbox: the stand-in `gh` refuses a merge, and `tests/test_home_merge.py` drives it).
- `decision-install-follows` runs `sh install.sh` in the main checkout after a merge that changes what the install assembles (`skills.json`, a skill's files), where the machine's layouts were assembled from that checkout, and says so on the `merged` line, or says loudly that it failed (not reachable from a sandbox: the stand-in `gh` refuses a merge, and `tests/test_jmerge_follow.py` drives it; `install-skills.md` drives the install it runs).
- `decision-claims` lists the briefs that still hold files.
- `decision-check-merges-nothing` asks GitHub and merges nothing.

## How to get to it (user POV)

- Run `jmerge --check` in the repo's main checkout.
- Run `jmerge --claims` there.
- Run `jmerge` there to merge what is ready (not reachable from a sandbox: the stand-in `gh` refuses a merge).
- Read the `jmerge` and `gate` lines a `jbus poll` sends, which runs `jmerge` where the repo's home is off.

## Driving it with verify-jstack

Needs: `demo`, `tasks`, `gh/open.json`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- The shell is in `$VERIFY_JSTACK_SANDBOX/demo`, and `gh/open.json` is `[]`.

- **Open a pull request.** Run `head=$("$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py)`. `gh/open.json` has pull request 7 on the branch `beta`, green, changing `src/beta/a.py`.
- **Write its brief.** Run `printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n' > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`. The brief has a Result and no review.
- **Ask, unreviewed.** Run `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: it has no review yet`.
- **Add a clean review.** Run `printf '## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `ready 7 <the head> beta beta`.
- **Review after.** Run `printf '## Review\nVerdict: findings\nHead: %s\nFindings:\n- warning src/beta/a.py:1 a made up one (bucket: Act on)\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: its findings are not handled: the Result has no Fixed line`. Then run `sed -i 's/^Pull request: open one when done$/&\nReview: after/' "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jmerge --check` again. It prints `ready 7 <the head> beta beta`: an `after` brief's findings hold nothing.
- **Review twice.** Run `printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\nReview: twice\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\nReviewer: mcp:9 #1\nFinding F1: fixed, a made up one\nFixed: %s\nSecond reviewer: mcp:10 #1\n\n## Review\nBy: demo #1\nVerdict: findings\nHead: %s\nFindings:\n- warning src/beta/a.py:1 a made up one (bucket: Act on)\n' "$head" "$(printf f%.0s $(seq 40))" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: its second review is not written at <the head's first 12>`. Then run `printf '\n## Review\nBy: demo #1\nVerdict: findings\nHead: %s\nFindings:\n- warning src/beta/a.py:2 a second one (bucket: Act on)\n- info src/beta/a.py:3 a small one (bucket: Consider)\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jmerge --check` again. It prints `ready 7 <the head> beta beta`: the second review's findings hold nothing. Then run `record jmerge-decision sh -c 'jbus cleanup "$1" | jbus --project demo queue add cleanup-beta --priority 50' cleanup "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jbus --project demo queue show`. The queue has the row `cleanup-beta`, not approved, and its brief in `state/demo/briefs/cleanup-beta.md` names `src/beta/a.py:2` and not `src/beta/a.py:3` or `src/beta/a.py:1`.
- **Touch a protected path.** Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta secrets/a.key`, then `record jmerge-decision jmerge --check`. It prints `hold 7 https://example.test/pull/7: needs user, touches secrets/a.key`.
- **Fail the check.** Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py FAILURE`, then `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: check has not passed`.
- **Fail the merge gate.** The gate runs in a checkout of the head, so this step gives the pull request a real one. Run `head=$(git commit-tree -p HEAD -m beta "$(git rev-parse 'HEAD^{tree}')") && git push -q origin "${head}:refs/heads/beta" && "$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py > /dev/null && jq --arg head "$head" '.[0].headRefOid = $head' "$VERIFY_JSTACK_SANDBOX/gh/open.json" > "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" && mv "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" "$VERIFY_JSTACK_SANDBOX/gh/open.json" && printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n\n## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `ready 7 <the head> beta beta`. Then run `printf '#!/bin/sh\necho "no passing receipt for $2 over $1"\nexit 1\n' > "$VERIFY_JSTACK_SANDBOX/gate.sh" && chmod +x "$VERIFY_JSTACK_SANDBOX/gate.sh" && echo "$VERIFY_JSTACK_SANDBOX/gate.sh" > "$VERIFY_JSTACK_SANDBOX/home/.local/state/home/demo/merge-gate"` and `record jmerge-decision jmerge --check`. It prints `hold 7 https://example.test/pull/7: its merge gate failed: no passing receipt for <the head> over <the commit start>`, and under it the same text after `  | `. Then run `rm "$VERIFY_JSTACK_SANDBOX/home/.local/state/home/demo/merge-gate"`.
- **List the claims.** Run `record jmerge-decision jmerge --claims`. It prints `beta pull request 7 root Where: `src/beta/``.
- **Check nothing merged.** Run `record jmerge-decision grep -c "pr merge" "$VERIFY_JSTACK_SANDBOX/gh/calls.log"`. It prints `0` (and exits 1, as `grep -c` does with no match). The demo checkout's `git log --oneline` still has the one commit `start`.
- **Proof.** Copy `gh/calls.log` and the brief into `$VERIFY_JSTACK_EVIDENCE`.

## Gotchas

- `jmerge` reads the briefs from `$HOME/.local/state/home/<the main checkout's directory name>`, not from `JBUS_HOME_DIR`. In a sandbox both are the same directory, because `env.sh` sets HOME.
- The recipe writes the brief through `${VERIFY_JSTACK_SANDBOX:?}`, so a shell that sourced no `env.sh` stops and writes nothing into the live briefs.
- The review's `Head:` must be the pull request's head commit, whole. `open-pull.sh` prints it.
- Only the check named `check` decides green. Another check's name in `statusCheckRollup` changes nothing.
- A plain `jmerge` on a ready pull request reaches `gh pr merge`, which the stand-in refuses with exit 64. That is the harness ending, not a jmerge failure, and it is not proof of a merge.
- Every line of `jmerge --check` exits 0, `wait` and `hold` included. Assert on the line, not the exit code.
- `jmerge` without `--check` appends each line to `merge.log` in the repo's state. `--check` writes nothing.
- `--check` runs no `fresh-check` command, but it does run the merge gate: the gate is how `--check` knows the pull request would be held.
