# Contributing to jstack

jstack takes bug reports, and pull requests that fix a bug or improve a page.
For a larger change, open an issue first, so that we can agree on the shape before you write it.
To report a vulnerability, follow [SECURITY.md](SECURITY.md), and do not open an issue for it.

## Report a bug

Open an issue with the **Bug report** template.
It asks for these:

- What you ran, what you saw, and what you expected to see.
- The version: the `jstack` line of `uv tool list`, such as `jstack v0.1.0`.
- The output of `jinstall --doctor`, in full.
- The T3 Code version, from `t3 --version`.

Read the output before you paste it, and take out what you do not want in public.

## Set up a checkout

Clone the repo and install jstack from the checkout:

```sh
git clone https://github.com/JoshuaHayesWasHere/jstack
cd jstack
sh install.sh --setup
```

`install.sh` takes every verb of `jinstall`, and installs the commands as an editable install of the checkout.
`sh install.sh --check` checks the install, and every line must start with `ok`.
In a checkout that is not installed, run a command as `uv run --project <checkout> <command>`.

[jinstall](features/jinstall/docs/jinstall.md#a-release-and-a-checkout) says what a checkout's install does that a release's does not.
[The lines of a checkout](features/jinstall/docs/troubleshooting/working-on-jstack.md) has each line that only a checkout's install prints, with what to do.

## What is in the repo

| Path | Holds |
|---|---|
| `features/` | Each feature in a folder of its own, `features/<name>/`: its skills, playbooks, templates, hooks, units, its command's package, tests and docs. `~/.{claude,agents,codex}/skills/<name>` link into the layout the install assembles from them. |
| `features/principles/` | One skill per working principle, `principle-<name>`, which a playbook step names where it relies on it. |
| `install.sh` | Installs jstack from this checkout. Piped to `sh` from a release, it installs that release. |
| `THIRD_PARTY.md` | The files taken from other projects, with their sources and licenses. |
| `testing/` | The shared test tooling, and in `testing/verify/` its verify page. |

`README.md` and `CATALOG.md` hold blocks that `scripts/generate-jstack-trees.py` writes.
Edit the source, such as a `feature.json`, then run `make trees`.
Never edit the block itself.

## Run the checks

The Python code is one `uv` project.

| | Command |
|---|---|
| Check | `make check` |
| Lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Test | `uv run pytest` |

`make check` is the one check command.
It runs the lint and the tests above, in that order, and stops at the first that fails.
`make check-fast` runs the lint and only the tests a change reaches.
A test reaches a file it imports, a file whose path it spells, and a file that a file it reads includes.
A skill or page includes the file beside it that one of its lines says to read now (``read `$T/../skills/<its folder>/<name>.md` now``), so a change to that file runs the tests that read the skill, up the chain of includes.

When a check fails, [A test of `make check` failed on a bound](features/repo-guards/docs/troubleshooting/a-test-of-make-check-failed-on-a-bound.md) and [`make check-fast` stopped before the tests](features/repo-guards/docs/troubleshooting/make-check-fast-stopped-before-the-tests.md) have the common causes.

`features/repo-guards/tests/test_no_comments.py` fails `make check` on a comment in the files under `src/`, `hooks/*.sh`, `install.sh` and `tests/*.py`, other than a shebang, `# noqa`, `# type:` or `# pragma`.

`verify-jstack` drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox, with stand-ins for T3 Code, GitHub and the webhook.
Its folder is `features/verify-jstack/project-skill/`, which `install.sh` links as the checkout's `.claude/skills/verify-jstack` and `.cursor/skills/verify-jstack`, both untracked.
A linked worktree has no such link, and reads the skill from `features/verify-jstack/project-skill/`, the folder `skills.json` names under `projectSkills`.

## Open a pull request

1. Fork the repo, and make a branch from `main` for one change.
2. Make the change, with a test where the repo has tests for that code.
3. Run `make check`, and fix what it finds.
4. Commit with a message that says what the change does.
	Leave out any `Co-authored-by` line that credits an AI tool.
	CI fails a pull request that carries one in its title, its body or any commit.
	In a checkout, the `commit-msg` hook that `install.sh` links strips such a line for you.
5. Open the pull request against `main`.
	The template gives the body its headings: Why, What changed, Scope, Tradeoffs, Blast radius and Verification.

A maintainer approves each CI run of a pull request from a fork, since the repo asks approval for every outside contributor.
A run waits for that approval each time you push, also when you push the fixes of a review.
The maintainer reviews the pull request and leaves the findings as comments on it.
Push the fixes to the same branch.
The maintainer merges it once the findings are fixed and `check` and `borders` pass.

## The repo's CI

| Workflow | Runs on | What it does |
|---|---|---|
| `check` | each pull request, and each push to `main` and to an integration branch | On a pull request, `make check-fast` and the check for AI co-author lines. On a push, `make check`. |
| `borders` | each pull request | `scripts/lint-borders.py`: every path has one owner, and a pull request that touches two features carries the `cross-cutting` label, which a maintainer adds. |
| `browser` | each night, a `v<version>` tag, and each published release | `make check-browser`, the tests that open a real browser. |
| `release` | a `v<version>` tag | Checks, builds and publishes the release. |
| `pstack-drift` | each Monday | `make pstack-drift`: what changed upstream in the files taken from pstack. |

A pull request into `main` needs `check` and `borders` to pass before it merges.

## Release

One command cuts a release from a clean `main` that is `origin/main`:

```sh
make release
```

It checks that `v<version>`, the version of `pyproject.toml`, is the version of `plugin.json` too (`make release-tag`), then tags it and pushes the tag.
If the push fails, it drops the tag again, so the next `make release` starts clean.
The tag runs `.github/workflows/release.yml`.
It checks that the tag is the version of both `pyproject.toml` and `plugin.json` (`make release-tag`), then runs `make check` and `make dist`.
It installs the wheel in a `HOME` of its own and runs `jinstall --check`, and only then makes the GitHub release.
The release's assets are what `make dist` writes: the wheel, the sdist, and `install.sh` with the version written in.

A version bump is an ordinary pull request: run `uv version --bump <major|minor|patch>`, write the same version in `plugin.json`, and run `make trees`, which copies it into the harness.
