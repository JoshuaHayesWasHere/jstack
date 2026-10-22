# The jbus units

The doctor prints a `units` line only once `jbus` has a config.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional units <directory>` | No unit of `jbus` is in `<directory>`. | Run `sh install.sh`. |
| `old optional units <directory> -> lacks <names>` | Some of the three units are not there. | Run `sh install.sh`. |
| `old optional units <directory> -> <unit> -> <path>` | A unit is a link to another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old optional units <directory> -> <names>: a copy of its template, not a link` | A unit was copied by hand and equals its template. | Run `sh install.sh`. It replaces the copy with a link. |
| `old optional units <directory> -> <unit> -> not a link, differs` | A unit is a file of your own that differs from its template. The install does not replace it. | Move the file away, then run `sh install.sh`. |
| `old optional units <directory> -> no ~/.local/bin/jbus` | The units run `~/.local/bin/jbus`, and it is not there. | Fix the `commands jstack` line first, then run `sh install.sh`. |
| `old optional units <directory> -> systemctl --user did not answer, so <timer> is not enabled` | No user manager of systemd answers in this session. | Run `systemctl --user status` to see why, then run `sh install.sh`. |
| `old optional units <directory> -> <timer> is not enabled` | The timer is linked and not enabled, so no pass runs. The ci, relay and snapshot units are enabled only once their `ci report`, `relay` and `state repo` lines are `ok`. | Run `sh install.sh`. |
| `old optional units <directory> -> <unit> is enabled, and nothing asks for it` | The ci, relay or snapshot unit is on, and the config that asks for it is gone: no project with `ci_report = true`, no relay env file, or no remote for the state tree. | Run `sh install.sh`, which turns it off, or put the config back. |
| `old optional units <directory> -> needs daemon-reload` | A unit changed on disk since systemd read it. | Run `sh install.sh`, or `systemctl --user daemon-reload`. |
