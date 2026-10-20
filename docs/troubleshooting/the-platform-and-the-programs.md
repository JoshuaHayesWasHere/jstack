# The platform and the programs

| Line | Meaning | Do this |
|---|---|---|
| `missing hard linux -> this is <platform>` | jstack runs on Linux only. | Use a Linux machine. |
| `missing hard t3 -> the nightly build (on Arch: t3code-nightly-bin)` | No `t3` command is in `<home>/.t3/bin` or on `PATH`. | Install the nightly build of T3 Code and open the app once. |
| `old hard t3 -> t3 --version did not answer: open the app once` | The `t3` command is there and printed no version. | Open T3 Code once, then run the doctor again. |
| `old hard t3 -> <version> is the stable build, needs the nightly build (on Arch: t3code-nightly-bin)` | The stable build lacks tools that jstack calls, such as `t3_thread_launch`. | Install the nightly build. |
| `old hard t3 -> <version>, needs <floor> or newer` | The nightly is older than the oldest build jstack supports. | Update T3 Code. |
| `missing hard claude` | Claude Code is not on `PATH`. | Install Claude Code. |
| `missing hard uv` | `uv` is not on `PATH`. | Install `uv`. |
| `missing hard git` | `git` is not on `PATH`. | Install `git` 2.31 or newer. |
| `old hard git -> <version>, needs 2.31 or newer` | The `git` on `PATH` is too old. | Update `git`. |
| `missing hard jq` | `jq` is not on `PATH`. | Install `jq` 1.6 or newer. |
| `old hard jq -> <version>, needs 1.6 or newer` | The `jq` on `PATH` is too old. | Update `jq`. |
| `old hard <program> -> its version could not be read` | `git --version` or `jq --version` printed no version number. | Run that command yourself and see what is on `PATH` under that name. |
| `missing hard gh` | The GitHub CLI is not on `PATH`. | Install `gh`. |
| `missing hard gh sign-in -> gh auth login` | `gh auth token` exited non-zero. | Run `gh auth login`. |
| `missing optional lavish-axi -> npm install -g lavish-axi` | `lavish-axi` is not on `PATH`. A scout writes no visual page, and a question round is asked as text. | Run `npm install -g lavish-axi`, or leave it. |
| `missing optional state repo <path> -> not a git repo` | The homes' state tree is not a git repo, so `jbus snapshot` fails and alerts. | Run `git init <path>`, then add the remote as the next line says. |
| `missing optional state repo <path> -> no remote` | The state tree has no `origin`. Each `jbus snapshot` commits and then fails, and the first failure alerts. | Run `git -C <path> remote add origin <url>`, with a private repository of your own. |
