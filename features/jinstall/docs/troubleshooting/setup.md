# Setup

`jinstall --setup` prints one line for each need the doctor lists, in the same order, and exits 1 while a `hard` need is left to you.
For a missing optional need, setup prints the doctor's own words, `missing optional`, because it is a layer you may leave off.
A second run writes nothing.

| Line | Meaning | Do this |
|---|---|---|
| `done <name>` | This run wrote it: a config that was not there, or a part the install puts. | Nothing. |
| `already <name>` | It was there and `ok`. | Nothing. |
| `needs you <program> -> <command>` | The program is missing or too old. `<command>` is `brew install <formula>` on macOS, `yay -S <package>` on a machine with `pacman`, and the program's name on any other Linux machine. On Windows it is `install jstack inside WSL2`. | Install the program, as [The platform and the programs](the-platform-and-the-programs.md#where-to-get-each-program) shows, then run `--setup` again. |
| `needs you gh sign-in -> gh auth login` | `gh` is not signed in. | Run `gh auth login`. |
| `missing optional <name> -> <command>` | A layer you have not set up, such as the relay or the backup. Nothing is wrong without it, and setup's exit code does not count it. | Nothing, or run the command to set the layer up. |
| `missing optional jbus sign-in <path> -> jbus t3 login` | `jbus` has its config and no sign-in. | Run `jbus t3 login`, as [Set up jbus](../../../jbus/docs/jbus/set-up-jbus.md) says. |
| `missing optional limits <path> -> jgauge limits` | `jgauge limits` has not read the account yet. | Run `jgauge limits`, or wait 2 min for `jgauge-limits.timer`. |
| `missing optional state repo <path> -> git -C <path> remote add origin <url>` | The state tree has no remote, so the backup is off. When the command starts with `git init <path> && `, the state tree is not a git repo yet. | Nothing, or run it with a private repository of your own as `<url>`. |
| `missing optional hook <repo>/.git/hooks/<name> <name> -> a hook of the repo's own, ...` | A repo jstack works in has a git hook of its own, which setup never writes over. The repo runs without jstack's hook, and setup's exit code does not count it. | Nothing, or add the line it names to your hook to run jstack's as well, as [jinstall](../jinstall.md#git-hooks-in-your-repos) shows. |
| `needs you <name> -> <why>` | A file is there and its loader refuses it, or the install could not put one of its parts. Setup never writes over a file. | Find the doctor's line for `<name>` [above](the-doctor.md) and do what it says. |

Setup writes three configs, each only where no file is there yet:

- `~/.config/jstack/config.toml`, with `user` from the first word of `git config user.name` and `timezone` from the machine.
- `~/.config/jstack/roles`, with every role `inherit`.
- `~/.config/jbus/config.toml`, mode 600, with `dispatch = false` and a `server`.
  `server` is the server that `t3.json`, the T3 sign-in in the same folder, names.
  When `t3.json` names no server, `server` is `http://127.0.0.1:3773`.

Setup puts the units in the same run, as links on Linux and launchd agents on macOS, because the jbus config exists by then.
`jinstall --uninstall` removes each of the three only while its bytes are the ones setup wrote, and says `kept <name> -> yours, it is not as setup wrote it` for one you changed.
