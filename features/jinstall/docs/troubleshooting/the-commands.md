# The commands

A release installs the nine commands as `uv`'s tool `jstack`.
A checkout installs them another way.
[The lines of a checkout](working-on-jstack.md#the-commands-of-a-checkout) lists its lines.

| Line | Meaning | Do this |
|---|---|---|
| `missing hard commands jstack -> uv has no tool jstack: uv tool install <the release's wheel> --reinstall` | `uv` has no tool `jstack`, for example because `jinstall` ran some other way. | Install the release again, as [jinstall](../jinstall.md#install) shows. |
| `old hard commands jstack -> tool jstack is <version>, and its plugin is <version>` | `jinstall` runs from a release of one version, and the tool `uv` has is another version. | Install the release again, as [jinstall](../jinstall.md#install) shows, then run `jinstall`. |
| `old hard commands jstack -> tool jstack is an editable install of <path>` | The tool runs the code of a checkout, not of a release. | Run `uv tool uninstall jstack`, then install the release again. |
| `old hard commands jstack -> lacks <names>` | The tool lacks those commands. | Install the release again, then run `jinstall`. |
| `old hard commands jstack -> <command> is not on PATH: <directory> is not in it` | The tool is installed, but your shell does not find its commands. | Add `<directory>` to `PATH`. `uv tool update-shell` does it. |
| `old hard commands jstack -> <command> is shadowed by <path>` | Another program of that name is earlier on `PATH`. | Remove or rename the program at `<path>`. |
