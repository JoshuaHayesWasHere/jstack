# jgauge room

`jgauge room` says whether the machine and the plan have room for one more thread: `go`, or `wait: ` and the first reading that has none. jbus asks it before every launch, so a row with no room waits and is launched on a later pass.
`jgauge session` counts what a thread's session used, `jgauge context` tells a home how full its context is, through `features/home/hooks/home-gauge.sh`, and `jgauge test-slot` runs a command while it holds one of the machine's test slots.
The counts are checked against two probe sessions (`features/jgauge/docs/meter-findings.md`).

Paths:
- `features/jgauge/src/jgauge/`
- `features/jgauge/hooks/`
- `features/jgauge/docs/`
- `features/jgauge/units/`
- `features/home/hooks/home-gauge.sh`
Tests: none

## Sub-features

- `room-go` prints `go` on an idle machine under its plan limits.
- `room-load` prints `wait:` when the one-minute load is at or over 85% of the cores.
- `room-limit` prints `wait:` when the five-hour or weekly limit is at or over 100% used.
- `room-instance` reads the limits of the instance `--instance` names, from `<LIMITS>.<instanceId>`, and the built-in `claudeAgent`'s from `LIMITS`.
- `room-unknown` prints `go` and a `note:` on stderr when the plan's limits are not known.
- `room-holds-launch` keeps an approved row from launching while there is no room.
- `meter` counts a session, a home's context and a test slot: not driven yet.

## How to get to it (user POV)

- Run `jgauge room`.
- Run `jbus poll` with an approved row in the queue, and read its `wait <slug>: no room: ...` line.

## Driving it with verify-jstack

Needs: `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/merged.json`, `machine/proc`, `machine/limits`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- `$PROC` is `$VERIFY_JSTACK_SANDBOX/machine/proc` and `$LIMITS` is `$VERIFY_JSTACK_SANDBOX/machine/limits`: the load starts at `0.10` and both limits at 10.

- **Idle.** Run `record jgauge-room jgauge room`. It prints `go`.
- **Load.** Run `echo "999.00 9.99 9.99 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"`, then `record jgauge-room jgauge room`. It prints `wait: load 999.00 is at or over 85% of <n> cores`, and exits 0.
- **A row waits.** Run `printf '# alpha: a demo task\nWhere: `src/alpha/`\nPull request: none\n' | record jgauge-room jbus queue add alpha --priority 1`, then `record jgauge-room jbus queue approve alpha --by user --at "2026-10-12 00:30 $(date -d '2026-10-12 00:30' +%Z)" --sha "$(sha256sum "$JBUS_STATE_DIR/demo/briefs/alpha.md" | cut -c1-12)"`, then `record jgauge-room jbus poll`. The pass prints `wait alpha: no room: load 999.00 is at or over 85% of <n> cores` and no `launched` line.
- **Room again.** Run `echo "0.10 0.10 0.10 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"`, then `record jgauge-room jbus poll`. It prints `launched alpha: mcp:sandbox-thread-1`.
- **Plan limit.** Run `printf 'five_hour 100 %s\nseven_day 10 %s\n' "$(($(date +%s) + 3600))" "$(($(date +%s) + 3600))" > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"`, then `record jgauge-room jgauge room`. It prints `wait: the five-hour limit is 100% used, at or over 100%, and resets in 1 h 0 min` (or `0 h 59 min`).
- **Another instance.** Run `printf 'five_hour 10 %s\nseven_day 10 %s\n' "$(($(date +%s) + 3600))" "$(($(date +%s) + 3600))" > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits.claudeAgent_claude_prime"`, then `record jgauge-room jgauge room --instance claudeAgent_claude_prime`. It prints `go`: the cap above is `claudeAgent`'s, and prime's own file has room.
- **Limits not known.** Run `: > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"`, then `record jgauge-room jgauge room`. It prints `note: the plan's five-hour and weekly limits are not known: <path> does not give them` and `go`.
- **Proof.** Copy `t3/calls.jsonl` into `$VERIFY_JSTACK_EVIDENCE`: its one `t3_thread_launch` is from the pass after the load fell.

## Gotchas

- `jgauge room` exits 0 for `go` and for `wait:`. Read the line.
- The core count is the real machine's (`nproc`). Use a load no machine has room for, like `999.00`, so the recipe holds everywhere.
- Without `PROC` and `LIMITS` set, `jgauge room` reads the real machine and the real plan. Doctor checks both point into the sandbox.
- A limit whose reset time has passed counts as not known. Write the reset as a time ahead of now, as `launch.sh` does.
- `record` keeps stdout and stderr together, so the `note:` line is in the evidence beside `go`.
