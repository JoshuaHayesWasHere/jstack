# The lines of a checkout

This page is for working on jstack, in a checkout of its repo.
In a checkout, `sh install.sh` runs the install and takes the verbs of `jinstall`: `sh install.sh --doctor`, `--check`, `--setup`, `--repo [<path>]` and `--uninstall`.
Wherever another troubleshooting page says to run `jinstall`, a checkout runs `sh install.sh` with the same flag.
The lines below print only in a checkout.
[Contributing](../../../../CONTRIBUTING.md) has the setup.

## The script

| Line | Meaning | Do this |
|---|---|---|
| `missing hard python -> 3.12 or newer, or uv, which brings one` | The script found no Python 3.12 and no `uv`, so it ran nothing. | Install `uv`. |
| `missing hard a checkout of jstack around <path> -> curl -fsSL <url> \| sh` | `install.sh` ran outside a checkout, and carries no release version. | Run it from the root of a checkout, or install a release with the `curl` line it names. |
| `usage: install.sh [--check \| --uninstall \| --doctor \| --setup \| --repo [<path>]]` | The argument is not one of the verbs. The script exits 2. | Run it with one verb or none. |
| `install.sh: <checkout> is a linked worktree, and HOME is your own: install from the main checkout` | A plain install from a worktree would point every skill at that worktree. The script wrote nothing. | Run `sh install.sh` in the main checkout. |
| `install.sh: <checkout> is a linked worktree, and HOME is your own: set up from the main checkout` | The same, for `--setup`. The script wrote nothing. | Run `sh install.sh --setup` in the main checkout. |

## The generated files

| Line | Meaning | Do this |
|---|---|---|
| `ok hard generated files are current` | `skills.json`, which the install assembles each layout from, and the other files `scripts/generate-jstack-trees.py` writes from the checkout are current. | Nothing. |
| `old hard generated files are current -> stale: <path>` | A skill, playbook, template or hook was added or changed after the generator ran, so `skills.json` does not list it yet, and it is in no layout. The install does not run the generator. | Run `make trees`, which runs `python3 scripts/generate-jstack-trees.py`, commit what it writes, then run `sh install.sh`. |

## The commands of a checkout

A checkout installs the commands as an editable install of itself, `uv tool install --editable <checkout>`.

| Line | Meaning | Do this |
|---|---|---|
| `missing hard commands jstack` | The `uv` tool `jstack` is not installed, so the nine commands are not on `PATH`. | Run `sh install.sh`. If the line stays, read the `install.sh: commands jstack:` line on stderr. |
| `old hard commands jstack -> lacks <names>` | The tool was installed before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> an install of <path>` | The tool runs the code of another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old hard commands jstack -> stale: its editable paths lack <paths>` | A package moved in the checkout after `uv` built the install, so the install's paths lack its new folder. | Run `sh install.sh`. |
| `old hard commands jstack -> tool <tool> is installed from a release or an index, not as an editable install of this checkout` | A tool of that name came from a release, an index or a git URL. The install does not replace it. | Run `uv tool uninstall <tool>`, then `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename` | The tool is installed under its old name, `jgauge`. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> tool jgauge, from before the rename, lacks <names>` | The old tool is installed, from before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename, is still installed` | Both the old tool and the new one are installed from this checkout. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> tool jgauge, an install of <path>` | The old tool is installed from another checkout. The install does not remove it. | Run `uv tool uninstall jgauge`, then `sh install.sh`. |

## The checkout's own skills

A skill for working on jstack, such as `verify-jstack`, is linked into the checkout as `.claude/skills/<name>` and `.cursor/skills/<name>` ([jinstall](../jinstall.md#the-checkouts-own-skills)).

| Line | Meaning | Do this |
|---|---|---|
| `missing hard <checkout>/<folder>/<name>` | The link for one of the checkout's own skills is not there. `<folder>` is `.claude/skills` or `.cursor/skills`. | Run `sh install.sh`. |
| `old hard <checkout>/<folder>/<name> -> <path>, a skill no feature declares` | The link is left from a skill whose feature no longer names it under `projectSkills`. | Run `sh install.sh`. It removes the link. |
| `old hard <checkout>/<folder>/<name> -> <path>` | The link points somewhere else. | Run `sh install.sh`. It points the link at the skill's feature. |
| `old hard <checkout>/<folder>/<name> -> not a link` | A file or a directory is in the link's place. The install never replaces it. | Move it away, then run `sh install.sh`. |

## A host with nothing on it

`scripts/fresh-host.sh` runs `--setup` on a fresh host: a throwaway `archlinux` container with the checkout's `HEAD` cloned in, `uv`, `git` and `jq` installed, and stand-ins for `t3`, `claude`, `gh`, `lavish-axi` and `systemctl`.
It passes only when the doctor then says `doctor: ok`, a second `--setup` writes nothing, and the only `needs you` line left is `claude`.
It starts a container, so run it under the heavy-suite lock: `flock ~/.local/state/locks/heavy-suite.lock sh scripts/fresh-host.sh`.
