# `jgauge room` prints `wait:`

`jgauge room` prints `wait: ` and the first reading that has no room. No thread is launched until it prints `go`. `wait:` is an answer, not a fault: most readings clear by themselves.

| Line | Meaning | Do this |
|---|---|---|
| `wait: load <load> is at or over 200% of <n> cores; the busiest: <command> in <folder> (<n>%), ...` | The run queue is twice the cores: a backstop past what CPU pressure already says. The line ends `; the busiest:` with the three processes that used the largest share of a core over their lives, each with its command and its working directory. A review never says it: its check, `jgauge room --light`, skips the load. | Wait for running tests or builds to end, or stop a process the line names that nothing needs. |
| `wait: CPU pressure <n> is at or over 40` | Something waited for a core for that share of the last minute (`some avg60` of `/proc/pressure/cpu`). A review never says it: `jgauge room --light` skips it with the load. | Wait for running tests or builds to end. |
| `wait: <n> GB of memory available, under 6` | The machine is short of memory. | Close what holds the memory. |
| `wait: memory pressure <n> is at or over 10` | Programs wait on memory. | Close what holds the memory. |
| `wait: /tmp has <n> of <m> file slots used, over 85%` | `/tmp` is almost out of file slots. | Remove old test directories from `/tmp`. |
| `wait: the five-hour limit is <n>% used, at or over <headroom>%, and resets in <time>` | The plan's limit of the one instance asked about is at or over your `headroom` (90 by default, [configuration](../../../jinstall/docs/configuration.md#jstack)): `--instance <id>`, or a role whose pool is that instance alone, or `claudeAgent` for a role with no pool. The same line names `the weekly limit`. | Wait for the reset, or give the role a pool of more than one instance ([jroles](../../../jroles/docs/jroles.md#pools)). |
| `wait: <a> and <b> are both at or over <headroom>%: <a>'s <window> limit is <n>% used and resets in <time>, ...; the first resets in <time>` | Every instance of the pool of the role asked about (`--role`, `crew` by default) is full. Each is named with the window that holds it longest. | Wait for the first reset it names. |
| `wait: <pool> is not a pool of provider instances` | `--instance`, or the role map's pool, gave a name with a character an instance id does not have. | Give the id as `orchestrator_capabilities` lists it. |
| `wait: the load or the core count could not be read` | A reading is missing. The lines for the CPU pressure, the memory, the memory pressure and the file slots have the same form. | `jgauge room` reads `/proc` and `df`. Check that both work in this shell. |

A `note: the plan's ... not known` line on stderr is no `wait:`. It says the limits file is missing or stale, and `jgauge room` still prints `go`.

A `note: <a>'s <window> limit is 100% used and resets in <time>; the pool has room on <b>` line on stderr is no `wait:` either: one instance of the pool is full, `<b>` has room, and `jgauge room` prints `go`.
A `note: room reads claudeAgent's limits: <why>` line says the role map could not be used, so the check read the file `LIMITS` names, as it does for a role with no pool.
