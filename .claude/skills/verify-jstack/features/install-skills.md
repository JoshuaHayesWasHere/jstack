# Installing jstack

`install.sh` puts every part jstack carries onto a machine: a link for each skill in `~/.claude/skills` and `~/.agents/skills`, the start hook and the tips hook in `~/.claude/settings.json`, the start hook in `~/.codex/hooks.json`, the six commands as the `uv` tool `jstack`, the limits writer as `statusLine`, and, once jbus has a config, the jbus units and the timer. It prints one line for each part, `<state> <level> <name>[ -> <detail>]`, where the state is `ok`, `missing` or `old` and the level is `hard` or `optional`. With `--check` it prints the same lines and writes nothing. With `--uninstall` it takes away what names this checkout and prints `removed <piece>` or `kept <piece> -> <why>`.

Paths:
- `/install.sh`
- `src/jinstall/`
- `src/jbus/*.py`
- `src/jbriefs/`
- `src/jgauge/`
- `src/jmerge/`
- `src/jpack/`
- `src/jleak/`
- `src/jroles/`
- `features/jsettings/`
- `hooks/`
- `templates/jbus.service`
- `templates/jbus.timer`
- `templates/jbus-failed.service`
- `templates/jbus-relay.service`
- `templates/jbus-snapshot.service`
- `templates/jbus-snapshot.timer`
- `templates/jbus-snapshot-failed.service`
- `templates/jbus-view.service`
Tests: none

## Sub-features

- `install-check-missing` reports every part as `missing` in a new HOME, writes nothing, and exits 1.
- `install-puts` puts every part, prints `ok` for each, and exits 0.
- `install-points-here` points each skill link and hook command into the checkout's harness copy, `harness/jstack/claude-code/`, and each unit into the checkout's `templates/`.
- `install-idempotent` changes nothing on a second run.
- `install-stale-tool` says `stale` of a tool whose editable paths lack a package root pyproject.toml lists, as one built before a package moved, and a run installs it again.
- `install-keeps-non-link` leaves something that is not a link in place, as `old ... -> not a link`.
- `install-uninstall-leaves-nothing` leaves HOME as it was before the install, and a second `--uninstall` prints nothing.

## How to get to it (user POV)

- Run `sh install.sh` from a jstack checkout.
- Run `sh install.sh --check`.
- Run `sh install.sh --uninstall`.
- Type `/crew`, `/home` or another skill's name in a thread, once installed (not reachable from a sandbox).

## Driving it with verify-jstack

Needs: `home`, `config`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`, with its line `ok   systemctl is the stand-in`.
- `$HOME/.claude`, `$HOME/.agents`, `$HOME/.codex` and `$HOME/.config` do not exist. HOME is the sandbox's.

- **List HOME before.** Run `(cd "$HOME" && find . | sort) > "$VERIFY_JSTACK_SANDBOX/before.txt"`.
- **Check a new HOME.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Its first line is `ok hard harness/ is current`, every other starts with `missing`, the last is `missing optional units <HOME>/.config/systemd/user`, and it exits 1. `$HOME/.claude` still does not exist.
- **Install.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`. Every line starts with `ok`, and it exits 0.
- **See where a link points.** Run `record install-skills readlink "$HOME/.claude/skills/crew"`. It prints `<this checkout>/harness/jstack/claude-code/skills/crew`.
- **See the hooks.** Run `record install-skills jq -r '.hooks[][].hooks[].command, (.statusLine.command // empty)' "$HOME/.claude/settings.json" "$HOME/.codex/hooks.json"`. Each command runs a script under `<this checkout>/harness/jstack/claude-code/hooks/`.
- **See the commands.** Run `record install-skills ls "$HOME/.local/bin" "$UV_TOOL_DIR"`. The six commands, and the one tool `jstack`.
- **See the units.** Run `record install-skills readlink "$HOME/.config/systemd/user/jbus.timer"`, then `record install-skills cat "$VERIFY_JSTACK_SANDBOX/systemctl.log"`. The link points at `<this checkout>/templates/jbus.timer`, and the log has `--user daemon-reload` and `--user enable --now jbus.timer`.
- **Check again.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Every line starts with `ok`, and it exits 0.
- **Stand in for a tool built before a move.** Run `sed -i '\|/features/jsettings/src$|d' "$UV_TOOL_DIR"/jstack/lib/python*/site-packages/_editable_impl_jstack.pth`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. The line for the commands is `old hard commands jstack -> stale: its editable paths lack <this checkout>/features/jsettings/src`, and it exits 1.
- **Install it again.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Every line starts with `ok`, and it exits 0.
- **Put a directory where a link goes.** Run `rm "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew" && mkdir "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew"`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`. The line for it is `old hard <HOME>/.claude/skills/crew -> not a link`, the directory is still there, and it exits 1. Then run `rmdir "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew"`.
- **Uninstall.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --uninstall`. Every line starts with `removed`, and it exits 0. Run it again: it prints nothing.
- **Proof.** Run `record install-skills sh -c '(cd "$HOME" && find . | sort) | diff "$VERIFY_JSTACK_SANDBOX/before.txt" -'`. It prints nothing and exits 0. The `record` file holds every line of each run.

## Gotchas

- This recipe is safe only because `env.sh` sets HOME to the sandbox and puts the stand-in `systemctl` first on PATH. Run Doctor first. With the real HOME, a plain `install.sh` from a linked worktree is refused, and one from a main checkout installs for real.
- The stand-in `systemctl` starts nothing: the recipe proves the links and the calls, not that systemd runs a pass.
- `uv tool install` is the real one. It needs `hatchling` in uv's cache or the network: with neither, the line is `missing hard commands jstack` and the reason is on stderr.
- The link count follows `skills/`: assert that every line is `ok`, not a number of lines.
- The `rm` in the recipe names the sandbox's HOME through `${VERIFY_JSTACK_SANDBOX:?}`, so a shell that sourced no `env.sh` stops there and removes nothing. Keep it that way: never write it with `$HOME`.
- `install.sh` needs a Python 3.12 or `uv`, and says so when it has neither.
- The links point at the checkout the script is run from. Run the one under `$VERIFY_JSTACK_REPO`, not a copy.
