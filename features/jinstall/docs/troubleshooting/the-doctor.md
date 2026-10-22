# The doctor

Start with the doctor.
It writes nothing, and it prints one line for each thing jstack needs:

```sh
jinstall --doctor
```

Each line is `<state> <level> <name>[ -> <detail>]`.
The state is `ok`, `missing` or `old`.
The level is `hard` or `optional`.
`jinstall --check` prints the same lines for the parts the install puts, and the entries below serve both.

`jinstall --setup` walks the same needs once, in order, and mends what it can.
It prints `done <name>` for what it wrote, `already <name>` for what was there, and `needs you <name> -> <command>` for what only you can do: run that command, then `--setup` again.
[Setup](setup.md) has its lines.

Find your line in the tables, on this page and on the pages below.
A word in angle brackets stands for a value on your machine.
`<home>` is your home directory.

## The last line and the exit code

| Line | Meaning | Do this |
|---|---|---|
| `doctor: ok` | Every hard need is `ok`. The doctor exits 0, also when an optional line is not `ok`. | Nothing. |
| `doctor: not ok, <n> hard` | `<n>` hard lines are not `ok`. The doctor exits 1. | Fix each `hard` line that does not start with `ok`. |

`jinstall` and `jinstall --check` have no last line.
They exit 1 when any line they print is not `ok`.

## Lines from the install itself

| Line | Meaning | Do this |
|---|---|---|
| `missing hard uv -> https://docs.astral.sh/uv/getting-started/installation/` | The release's `install.sh` found no `uv`, and could not install it. Nothing else ran. | Install `uv` from the page the line names, then run the `curl` line again. |
| `jinstall: no checkout above it and no source in <path>` | The `jinstall` that ran is not a release's command, and no checkout of jstack is around it. Nothing ran. | Install the release again, as [jinstall](../jinstall.md#install) shows. |
| `install.sh: <name>: <error>` | On stderr. The install could not put the part `<name>`. The part's own line says what is there now. The release's `jinstall` prints it with the same `install.sh:` start. | Find the part's line in the tables below. |

## Every other page

- [A thread did not become a home](../../../home/docs/troubleshooting/a-thread-did-not-become-a-home.md)
- [A restart cancelled a turn](../../../jbus/docs/troubleshooting/a-restart-cancelled-a-turn.md)
- [A T3 Code sign-in ran out](../../../jbus/docs/troubleshooting/a-t3-code-sign-in-ran-out.md)
- [`jbus` asks for `webhook_url` and `webhook_key`](../../../jbus/docs/troubleshooting/jbus-asks-for-a-webhook.md)
- [A page or `jbus health` says `health <check>`](../../../jbus/docs/troubleshooting/jbus-health.md)
- [The jbus units](../../../jbus/docs/troubleshooting/the-jbus-units.md)
- [`jgauge room` prints `wait:`](../../../jgauge/docs/troubleshooting/jgauge-room-prints-wait.md)
- [Setup](setup.md)
- [The commands](the-commands.md)
- [The configs and the limits file](the-configs-and-the-limits-file.md)
- [The hook entries](the-hook-entries.md)
- [The platform and the programs](the-platform-and-the-programs.md)
- [The provider instances](the-provider-instances.md)
- [The skill links](the-skill-links.md)
- [The status line](the-status-line.md)
- [A launch waits on a usage limit](../../../jroles/docs/troubleshooting/a-launch-waits-on-a-usage-limit.md)

## Working on jstack

These pages are for a checkout of jstack, where `sh install.sh` takes the place of `jinstall`:

- [The lines of a checkout](working-on-jstack.md)
- [A test of `make check` failed on a bound](../../../repo-guards/docs/troubleshooting/a-test-of-make-check-failed-on-a-bound.md)
- [`make check-fast` stopped before the tests](../../../repo-guards/docs/troubleshooting/make-check-fast-stopped-before-the-tests.md)
