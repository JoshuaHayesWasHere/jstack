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
| `timeout jbus` | The passes stopped at `jbus.service`'s `TimeoutStartSec`, in its journal on Linux or its agent's log on macOS, over the last 60 minutes. | 1 |
| `timeout jmerge` | How many times a pass stopped `jmerge` at its 17-minute timeout, read from the line the pass writes to the same journal. | 1 |
| `relay` | The state of `jbus-relay.service`. | not `active` |
| `relay heartbeat` | How long since the relay last wrote its heartbeat. | 3 minutes |
| `relay silent` | How long since the relay last heard a body. | `RELAY_SILENT_MINUTES`, 90 |
| `relay errors` | How long a route's POSTs have failed, and how many bodies wait. | 10 minutes |
| `relay refused` | The bodies a target refused permanently in the last 60 minutes, and where the last is kept in `dead/`. | 1 |
| `quota <instance> seven_day` | The share of the instance's seven-day window used, from the ledger. Every instance has one: 0 where a Claude instance's ledger is fresh and has no line of the window, which is not open, and unread, null, where nobody reads the instance's use. | 80% |
| `quota <instance> five_hour` | The share of the five-hour window used, read the same way. | paged only when full, as `capped` |
| `capped <instance>` | The windows of the instance that are full, and until when. | 100% of a window |

The mounts are those the stack writes: jbus's state and the homes, each project's checkout, the temp directory, your home directory, the ledger, and the relay's state.
A pass that is stopped cannot say so itself, so on Linux jbus reads both timeouts from the journal of `jbus.service`, and on macOS from the agent's log, `~/Library/Logs/jstack/jstack.jbus.log`.

The relay is optional, and a machine with none has only the `relay` line above, `not watched`.
jbus watches the relay only where the config posts to it, with a `blocking_url` on 127.0.0.1 or localhost at `RELAY_PORT` ([The relay](the-relay.md)).
jbus reads `RELAY_PORT` and `RELAY_STATE` from the relay's own env file, `~/.config/jbus-relay/env`, since `jbus.service` does not load that file.
jbus posts a `refresh` to `blocking_url` each hour, so a relay it posts to hears a body at least that often.
While the relay's unit is not active or its heartbeat is stale, jbus does not judge silence and errors.
The `relay` and `relay heartbeat` lines already report the fault.
Silence counts from the last body the relay heard.
A restart keeps that time, so a relay that restarts often still goes silent.

The instances are the built-in one and each instance a role's pool names ([jroles](../../../jroles/docs/jroles.md)).
Their numbers come from the ledger, which the threads' status lines and their usage-limit failures write.

## The readings kept

Each pass's look keeps its readings in `health.jsonl`, in jbus's state directory, one JSON line `{at, key, value, over}` a reading.
`value` is the number alone: the percent of a `disk`, `inodes` or `quota` reading, 1 or 0 of the others, by whether the reading is over, and null where the look could not read it.
A reading gets a line when its `value` or `over` differs from its key's last line, or when that line is 5 minutes old or more, so each key has a line at most one a pass, and at least every 5 minutes and one pass: within 15 minutes, since the longest pass of the push of 2026-11-09 took 435 s.
The look reads each key's last line from the file's last 64 KiB, so a look that ran twice writes nothing new, and a key whose last line is older than that gets one at once.
`jbus health` keeps nothing.
The telemetry store reads the file as the table `health_readings` ([The telemetry store](the-telemetry-store.md)), and the scorecard's `disk` measure reads the day's highest `disk` or `inodes` value from it.

## Incidents and pages

A check over its limit is an incident, under the key `health <check>`.
A pass pages an incident once when it starts, and logs its end, a `quiet` `recovered` event, when a reading under the limit ends it.
It tracks the incident in `streaks.json`, as it does every other alert.
The page is the line `jbus health` prints, after `alert:` or `recovered:`.
It goes to the desktop with `notify-send`.
On macOS, which has no `notify-send`, it goes to no desktop.
It also goes to the infra home, as an alert of the machine's.
A check that could not be read leaves its incident as it is.
Some checks go away: a mount or an instance is gone, or the config no longer posts to the relay.
The incident of such a check ends with no page.

## The pause

`capped <instance>` names the instance that new launches skip ([jroles](../../../jroles/docs/jroles.md#pools)).
While the cap holds, a new launch goes to the next instance of the pool.
With every instance capped, no launch starts, and the page says until when.
At the reset, launches go back to the instance by themselves.
The recovered page says so in one line, `launches on <instance> resume`, and the pass's journal has the same line.
