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
| `missing optional lavish-axi -> npm install -g lavish-axi` | `lavish-axi` is not on `PATH`. It is Lavish, a local editor that opens an HTML page in your browser for you to mark up, and hands your notes back to the agent. Without it, a scout writes no visual page, and a question round comes as text. | Run `npm install -g lavish-axi`, or leave it. |
| `missing optional state repo <path> -> not a git repo` | The homes' state tree is not a git repo, so `jbus snapshot` fails, and the backup is off. | Run `git init <path>`, then add the remote as the next line says. |
| `missing optional state repo <path> -> no remote, so the backup is off` | The state tree has no `origin`. Each `jbus snapshot` commits in the state tree and pushes nothing. `jbus-snapshot.timer` is off, and nothing sends alerts. | Nothing, or run `git -C <path> remote add origin <url>`, with a private repository of your own, then `jinstall`. |
| `old optional state repo <path> -> needs gitleaks, which reads each snapshot for secrets` | The state tree has a remote and there is no `gitleaks`, so a snapshot would commit nothing and fail. The install leaves `jbus-snapshot.timer` as it is. | Install `gitleaks`, then run `jinstall`. |

## Where to get each program

Each program's own page has the install steps for every platform it supports.
On a machine with `pacman`, `jinstall --setup` names the Arch package as `yay -S <package>`, and on any other machine it names the program.
The last column gives the Arch package as one example.

| Program | Install page | Arch package |
|---|---|---|
| T3 Code, the nightly build | [pingdotgg/t3code](https://github.com/pingdotgg/t3code) | `t3code-nightly-bin` |
| Claude Code, `claude` | [Set up Claude Code](https://code.claude.com/docs/en/setup) | `claude-code` |
| `uv` | [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) | `uv` |
| `git` | [git downloads](https://git-scm.com/downloads) | `git` |
| `jq` | [Download jq](https://jqlang.org/download/) | `jq` |
| `gh`, the GitHub CLI | [GitHub CLI installation](https://github.com/cli/cli#installation) | `github-cli` |
| `gitleaks`, for the backup only | [Installing gitleaks](https://github.com/gitleaks/gitleaks#installing) | `gitleaks` |
| `lavish-axi`, optional | `npm install -g lavish-axi`, from [kunchenguid/lavish-axi](https://github.com/kunchenguid/lavish-axi) | none, it comes from npm |
