# jinstall

`jinstall` installs, checks and removes jstack on a machine.
A release installs it as a command, and it acts on the source the release's wheel carries, with no checkout.
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
| `jinstall` | Puts each part: the layouts, the skill links, the hooks, the status line, the private patterns, the commands and the units. One line a part. |
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
| The layouts are assembled from | `<tool venv>/share/jstack` | `<checkout>` |
| Units link to | `<tool venv>/share/jstack/templates/` | `<checkout>/templates/` |
| The commands are ok when | uv's tool `jstack` is the release's version, not editable | uv's tool `jstack` is an editable install of the checkout |
| Also checked | nothing more | the generated files are current (`generated files are current`), and the `pre-push` hook of a main checkout |

A release's `--uninstall` keeps the tool it runs from: `uv tool uninstall jstack` removes it after.
A new release replaces its source in place, so the layouts' links stay where they are.

## The layouts

The repo keeps each skill once, in its feature, and the install splits it out for each harness.
It assembles one layout for each harness at `~/.local/share/jstack/harness/<harness>/`, or under `$XDG_DATA_HOME`: `claude-code`, `codex` and `cursor`.
`~/.claude/skills` links each skill into Claude Code's layout, `~/.codex/skills` into Codex's, and `~/.agents/skills` into Cursor's.
A layout holds `skills/<name>/`, `playbooks/`, `principles/`, `templates/`, the hooks of its harness in `hooks/`, a `README.md`, and `source`, a link to the checkout or the release.
`skills/` and `templates/` are siblings, so `realpath ~/.claude/skills/<name>/../../templates` finds the templates.
Each file of a skill is a link to its file in the source, so an edit in a checkout is live with no install.
A new skill appears on the next install, once `python3 scripts/generate-jstack-trees.py` has listed it in `skills.json`.
A Markdown file with a link to a file the layout leaves out, such as a page of `docs/`, is written with that link pointed at GitHub, and the install's `--check` names it stale once its source changes.
The `README.md` of each layout names, for each skill, the tools and paths it asks for that the harness leaves out: Codex and Cursor have none of Claude Code's own tools, its home folder or its settings file.
`--check` prints one line for each layout, `ok` when it is as the install assembles it, and `old` with the first file that is stale.

## The checkout's own skills

A skill for working on jstack itself, such as `verify-jstack`, lives in its feature and is named in that feature's `feature.json` under `projectSkills`.
An install from a checkout links each one as `<checkout>/.claude/skills/<name>` for Claude Code and `<checkout>/.cursor/skills/<name>` for Cursor, which is where each reads a repo's own skills.
git tracks neither folder, so a checkout has them once `install.sh` has run in it.
The next install unlinks a link there whose skill no feature declares any more.
`--check` prints one line for each link: `ok`, `missing`, or `old` with where it points.
An install from a release makes none, and neither does a run under a HOME that is not your own for a checkout outside that HOME.
A linked worktree gets none: `install.sh` refuses to run from one under your own HOME, so a worktree reads a project skill from its feature's folder.

## Hook entries

The install writes one entry for each hook that `skills.json` lists, and `install.sh --uninstall` removes them: you write none of them by hand.
[The catalog](../../../CATALOG.md#hooks) lists every hook, and each feature's own page shows its entry as the install writes it.
Each harness reads its entries from one file: Claude Code from `~/.claude/settings.json`, and Codex from `~/.codex/hooks.json`.
Each entry runs the script from that harness's layout, `<layout>/hooks/<script>`.
Cursor gets no hook entry.
The status line is Claude Code's, a `statusLine` in `~/.claude/settings.json`: the install writes it when the key is absent, replaces one that runs the same script from another layout, and leaves a status line of your own as it is.
A git hook is no settings entry: the install links `.git/hooks/<name>` of the main checkout to its script, and the repo's worktrees run it too.
The install leaves every other key of those files as it was.

## Releasing

A release is cut from a clean `main` that is `origin/main`, by one command:

```sh
make release
```

It checks that `v<version>`, the version of `pyproject.toml`, is the version of `plugin.json` too (`make release-tag`), then tags it and pushes the tag.
Where the push fails, it drops the tag again, so the next `make release` starts clean.
The tag runs `.github/workflows/release.yml`.
It checks that the tag is the version of both `pyproject.toml` and `plugin.json` (`make release-tag`), then runs `make check` and `make dist`.
It installs the wheel in a `HOME` of its own and runs `jinstall --check`, and only then makes the GitHub release.
The release's assets are what `make dist` writes: the wheel, the sdist, and `install.sh` with the version written in.

A version bump is an ordinary pull request: `uv version --bump <major|minor|patch>`, the same version in `plugin.json`, and `make trees`, which copies it into the harness.
