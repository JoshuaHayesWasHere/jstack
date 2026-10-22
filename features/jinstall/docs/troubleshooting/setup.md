# Setup

`sh install.sh --setup` prints one line for each need the doctor lists, in the same order, and exits 1 while a `hard` need is left to you.
An optional need that is missing gets the doctor's own words, `missing optional`, since it is a layer you may leave off.
A second run writes nothing.

| Line | Meaning | Do this |
|---|---|---|
| `done <name>` | This run wrote it: a config that was not there, or a part the install puts. | Nothing. |
| `already <name>` | It was there and `ok`. | Nothing. |
| `needs you <program> -> yay -S <package>` | The program is missing or too old. On a machine with no `pacman` the command is the program's name. | Install it, then run `--setup` again. |
| `needs you gh sign-in -> gh auth login` | `gh` is not signed in. | Run `gh auth login`. |
| `missing optional <name> -> <command>` | A layer you have not set up, such as the relay or the backup. Nothing is wrong without it, and setup's exit code does not count it. | Nothing, or run the command to set the layer up. |
| `missing optional jbus sign-in <path> -> jbus t3 login` | `jbus` has its config and no sign-in. | Run `jbus t3 login`, as [Set up jbus](../../../jbus/docs/jbus/set-up-jbus.md) says. |
| `missing optional limits <path> -> jgauge limits` | The reader of each account has not run yet. | Run `jgauge limits`, or wait 2 min for `jgauge-limits.timer`. |
| `missing optional state repo <path> -> git -C <path> remote add origin <url>` | The state tree has no remote, or with `git init <path> && ` first, is not a git repo, so the backup is off. | Nothing, or run it with a private repository of your own as `<url>`. |
| `missing optional hook <repo>/.git/hooks/<name> <name> -> a hook of the repo's own, ...` | A repo jstack works in, not jstack's own checkout, has a git hook of its own, which setup never writes over. The repo runs without jstack's hook, and setup's exit code does not count it. | Nothing, or add the line it names to your hook to run jstack's as well, as [jinstall](../jinstall.md) shows. |
| `needs you <name> -> <why>` | A file is there and its loader refuses it, or a part the install puts could not be put. Setup never writes over a file. | Find the doctor's line for `<name>` [above](the-doctor.md) and do what it says. |

Setup writes three configs, each only where no file is: `~/.config/jstack/config.toml`, with `user` from the first word of `git config user.name` and `timezone` from the machine, `~/.config/jstack/roles` with every role `inherit`, and `~/.config/jbus/config.toml`, mode 600, with `server` from the T3 sign-in beside it, else `http://127.0.0.1:3773`, and `dispatch = false`. The units are linked in the same run, since the jbus config is then there. `--uninstall` removes each of the three only while its bytes are the ones setup wrote, and says `kept <name> -> yours, it is not as setup wrote it` for one you changed.

`scripts/fresh-host.sh` runs `--setup` on a fresh host: a throwaway `archlinux` container with the checkout's `HEAD` cloned in, `uv`, `git` and `jq` installed, and stand-ins for `t3`, `claude`, `gh`, `lavish-axi` and `systemctl`.
It fails unless the doctor then says `doctor: ok`, a second `--setup` writes nothing, and the only `needs you` line left is `claude`.
It starts a container, so run it under the heavy-suite lock: `flock ~/.local/state/locks/heavy-suite.lock sh scripts/fresh-host.sh`.
