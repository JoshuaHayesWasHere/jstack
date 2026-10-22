# Installing jstack

`install.sh` puts every part jstack carries onto a machine: a layout for each harness under `~/.local/share/jstack/harness/` (Claude Code, Codex and Cursor), a link for each skill in `~/.claude/skills`, `~/.codex/skills` and `~/.agents/skills` into its own harness's layout, the start hook and the tips hook in `~/.claude/settings.json`, the start hook in `~/.codex/hooks.json`, the six commands as the `uv` tool `jstack`, the limits writer as `statusLine`, and, once jbus has a config, the jbus units and the timer. It prints one line for each part, `<state> <level> <name>[ -> <detail>]`, where the state is `ok`, `missing` or `old` and the level is `hard` or `optional`. With `--check` it prints the same lines and writes nothing. With `--uninstall` it takes away what names this checkout and prints `removed <piece>` or `kept <piece> -> <why>`.

Paths:
- `/install.sh`
- `/skills.json`
- `features/jinstall/src/jinstall/`
- `features/jbus/src/jbus/*.py`
- `features/jbriefs/src/jbriefs/`
- `features/jgauge/src/jgauge/`
- `features/jmerge/src/jmerge/`
- `features/jpack/src/jpack/`
- `features/jleak/src/jleak/`
- `features/jleak/hooks/`
- `features/jroles/src/jroles/`
- `features/jsettings/`
- `hooks/`
- `features/jbus/units/jbus.service`
- `features/jbus/units/jbus.timer`
- `features/jbus/units/jbus-failed.service`
- `features/jbus/units/jbus-relay.service`
- `features/jbus/units/jbus-snapshot.service`
- `features/jbus/units/jbus-snapshot.timer`
- `features/jbus/units/jbus-snapshot-failed.service`
- `features/jbus/units/jbus-view.service`
Tests: none

## Sub-features

- `install-check-missing` reports every part as `missing` in a new HOME, writes nothing, and exits 1.
- `install-puts` puts every part, prints `ok` for each, and exits 0.
- `install-layouts` assembles one layout for each harness, whose skill files link to their files in the checkout, with `templates/` and `playbooks/` beside `skills/`.
- `install-points-here` points each skill link and hook command into its own harness's layout, and each unit into the checkout's `templates/`.
- `install-from-a-wheel` does the same with `jinstall` from a wheel, in a HOME with no checkout, with every layout file a link into the installed wheel.
- `install-idempotent` changes nothing on a second run.
- `install-stale-tool` says `stale` of a tool whose editable paths lack a package root pyproject.toml lists, as one built before a package moved, and a run installs it again.
- `install-follows-a-move` says `stale` of a layout whose skill a pulled merge moved, every link of that skill dangling, and a run in the main checkout, which `jmerge` makes after such a merge, leaves every link resolving.
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
- **Check a new HOME.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Its first line is `ok hard generated files are current`, the next three are `missing hard layout <harness> <HOME>/.local/share/jstack/harness/<harness>`, every other starts with `missing`, the last is `missing optional units <HOME>/.config/systemd/user`, and it exits 1. `$HOME/.claude` still does not exist.
- **Install.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`. Every line starts with `ok`, and it exits 0.
- **See where a link points.** Run `record install-skills readlink "$HOME/.claude/skills/crew" "$HOME/.codex/skills/crew" "$HOME/.agents/skills/crew"`. It prints `<HOME>/.local/share/jstack/harness/claude-code/skills/crew`, then the same under `codex` and `cursor`.
- **See every link resolve into the checkout.** Run `record install-skills sh -c 'for l in "$HOME"/.claude/skills/* "$HOME"/.codex/skills/* "$HOME"/.agents/skills/*; do for f in $(find -L "$l" -type f); do r=$(readlink -f "$f"); case $r in "$VERIFY_JSTACK_REPO"/*) ;; *) echo "outside: $f -> $r";; esac; done; done; echo checked'`. It prints only `checked`, but for the two files of `skills/home` that the layout writes because they link into `docs/`.
- **See the templates beside the skills.** Run `record install-skills realpath "$HOME/.claude/skills/crew/../../templates"`. It prints `<HOME>/.local/share/jstack/harness/claude-code/templates`.
- **See the hooks.** Run `record install-skills jq -r '.hooks[][].hooks[].command, (.statusLine.command // empty)' "$HOME/.claude/settings.json" "$HOME/.codex/hooks.json"`. Each command of `settings.json` runs a script under `<HOME>/.local/share/jstack/harness/claude-code/hooks/`, and the one of `hooks.json` under `.../codex/hooks/`.
- **See the commands.** Run `record install-skills ls "$HOME/.local/bin" "$UV_TOOL_DIR"`. The six commands, and the one tool `jstack`.
- **See the units.**
  Run `record install-skills readlink "$HOME/.config/systemd/user/jbus.timer"`, then `record install-skills cat "$VERIFY_JSTACK_SANDBOX/systemctl.log"`.
  The link points at `<this checkout>/features/jbus/units/jbus.timer`, and the log has `--user daemon-reload` and `--user enable --now jbus.timer`.
- **Check again.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Every line starts with `ok`, and it exits 0.
- **Stand in for a tool built before a move.** Run `sed -i '\|/features/jsettings/src$|d' "$UV_TOOL_DIR"/jstack/lib/python*/site-packages/_editable_impl_jstack.pth`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. The line for the commands is `old hard commands jstack -> stale: its editable paths lack <this checkout>/features/jsettings/src`, and it exits 1.
- **Install it again.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --check`. Every line starts with `ok`, and it exits 0.
- **Put a directory where a link goes.** Run `rm "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew" && mkdir "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew"`, then `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh"`. The line for it is `old hard <HOME>/.claude/skills/crew -> not a link`, the directory is still there, and it exits 1. Then run `rmdir "${VERIFY_JSTACK_SANDBOX:?}/home/.claude/skills/crew"`.
- **Uninstall.** Run `record install-skills sh "$VERIFY_JSTACK_REPO/install.sh" --uninstall`. Every line starts with `removed`, and it exits 0. Run it again: it prints nothing.
- **Proof.** Run `record install-skills sh -c '(cd "$HOME" && find . | sort) | diff "$VERIFY_JSTACK_SANDBOX/before.txt" -'`. It prints nothing and exits 0. The `record` file holds every line of each run.

The checkout's own skills, from a clone inside the sandbox's HOME, since a run under a HOME that is not yours links none into a checkout outside it:

- **Clone and install.** Run `git clone -q "$VERIFY_JSTACK_REPO" "$HOME/jstack" && cd "$HOME/jstack"`, then `record project-skills sh install.sh`.
- **See each project skill resolve.** Run `record project-skills sh -c 'readlink -f .claude/skills/verify-jstack/SKILL.md .claude/skills/verify-main-red/SKILL.md .cursor/skills/verify-jstack/SKILL.md'`. It prints each one's `SKILL.md` in its feature's folder, under `features/verify-jstack/project-skill/` and `features/jbus/project-skill/verify-main-red/`.
- **See git track none of it.** Run `record project-skills git ls-files .claude .cursor`. It prints nothing, and `git status --short --ignored .claude .cursor` prints `!! .claude/` and `!! .cursor/`.

From a wheel, in a second sandbox, so that no checkout is above its HOME or its tool:

- **Build and install the wheel.** Run `record install-skills uv build --wheel --out-dir "$VERIFY_JSTACK_SANDBOX/dist" "$VERIFY_JSTACK_REPO"`, then `record install-skills uv tool install "$VERIFY_JSTACK_SANDBOX"/dist/*.whl`. The tool's commands land in `$HOME/.local/bin`.
- **Install from it.** Run `record install-skills "$HOME/.local/bin/jinstall"`, then `record install-skills "$HOME/.local/bin/jinstall" --check`. Every line starts with `ok`, and there is no `generated files` line and no `pre-push` line.
- **See every link resolve into the wheel.** Run the loop of the checkout's recipe with `"$UV_TOOL_DIR"/jstack/share/jstack` in place of `$VERIFY_JSTACK_REPO`. It prints only `checked`, but for the same two written files.

From a clone of this checkout at the commit before a merge that moved a skill, in a third sandbox, so that the merge can be pulled as `jmerge` pulls it.
`jmerge`'s own merge is not reachable from a sandbox (the stand-in `gh` refuses a merge): `features/jmerge/tests/test_jmerge_follow.py` drives the run it makes after one.

- **Clone at the commit before #202, which moved pr-review into `features/`.** Run `git clone -q --bare "$VERIFY_JSTACK_REPO" "$VERIFY_JSTACK_SANDBOX/jstack-origin.git" && git -C "$VERIFY_JSTACK_SANDBOX/jstack-origin.git" update-ref refs/heads/main 382f413~1 && git clone -q -b main "$VERIFY_JSTACK_SANDBOX/jstack-origin.git" "$VERIFY_JSTACK_SANDBOX/jstack" && cd "$VERIFY_JSTACK_SANDBOX/jstack"`.
- **Install from it.** Run `record install-skills sh install.sh`. Every layout line is `ok`, and `readlink -f "$HOME/.claude/skills/pr-review/SKILL.md"` is `<the clone>/skills/pr-review/SKILL.md`.
- **Merge the move.** Run `git -C "$VERIFY_JSTACK_SANDBOX/jstack-origin.git" update-ref refs/heads/main 382f413`, then `record install-skills git pull -q --ff-only`.
- **See it stale.** Run `record install-skills sh install.sh --check`. The three layout lines are `old hard layout <harness> <layout> -> stale: skills/pr-review/SKILL.md, and 7 more`, and `record install-skills sh -c 'find -L "$HOME"/.claude/skills/ -type l; echo checked'` lists each file of `pr-review` before `checked`.
- **Run what `jmerge` runs after it.** Run `record install-skills sh install.sh`, then the `find` again. It prints only `checked`, and the layout lines of `--check` are `ok`.

## Gotchas

- This recipe is safe only because `env.sh` sets HOME to the sandbox and puts the stand-in `systemctl` first on PATH. Run Doctor first. With the real HOME, a plain `install.sh` from a linked worktree is refused, and one from a main checkout installs for real.
- The stand-in `systemctl` starts nothing: the recipe proves the links and the calls, not that systemd runs a pass.
- `uv tool install` is the real one. It needs `hatchling` in uv's cache or the network: with neither, the line is `missing hard commands jstack` and the reason is on stderr.
- The link count follows `skills.json`: assert that every line is `ok`, not a number of lines.
- A new skill is in no layout until `python3 scripts/generate-jstack-trees.py` lists it in `skills.json`: the first line, `generated files are current`, says so.
- The `rm` in the recipe names the sandbox's HOME through `${VERIFY_JSTACK_SANDBOX:?}`, so a shell that sourced no `env.sh` stops there and removes nothing. Keep it that way: never write it with `$HOME`.
- `install.sh` needs a Python 3.12 or `uv`, and says so when it has neither.
- The links point at the checkout the script is run from. Run the one under `$VERIFY_JSTACK_REPO`, not a copy, but in the recipe of a move, whose clone is the checkout under test.
- In the recipe of a move, the line for the commands is `old hard commands jstack -> jbriefs is shadowed by <this checkout>/.venv/bin/jbriefs`: `env.sh` puts this checkout's commands first on PATH, and it is not the move's.
