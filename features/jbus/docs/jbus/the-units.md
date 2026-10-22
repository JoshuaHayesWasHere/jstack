# The units

`jinstall` links each systemd unit of `features/jbus/units/` into `~/.config/systemd/user/`, reloads systemd, and enables the timers that run jbus.
In a release the links point into the tool's own copy, `<tool venv>/share/jstack/features/jbus/units/`, and in a checkout into the checkout.
Each unit runs `~/.local/bin/jbus`.

| Unit | Runs | When | Enabled by the install |
|---|---|---|---|
| `jbus.timer`, `jbus.service` | `jbus poll`, one pass | Every minute (`OnUnitActiveSec=1min`), from 2 minutes after boot | Always |
| `jbus-failed.service` | `jbus alarm` | When a pass fails (`OnFailure=` of `jbus.service`) | Started by `jbus.service` |
| `jbus-stale.timer`, `jbus-stale.service` | `jbus alarm --stale 2h` | Every 15 minutes | Always |
| `jbus-snapshot.timer`, `jbus-snapshot.service` | `jbus snapshot` | At 08:30 and 17:30 local time | Once the homes' state tree has a remote and gitleaks is on the machine |
| `jbus-snapshot-failed.service` | `jbus snapshot --alarm` | When a snapshot fails | Started by `jbus-snapshot.service` |
| `jbus-ci.timer`, `jbus-ci.service` | `jbus ci --report --each` | Mondays at 09:00 in the machine's zone | Once a project says `ci_report = true` |
| `jbus-relay.service` | `jbus relay` | Always on, restarted on a failure | Once `~/.config/jbus-relay/env` holds every key the relay needs |
| `jbus-view.service` | `jbus view` | Always on | Never: `systemctl --user enable --now jbus-view.service` starts it |

`jbus.service` stops a pass after 20 minutes (`TimeoutStartSec=20min`).
`jbus-stale.timer` catches a timer that stopped, which fails no pass ([When jbus fails](when-jbus-fails.md)).
`jbus-snapshot.timer` is [Back up the homes' state](back-up-the-homes-state.md), `jbus-ci.timer` is [Measure the CI](measure-the-ci.md), `jbus-relay.service` is [The relay](the-relay.md), and `jbus-view.service` is [The view](the-view.md).

An optional unit is turned off again by the next install once the config that asked for it is gone.
`jinstall --check` and `jinstall --doctor` print one `units` line, and [The jbus units](../troubleshooting/the-jbus-units.md) says what each form of it means.

Each unit's `Documentation=` names the page of these docs for what it runs, such as [Set up jbus](set-up-jbus.md) for `jbus.timer`, by where its file is (`%Y`).
`systemctl --user show -p Documentation <unit>` prints that page.
A unit copied in place of the link loses that, and `jinstall --check` reports the copy as old.
