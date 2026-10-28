# A launch waits on a usage limit

`jroles <role>` picks the first instance of the role's pool with headroom in the ledger, and a launch, by `jbus` or by hand, goes to that instance ([jroles](../jroles.md#pools)).
`jgauge room` makes a launch wait on the plan only while every instance of that pool is full ([jroles](../jroles.md#the-ledger)).
A thread already running moves only when its turn fails on a usage limit.
It then moves to the first instance of its pool with headroom ([jroles](../jroles.md#pools)).
To see what a cap would do to one thread, replay a recorded cap with `jbus failover --replay <items.json> --thread <id> --dry-run`.
It prints the move and writes nothing.
Without `--dry-run`, it makes the move.

| Line | Meaning | Do this |
|---|---|---|
| `jroles: <role> waits: <a> and <b> are both capped until <time>`, exit 75 | Every instance of the pool has a window at or over your `headroom` (90% by default). | Wait for the time it names. The first launch after that time goes on. `jbus` says it once, as a `stall`, and launches by itself after the reset. |
| `refused <role>: <id> is no <provider> instance of providers.json` | The role line names an instance the inventory does not declare under the line's provider. The role inherits. | Add the instance to `~/.config/jstack/providers.json`, as [Configuration](../../../jinstall/docs/configuration.md#provider-instances) shows, or take the id off the line. |
| `refused <role>: the pool <list> names an instance twice or none` | The instance field has an id twice, or an empty one, such as `claudeAgent,`. | Write each id once, joined by commas with no space. |
| `wait: <a> and <b> are both at or over <headroom>%: <a>'s <window> limit ... resets in <time>, <b>'s ...; the first resets in <time>` from `jgauge room` | Every instance of the role's pool is full, each named with the window that holds it longest. | Wait for the first reset it names. A pool with one instance free says `go`. |
| `note: <a>'s <window> limit is 100% used and resets in <time>; the pool has room on <b>` from `jgauge room` | One instance of the pool is full and `<b>` has room, so the launch goes on `<b>`. | Nothing. |
| `failover <name>: <window> limit until <time>, carry-on on <a> to <b>, ...` in a `jbus` pass | `jbus` moved a Claude thread of a `jbus` project from `<a>`, where it capped, to `<b>`, in either direction between the instances of its pool. The thread is a crew (`<name>` is its slug), a reviewer (`review <slug>`), a scout (`scout <slug>`) or a home (`home`). | Nothing. The thread carries on there, and stays there until `<b>` caps, since nothing moves it back. |
| `failover <name>: ..., carry-on on <a>, ...` with no `to` | The thread's configuration was already on the instance with headroom, so `jbus` only told it to carry on. | Nothing. |
| `capped <instance>: <window> until <time>` in a `jbus` pass | A thread's turn ended on that instance's usage limit, and the ledger now has it. | Nothing. `jbus` moves the thread to the next instance of its pool, or the thread waits for the reset. |
