# The platform and the programs

| Line | Meaning | Do this |
|---|---|---|
| `missing hard platform -> this is win32: run jstack inside WSL2` | jstack does not run on Windows itself. | Install WSL2 and run jstack inside its Linux distribution. |
| `missing hard platform -> this is <platform>: jstack runs on Linux and macOS` | jstack runs on Linux and on macOS, and on no other platform. | Use a Linux machine or a Mac with Apple Silicon. |
| `missing hard t3 -> T3 Code 0.1.2 or newer, stable or nightly (<where>)` | No `t3` command is in `<home>/.t3/bin` or on `PATH`. `<where>` is `on Arch: t3code-bin`, or on macOS `on a Mac with Apple Silicon: brew install --cask t3-code`. | Install T3 Code, the stable or the nightly build, and open the app once. T3 Code has no `t3` command for an Intel Mac, so jstack does not run there. |
| `old hard t3 -> t3 --version did not answer: open the app once` | The `t3` command is there and printed no version. | Open T3 Code once, then run the doctor again. |
| `old hard t3 -> <version>, needs 0.1.2-nightly.20261022.3526 or newer` | The build, stable, nightly or preview, is older than the oldest one jstack supports, and may lack tools that jstack calls, such as `t3_thread_launch`. A release ranks after each of its own nightlies, so stable `0.1.2` meets it. | Update T3 Code to stable `0.1.2` or a newer build. |
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
On macOS, `jinstall --setup` names the Homebrew command, `brew install <formula>`.
On a Linux machine with `pacman`, it names the Arch package as `yay -S <package>`, and on any other Linux machine it names the program.
On Windows, it says to run jstack inside WSL2, and there each program is installed in the Linux distribution.

| Program | Install page | Homebrew, on macOS | Arch package |
|---|---|---|---|
| T3 Code, stable or nightly | [pingdotgg/t3code](https://github.com/pingdotgg/t3code) | `brew install --cask t3-code`, on Apple Silicon | `t3code-bin`, or `t3code-nightly-bin` for the nightly |
| Claude Code, `claude` | [Set up Claude Code](https://code.claude.com/docs/en/setup) | `brew install --cask claude-code` | `claude-code` |
| `uv` | [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) | `brew install uv` | `uv` |
| `git` | [git downloads](https://git-scm.com/downloads) | `brew install git` | `git` |
| `jq` | [Download jq](https://jqlang.org/download/) | `brew install jq` | `jq` |
| `gh`, the GitHub CLI | [GitHub CLI installation](https://github.com/cli/cli#installation) | `brew install gh` | `github-cli` |
| `gitleaks`, for the backup only | [Installing gitleaks](https://github.com/gitleaks/gitleaks#installing) | `brew install gitleaks` | `gitleaks` |
| `lavish-axi`, optional | `npm install -g lavish-axi`, from [kunchenguid/lavish-axi](https://github.com/kunchenguid/lavish-axi) | none, it comes from npm | none, it comes from npm |
