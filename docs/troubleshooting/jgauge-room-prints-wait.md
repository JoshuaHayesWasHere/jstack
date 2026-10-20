# `jgauge room` prints `wait:`

`jgauge room` prints `wait: ` and the first reading that has no room. No thread is launched until it prints `go`. `wait:` is an answer, not a fault: most readings clear by themselves.

| Line | Meaning | Do this |
|---|---|---|
| `wait: load <load> is at or over 200% of <n> cores` | The run queue is twice the cores: a backstop past what CPU pressure already says. A review never says it: its check, `jgauge room --light`, skips the load. | Wait for running tests or builds to end. |
| `wait: CPU pressure <n> is at or over 40` | Something waited for a core for that share of the last minute (`some avg60` of `/proc/pressure/cpu`). A review never says it: `jgauge room --light` skips it with the load. | Wait for running tests or builds to end. |
| `wait: <n> GB of memory available, under 6` | The machine is short of memory. | Close what holds the memory. |
| `wait: memory pressure <n> is at or over 10` | Programs wait on memory. | Close what holds the memory. |
| `wait: /tmp has <n> of <m> file slots used, over 85%` | `/tmp` is almost out of file slots. | Remove old test directories from `/tmp`. |
| `wait: the five-hour limit is <n>% used, at or over 100%, and resets in <time>` | The plan's limit of the instance asked about (`--instance`, `claudeAgent` by default) is used up. The same line names `the weekly limit`. | Wait for the reset, or launch on another instance of the role's pool. |
| `wait: <name> is not the name of a provider instance` | `--instance` was given a name with a character an instance id does not have. | Give the id as `orchestrator_capabilities` lists it. |
| `wait: the load or the core count could not be read` | A reading is missing. The lines for the CPU pressure, the memory, the memory pressure and the file slots have the same form. | `jgauge room` reads `/proc` and `df`. Check that both work in this shell. |

A `note: the plan's ... not known` line on stderr is no `wait:`. It says the limits file is missing or stale, and `jgauge room` still prints `go`.
