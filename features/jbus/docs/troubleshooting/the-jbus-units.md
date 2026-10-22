# The jbus units

`jinstall --doctor` and `jinstall --check` print one `units` line once `jbus` has a config.
Each fix below runs `jinstall`, which links the units again and enables the timers.
In a checkout of jstack, run `sh install.sh` in its place.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional units <directory>` | No unit is in `<directory>`. | Run `jinstall`. |
| `old optional units <directory> -> lacks <names>` | The units it names are not there. | Run `jinstall`. |
| `old optional units <directory> -> <unit> -> <path>` | A unit is a link to another install or checkout. | Run `jinstall` from the install you want live. |
| `old optional units <directory> -> <names>: a copy of its template, not a link` | A unit was copied by hand and equals its file in the install. | Run `jinstall`. It replaces the copy with a link. |
| `old optional units <directory> -> <unit> -> not a link, differs` | A unit is a file of your own that differs from the install's. The install does not replace it. | Move the file away, then run `jinstall`. |
| `old optional units <directory> -> no ~/.local/bin/jbus` | The units run `~/.local/bin/jbus`, and it is not there. | Fix the `commands jstack` line first, then run `jinstall`. |
| `old optional units <directory> -> systemctl --user did not answer, so <timer> is not enabled` | No user manager of systemd answers in this session. | Run `systemctl --user status` to see why, then run `jinstall`. |
| `old optional units <directory> -> <timer> is not enabled` | The timer is linked and not enabled, so no pass runs. The ci, relay and snapshot units are enabled only once their `ci report`, `relay` and `state repo` lines are `ok`. | Run `jinstall`. |
| `old optional units <directory> -> <unit> is enabled, and nothing asks for it` | The ci, relay or snapshot unit is on, and the config that asks for it is gone: no project with `ci_report = true`, no relay env file, or no remote for the state tree. | Run `jinstall`, which turns it off, or put the config back. |
| `old optional units <directory> -> needs daemon-reload` | A unit changed on disk since systemd read it. | Run `jinstall`, or `systemctl --user daemon-reload`. |

[The units](../jbus/the-units.md) lists each unit and what it runs.
