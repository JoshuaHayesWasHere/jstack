# The health check

A failure that no thread runs into stays unseen unless something checks the machine as a whole.
`jbus health` runs those checks and prints them.
Every `jbus poll` runs the same checks as its first step and pages what it finds.

```sh
jbus health
```

It prints one line for each check, with its number, what the number counts, and the limit it is held against.
It pages nothing.
It exits 1 when a check is over its limit, and 0 when none is.

```text
ok   health disk /home: 41% of its space used (190.2 of 465.6 GiB), alerts at 80%
ok   health inodes /tmp: 3% of its inodes used (31,207 of 1,048,576), alerts at 80%
ok   health timeout jbus: jbus.service stopped at its 20min start timeout 0 times in the last 60 min, alerts at 1
ok   health relay: the config posts nothing to 127.0.0.1, not watched
over health capped claudeAgent: five_hour full until 2026-10-22 13:30 CEST, pauses its launches at 100% of a window; launches skip claudeAgent until then
```

The first word is `ok`, `over`, or `?` for a check that could not be read.

## The checks

| Check | The number | The limit |
|---|---|---|
| `disk <mount>` | The share of the mount's space used, as `df` gives it. | 80% |
| `inodes <mount>` | The share of the mount's inodes used. A filesystem that counts none, such as btrfs, has no such line. | 80% |
| `timeout jbus` | The passes systemd stopped at `jbus.service`'s `TimeoutStartSec`, in its journal over the last 60 minutes. | 1 |
| `timeout jmerge` | The `jmerge` runs a pass stopped at its 17-minute timeout, from the line the pass writes to the same journal. | 1 |
| `relay` | The state of `jbus-relay.service`. | not `active` |
| `relay heartbeat` | How long since the relay last wrote its heartbeat. | 3 minutes |
| `relay silent` | How long since the relay last heard a body. | `RELAY_SILENT_MINUTES`, 90 |
| `relay errors` | How long a route's POSTs have failed, and how many bodies wait. | 10 minutes |
| `relay refused` | The bodies a target refused for good in the last 60 minutes, and where the last is kept in `dead/`. | 1 |
| `quota <instance> seven_day` | The share of the instance's seven-day window used, from the ledger. | 80% |
| `quota <instance> five_hour` | The share of the five-hour window used. | paged only when full, as `capped` |
| `capped <instance>` | The windows of the instance that are full, and until when. | 100% of a window |

The mounts are those the stack writes: jbus's state and the homes, each project's checkout, the temp directory, your home directory, the ledger, and the relay's state.
A pass that systemd stops cannot say so itself, so jbus reads both timeouts from the journal of `jbus.service`.

The relay is optional, and a machine with none has only the `relay` line above, `not watched`.
The relay is watched only where the config posts to it: a `webhook_url` or `blocking_url` on 127.0.0.1 or localhost at `RELAY_PORT` ([The relay](the-relay.md)).
`RELAY_PORT` and `RELAY_STATE` are read from the relay's own env file, `~/.config/jbus-relay/env`, since `jbus.service` does not load it.
jbus posts a `refresh` to `blocking_url` each hour, so a relay it posts to hears a body at least that often.
While the relay's unit is not active or its heartbeat is stale, jbus does not judge silence and errors.
The `relay` and `relay heartbeat` lines already report the fault.
Silence counts from the last body the relay heard.
A restart keeps that time, so a relay that restarts often still goes silent.

The instances are the built-in one and each instance a role's pool names ([jroles](../../../jroles/docs/jroles.md)).
Their numbers come from the ledger, which the threads' status lines and their usage-limit failures write.

## Incidents and pages

A check over its limit is an incident, under the key `health <check>`.
A pass pages an incident once when it starts, and once when a reading under the limit ends it.
It tracks the incident in `streaks.json`, as it does every other alert.
The page is the line `jbus health` prints, after `alert:` or `recovered:`.
It goes to the desktop with `notify-send`.
If you set a top-level webhook, the page also goes there as an event of the machine, once and not once for each project.
A check that could not be read leaves its incident as it is.
When jbus stops taking a check, because a mount or an instance is gone or the config no longer posts to the relay, the check's incident ends with no page.

## The pause

`capped <instance>` is the instance that launches skip ([jroles](../../../jroles/docs/jroles.md#pools)).
While the cap holds, a new launch goes to the next instance of the pool.
With every instance capped, no launch starts, and the page says until when.
At the reset, launches go back to the instance by themselves.
The recovered page says so in one line, `launches on <instance> resume`, and the pass's journal has the same line.
