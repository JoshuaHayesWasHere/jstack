# A page or `jbus health` says `health <check>`

`jbus health` prints each check of the machine with its number and its limit, and a pass pages the ones over it ([The health check](../jbus/the-health-check.md)).

| Line | Meaning | Do this |
|---|---|---|
| `alert: health disk <mount>: <n>% of its space used ...` or `inodes <mount>` | The mount is at 80% or more. | Free space there. Under `/tmp`, you can delete old `pytest-of-*` directories that no live process holds. |
| `alert: health timeout jbus: ...` | systemd stopped a pass at `TimeoutStartSec`. | `journalctl --user -u jbus.service` shows the pass. |
| `alert: health timeout jmerge: ...` | A pass stopped `jmerge` at its timeout. | Run `jmerge --check` in the main checkout and see where it waits. |
| `alert: health relay: jbus-relay.service is <state>` or `relay heartbeat` | The relay the config posts to is not running. | `systemctl --user status jbus-relay`, and [The relay](../jbus/the-relay.md) for a refused start. |
| `alert: health relay silent: ...` | No body reached the relay in `RELAY_SILENT_MINUTES`. | See whether passes run (`jbus status`) and post to the relay's port. |
| `alert: health relay errors: ...` | Your chat bot's webhook or the pager has refused the relay's POSTs for 10 minutes. | The relay's journal names the target and the status. |
| `alert: health relay refused: ...` | A target refused a body permanently, and the relay will not send it again. | Read the body in the `dead/` file the line names, and mend what the target refused. |
| `alert: health capped <instance>: ...` | The instance is at 100% of a window, and launches skip it until the reset. | Nothing. Launches resume by themselves, and `recovered: ... launches on <instance> resume` says so. |
| `?    health <check>: ... could not be read` | The source of the check did not answer. | Run the command it reads (`journalctl`, `systemctl --user show`) by hand. |
