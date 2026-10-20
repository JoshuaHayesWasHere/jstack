# Setup

`sh install.sh --setup` prints one line for each need the doctor lists, in the same order, and exits 1 while a `hard` need is left to you. A second run writes nothing.

| Line | Meaning | Do this |
|---|---|---|
| `done <name>` | This run wrote it: a config that was not there, or a part the install puts. | Nothing. |
| `already <name>` | It was there and `ok`. | Nothing. |
| `needs you <program> -> yay -S <package>` | The program is missing or too old. On a machine with no `pacman` the command is the program's name. | Install it, then run `--setup` again. |
| `needs you gh sign-in -> gh auth login` | `gh` is not signed in. | Run `gh auth login`. |
| `needs you jbus sign-in <path> -> jbus t3 login` | `jbus` has its config and no sign-in. | Run `jbus t3 login`, as [Set up jbus](../jbus/set-up-jbus.md) says. |
| `needs you limits <path> -> claude` | Only Claude Code's status line writes the limits file. | Start one Claude Code session. |
| `needs you state repo <path> -> git -C <path> remote add origin <url>` | The state tree has no remote, or with `git init <path> && ` first, is not a git repo. | Run it with a private repository of your own as `<url>`. |
| `needs you <name> -> <why>` | A file is there and its loader refuses it, or a part the install puts could not be put. Setup never writes over a file. | Find the doctor's line for `<name>` [above](../troubleshooting.md) and do what it says. |

Setup writes three configs, each only where no file is: `~/.config/jstack/config.toml`, with `user` from the first word of `git config user.name` and `timezone` from the machine, `~/.config/jstack/roles` with every role `inherit`, and `~/.config/jbus/config.toml`, mode 600, with `server` from the T3 sign-in beside it, else `http://127.0.0.1:3773`, and `dispatch = false`. The units are linked in the same run, since the jbus config is then there. `--uninstall` removes each of the three only while its bytes are the ones setup wrote, and says `kept <name> -> yours, it is not as setup wrote it` for one you changed.

`scripts/fresh-host.sh` runs `--setup` on a fresh host: a throwaway `archlinux` container with the checkout's `HEAD` cloned in, `uv`, `git` and `jq` installed, and stand-ins for `t3`, `claude`, `gh`, `lavish-axi` and `systemctl`. It fails unless the doctor then says `doctor: ok`, a second `--setup` writes nothing, and the only `needs you` lines left are `jbus t3 login` and `claude`. It starts a container, so run it under the heavy-suite lock: `flock ~/.local/state/locks/heavy-suite.lock sh scripts/fresh-host.sh`.
