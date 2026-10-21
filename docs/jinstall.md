# jinstall

`jinstall` installs, checks and removes jstack on a machine.
A release installs it as a command, and it acts on the harness copy the release's wheel carries, with no checkout.
In a checkout, `sh install.sh` runs the same code, before any command is on `PATH`.

## Install

From a release, with nothing but `curl` and a shell:

```sh
curl -fsSL https://github.com/JoshuaHayesWasHere/jstack/releases/latest/download/install.sh | sh
```

The script installs `uv` when it is missing, runs `uv tool install` on that release's wheel, and then runs `jinstall --setup`.
The same can be done by hand, with `uv` already there:

```sh
uv tool install git+https://github.com/JoshuaHayesWasHere/jstack@v<version>
jinstall --setup
```

From a checkout, `sh install.sh --setup` does the same for the checkout, and installs the commands as an editable install of it.

## The verbs

| Verb | What it does |
|---|---|
| `jinstall` | Puts each part: the skill links, the hooks, the status line, the private patterns, the commands and the units. One line a part. |
| `jinstall --check` | Prints the same lines and writes nothing. Every line starts with `ok` on a machine that is set up. |
| `jinstall --setup` | Walks every need once, in order: `done <name>`, `already <name>`, or `needs you <name> -> <command>`. |
| `jinstall --doctor` | Prints one line for each requirement, then the lines of `--check`, and `doctor: ok` last. |
| `jinstall --uninstall` | Takes away what it put, and keeps what is yours. |

`--setup` links each skill into `~/.{claude,agents,codex}/skills`, adds the hooks to `~/.claude/settings.json` and `~/.codex/hooks.json`, and sets a status line that writes the limits file, unless you have a status line of your own.
Where no file is, it writes your jstack config, a role map where every role inherits, and a `jbus` config that launches nothing (`dispatch = false`), and then links the `jbus` units.
Run each command a `needs you` line names, such as `gh auth login` or `jbus t3 login`, then run it again.
A second run writes nothing.

## A release and a checkout

| | A release | A checkout |
|---|---|---|
| Runs as | `jinstall [<verb>]` | `sh install.sh [<verb>]`, or `jinstall` of an editable install |
| Links and hooks point into | `<tool venv>/share/jstack/claude-code` | `<checkout>/harness/jstack/claude-code` |
| Units link to | the copy's `templates/` | `<checkout>/templates/` |
| The commands are ok when | uv's tool `jstack` is the copy's version, not editable | uv's tool `jstack` is an editable install of the checkout |
| Also checked | nothing more | the copy is current (`harness/ is current`), and the `pre-push` hook of a main checkout |

A release's `--uninstall` keeps the tool it runs from: `uv tool uninstall jstack` removes it after.
A new release replaces the copy in place, so the links stay where they are.

## Releasing

A release is cut from a clean `main` that is `origin/main`, by one command:

```sh
make release
```

It tags `v<version>`, the version of `pyproject.toml`, and pushes the tag.
The tag runs `.github/workflows/release.yml`.
It checks that the tag is the version of both `pyproject.toml` and `plugin.json` (`make release-tag`), then runs `make check` and `make dist`.
It installs the wheel in a `HOME` of its own and runs `jinstall --check`, and only then makes the GitHub release.
The release's assets are what `make dist` writes: the wheel, the sdist, and `install.sh` with the version written in.

A version bump is an ordinary pull request: `uv version --bump <major|minor|patch>`, the same version in `plugin.json`, and `make trees`, which copies it into the harness.
