# The commands

| Line | Meaning | Do this |
|---|---|---|
| `missing hard commands jstack` | The `uv` tool `jstack` is not installed, so the nine commands are not on `PATH`. | Run `sh install.sh` in a checkout, or the release's `install.sh` (README, Quickstart). If the line stays, read the `install.sh: commands jstack:` line on stderr. |
| `old hard commands jstack -> lacks <names>` | The tool was installed before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename` | The tool is installed under its old name, `jgauge`. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> tool jgauge, from before the rename, lacks <names>` | The old tool is installed, from before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename, is still installed` | Both the old tool and the new one are installed from this checkout. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> an install of <path>` | The tool runs the code of another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old hard commands jstack -> tool jgauge, an install of <path>` | The old tool is installed from another checkout. The install does not remove it. | Run `uv tool uninstall jgauge`, then `sh install.sh`. |
| `old hard commands jstack -> tool <tool> is installed from a release or an index, not as an editable install of this checkout` | A tool of that name came from a release, an index or a git URL. The install does not replace it. | Run `uv tool uninstall <tool>`, then `sh install.sh`. |
| `old hard commands jstack -> tool jstack is <version>, and its copy is <version>` | `jinstall` from a release runs with a copy of another version than the tool uv has. | Run `uv tool install <the release's wheel> --reinstall`, then `jinstall`. |
| `old hard commands jstack -> <command> is not on PATH: <directory> is not in it` | The tool is installed, and your shell does not find its commands. | Add `<directory>` to `PATH`. `uv tool update-shell` does it. |
| `old hard commands jstack -> <command> is shadowed by <path>` | Another program of that name is earlier on `PATH`. | Remove or rename the program at `<path>`. |
