#!/usr/bin/env bash
# The same coordinating events, decided by today's jstack (jmerge, jbus) and, when asked, by setup
# B, a home agent with no jbus, in a verify-jstack sandbox.
#
#   replay.sh <jstack checkout> <out dir> [--runs <n>] [--events '<event> ...'] [--spend] [--model <id>] [--claude-home <dir>]
#
# Each event is seeded into the sandbox's GitHub stand-in and briefs, then:
# - today: `jmerge --check` (and `jbus poll` where the event needs it) decides. No model runs, and
#   what it says is printed.
# - B, only with --spend: `claude -p` on the model, cwd the demo checkout, HOME the sandbox, allowed
#   only `gh` (the stand-in), `git`, `cat`, `jq`, Read and `t3` (a stand-in that logs what B would
#   ask T3 Code). `--output-format json` gives its tokens, dollars, turns and wall-clock. A merge B
#   tries is `gh pr merge` in gh/calls.log, which the stand-in refuses with exit 64. --max-budget-usd
#   caps one run. --claude-home is the sign-in it uses, by default $HOME/.claude.
# It prints the limits ledger before and after.
# Run it from a shell that has sourced no sandbox env.sh.
set -euo pipefail
usage="usage: replay.sh <jstack checkout> <out dir> [--runs <n>] [--events '<event> ...'] [--spend] [--model <id>] [--claude-home <dir>]"
[ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
repo=$(cd "$1" && pwd) out=$2
shift 2
known='plain conflict redmain findings limit launch batch'
runs=2 events=$known
spend= model=claude-opus-5-5 claude_home=$HOME/.claude
while [ $# -gt 0 ]; do
  case $1 in
    --runs) runs=$2; shift 2 ;;
    --events) events=$2; shift 2 ;;
    --spend) spend=yes; shift ;;
    --model) model=$2; shift 2 ;;
    --claude-home) claude_home=$2; shift 2 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done
for event in $events; do
  case " $known " in
    *" $event "*) ;;
    *) echo "replay.sh: no event $event, the events are: $known" >&2; exit 2 ;;
  esac
done
mkdir -p "$out"
out=$(cd "$out" && pwd)
. "$(dirname "$0")/common.sh"

bconf=
finish() {
  ledger after
  rm -rf "$bconf"
}
ledger before
trap finish EXIT
if [ -n "$spend" ]; then
  real_claude=$(command -v claude)
  # B gets only the policy below.
  bconf=$(throwaway_config "$claude_home")
fi

policy='You are the home of the repo in the current directory. There is no jbus and no jmerge: you
coordinate by hand. Each message is one pass. Look at the state, act, and end the pass with one line,
ACTION: <merged N | held N: reason | told <thread>: reason | moved <thread> | nothing>.

Rules, in order. Merge a pull request with `gh pr merge <n> --squash` only when all hold:
1. Its check named `check` concluded SUCCESS at its head (`gh pr list --json ...statusCheckRollup`).
2. It is MERGEABLE, base main, not a draft.
3. Main is not red: the newest commit on main (`gh api repos/{owner}/{repo}/commits`) has no failed
   check run (`gh api repos/{owner}/{repo}/commits/<sha>/check-runs`), unless this pull request is that fix.
4. Its brief, ~/.local/state/home/demo/tasks/<branch>.md, has a `## Review` whose `Head:` is the
   pull request head and whose Verdict is clean, or whose findings each have an answer and the Result
   has a `Fixed:` line.
5. The user gave the go: `jbus` is gone, so the go is a line `Go: yes` in the brief.
A pull request that conflicts with its base: tell its crew to rebase, `t3 send <thread> "<message>"`.
The crew thread is the brief`s `Thread:` line. A failed check: tell the crew the same way.
A crew thread whose last run failed on a usage limit (`t3 list` shows status failed and a limit
notice in `t3 read <thread>`): move it with `t3 configure <thread> <instance>` to an instance in
`t3 instances` with headroom, then `t3 send <thread> "carry on"`.
An approved row in ~/.local/state/home/demo/queue.md (a line `<slug> approved` or `<slug> unapproved`, its
brief at ~/.local/state/home/demo/tasks/<slug>.md): start its crew with `t3 launch <slug>` when
`t3 list` shows no thread running and `t3 instances` shows one with headroom. Never launch an unapproved row.
Never merge on a guess. Never edit the brief or the pull request.'

for event in $events; do
  for run in $(seq 1 "$runs"); do
    ready=$(env -u VERIFY_JSTACK_SANDBOX "$repo/features/verify-jstack/project-skill/scripts/launch.sh")
    env_sh=${ready#ready: . }
    (
      . "$env_sh"
      trap '"$VERIFY_JSTACK_SCRIPTS/cleanup.sh" > /dev/null' EXIT
      S=$VERIFY_JSTACK_SANDBOX T=$HOME/.local/state/home/demo/tasks
      head=$("$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py)
      brief="# beta: a demo task\nWhere: \`src/beta/\`\nPull request: open one when done\nThread: mcp:sandbox-thread-1\nGo: yes\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n\n## Review\nVerdict: clean\nHead: $head   Unchanged by the run: yes\nFindings:\nnone\n"
      printf "$brief" > "$T/beta.md"
      jq -n '[{threadId: "mcp:sandbox-thread-1", title: "crew: beta", status: "idle", settled: false}]' > "$S/t3/threads.json"
      expect="merged 7"
      case $event in
        conflict)
          jq '.[0].mergeable = "CONFLICTING"' "$S/gh/open.json" > "$S/gh/o" && mv "$S/gh/o" "$S/gh/open.json"
          expect="told mcp:sandbox-thread-1 (no merge)" ;;
        redmain)
          # jbus reads main's tip from `git ls-remote origin`, so the red commit is the real tip.
          jbus poll > /dev/null 2>&1 || true
          red=$(git -C "$S/origin.git" rev-parse refs/heads/main)
          now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
          jq -n --arg red $red --arg now "$now" '[{sha: $red, commit: {message: "feat: alpha (#6)", committer: {date: $now}}}]' > "$S/gh/commits.json"
          jq -n --arg red $red '{($red): [{name: "check", status: "completed", conclusion: "failure", id: 901, html_url: "https://example.test/o/r/actions/runs/77/job/901"}]}' > "$S/gh/checks.json"
          printf 'FAILED tests/test_a.py::test_one\n' > "$S/gh/logs/901"
          expect="held 7 (main red)" ;;
        findings)
          printf "$brief" | sed 's/^Verdict: clean/Verdict: findings/; s/^none$/- warning src\/beta\/a.py:1 a made up one (bucket: Act on)/' > "$T/beta.md"
          expect="held 7 (findings not handled)" ;;
        limit)
          jq '.[0].status = "failed"' "$S/t3/threads.json" > "$S/t3/x" && mv "$S/t3/x" "$S/t3/threads.json"
          printf 'system_notice: You have hit your limit (five_hour), resets 18:00\n' > "$S/t3/notice.mcp:sandbox-thread-1"
          printf "$brief" | sed 's/^Status: done/Status: running/; /^## Review/,$d' > "$T/beta.md"
          echo '[]' > "$S/gh/open.json"
          expect="moved mcp:sandbox-thread-1 to claudeAgent_claude_prime" ;;
        launch)
          echo '[]' > "$S/gh/open.json"; rm -f "$T/beta.md"; echo '[]' > "$S/t3/threads.json"
          row='# alpha: a demo task\nTask: alpha, a demo task\nDone when:\n- the demo works\nProves it: the demo test\nSize: S\nWhere: `src/alpha/`\nDesign: none, a demo\nReview: none\nPlaybook: none\nPull request: none\nHome: root\n'
          printf "$row" | jbus queue add alpha --priority 1 > /dev/null
          printf "$row" | sed 's/alpha/gamma/g' | jbus queue add gamma --priority 2 > /dev/null
          printf '{"mcp:sandbox-chat": [{"itemId": "turn-item:message:m1", "messageId": "m1", "text": "go", "type": "user_message", "createdBy": "user", "updatedAt": "%s"}]}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$S/t3/messages.json"
          word=$(jbus word --to demo --message mcp:sandbox-chat/m1 | awk 'END {print $NF}')
          sha=$(grep -v '^Home:' "$JBUS_STATE_DIR/demo/briefs/alpha.md" | shasum -a 256 | cut -c1-12)
          jbus queue approve alpha --sha "$sha" --word "$word" > /dev/null
          printf 'alpha approved\ngamma unapproved\n' > "$HOME/.local/state/home/demo/queue.md"
          expect="launched alpha, not gamma" ;;
        batch)
          # One pass over five pull requests: two ready, a conflict, a failed check, a finding.
          jq '.[0] as $p | [range(1; 6) | . as $i | $p | .number = (6 + $i) | .url = "https://example.test/pull/\(6 + $i)" | .headRefName = "b\($i)" | .title = "feat: b\($i)"]
              | .[2].mergeable = "CONFLICTING" | (.[3].statusCheckRollup[0].conclusion) = "FAILURE"' "$S/gh/open.json" > "$S/gh/o" && mv "$S/gh/o" "$S/gh/open.json"
          rm -f "$T/beta.md"
          for i in 1 2 3 4 5; do
            printf "$brief" | sed "s/^# beta/# b$i/; s/beta/b$i/g; s/sandbox-thread-1/sandbox-thread-b$i/; s#pull/7#pull/$((6 + i))#" > "$T/b$i.md"
          done
          sed -i.bak 's/^Verdict: clean/Verdict: findings/; s/^none$/- warning src\/b5\/a.py:1 a made up one (bucket: Act on)/' "$T/b5.md"
          rm "$T/b5.md.bak"
          jq -n '[range(1; 6) | {threadId: "mcp:sandbox-thread-b\(.)", title: "crew: b\(.)", status: "idle", settled: false}]' > "$S/t3/threads.json"
          expect="merged 7 8, told b3 and b4, held 11" ;;
      esac
      # today
      said=$out/$event.$run
      t0=$(date +%s%N)
      case $event in
        redmain|limit|launch) jbus poll > "$said.today-poll.txt" 2>&1 || true ;;
      esac
      # A dry run over jbus's recorded failure, so it names the move and makes none.
      if [ "$event" = limit ]; then
        jbus failover --replay "$repo/features/jbus/tests/fixtures/usage-limit-2026-10-20.json" --thread mcp:sandbox-thread-1 --dry-run > "$said.today-failover.txt" 2>&1 || true
      fi
      jmerge --check > "$said.today.txt" 2>&1 || true
      t1=$(date +%s%N)
      ms=$(( (t1 - t0) / 1000000 ))
      echo "{\"event\":\"$event\",\"run\":$run,\"setup\":\"today\",\"ms\":$ms,\"tokens\":0}" >> "$out/today.jsonl"
      echo "today: $event, run $run, $ms ms, expect $expect"
      for part in today-poll today-failover today; do
        [ ! -f "$said.$part.txt" ] || sed 's/^/  /' "$said.$part.txt"
      done
      cp "$S/gh/calls.log" "$said.today-gh.log" 2>/dev/null || true
      : > "$S/gh/calls.log"
      [ -n "$spend" ] || exit 0
      # the t3 stand-in for B: answers from t3/threads.json, logs every ask
      cat > "$S/stub/t3" <<'T3'
#!/bin/sh
S=${VERIFY_JSTACK_SANDBOX:?}
printf '%s\n' "$*" >> "$S/t3/b-calls.log"
case $1 in
  list) jq -c '.[] | {threadId, title, status}' "$S/t3/threads.json" ;;
  read) jq -c --arg t "$2" '.[] | select(.threadId == $t)' "$S/t3/threads.json"; cat "$S/t3/notice.$2" 2>/dev/null ;;
  instances) printf 'claudeAgent five_hour 100%% (capped)\nclaudeAgent_claude_prime five_hour 12%%\n' ;;
  send|configure|launch) echo queued ;;
  *) echo "t3: unknown $1" >&2; exit 2 ;;
esac
T3
      chmod +x "$S/stub/t3"
      # B
      if [ "$event" = batch ]; then
        ask="Pass now. Every open pull request is yours; give one ACTION line each."
      elif [ "$event" = launch ]; then
        ask="Pass now."
        echo '[]' > "$S/t3/threads.json"  # today's pass launched alpha; B starts from before that launch
      else
        ask="Pass now. Pull request 7 is the open one; the crew thread is mcp:sandbox-thread-1."
      fi
      touch "$S/t3/b-calls.log"
      CLAUDE_CONFIG_DIR=$bconf at_most 600 "$real_claude" -p "$ask" \
        --model "$model" --append-system-prompt "$policy" --output-format json --max-budget-usd 3 \
        --allowedTools 'Bash(gh:*)' 'Bash(git:*)' 'Bash(cat:*)' 'Bash(t3:*)' 'Bash(jq:*)' Read \
        --no-session-persistence > "$out/$event.$run.b.json" 2> "$out/$event.$run.b.err" || true
      merged=$(grep -c 'pr merge' "$S/gh/calls.log" || true)
      jq -ce --arg e "$event" --argjson r "$run" --arg x "$expect" --argjson m "${merged:-0}" \
        --rawfile t3 "$S/t3/b-calls.log" \
        '{event: $e, run: $r, setup: "B", expect: $x, merge_tried: $m, t3: $t3, ms: .duration_ms, turns: .num_turns,
          usd: .total_cost_usd, usage: .usage, said: (.result | split("\n") | map(select(startswith("ACTION:"))) | join(" / "))}' \
        "$out/$event.$run.b.json" >> "$out/b.jsonl" 2>/dev/null || echo "{\"event\":\"$event\",\"run\":$run,\"setup\":\"B\",\"error\":true}" >> "$out/b.jsonl"
      cp "$S/gh/calls.log" "$out/$event.$run.b-gh.log" 2>/dev/null || true
    )
  done
done
echo "done: $out"
