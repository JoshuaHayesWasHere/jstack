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
Keep the checkout where it is, and run `install.sh` in the main checkout, not in a worktree.
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
| Check of a change | `make check-fast` |
| Lint | `make lint` |
| Test | `make test`, or `make test TESTS=<files>` for some files |

`make check` is the one check command.
It runs `make lint`, then `make test`, and stops at the first that fails.
`make lint` runs `features/writing/scripts/comment_lint.py` on the files the branch changed, which only warns, then the repo standard's `stale` guard, which runs `scripts/generate-jstack-trees.py --check` as `.repo-standard.yml` names it, `scripts/check-jstack-docs.py`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run pyrefly check --summary=none features/*/src`, which type-checks each feature's `src`.
`make test` runs `uv run pytest` on several workers with `-m "not browser"`, so it leaves out the tests that open a real browser.
`make check-browser` runs those.

`make check-fast` is the check of a change against `BASE`, `origin/main` by default.
It first runs `features/writing/scripts/prose_lint.py`, which fails a Markdown line the diff adds that holds two sentences.
Then it runs `make lint`, and `make test` on only the tests the change reaches.
Where `scripts/select_tests.py` selects `all`, it runs `make check` instead.
A test reaches a file it imports, a file whose path it spells, and a file that a file it reads includes.
A skill or page includes the file beside it that one of its lines says to read now (``read `$T/../skills/<its folder>/<name>.md` now``), so a change to that file runs the tests that read the skill, up the chain of includes.

When a check fails, [A test of `make check` failed on a bound](features/repo-guards/docs/troubleshooting/a-test-of-make-check-failed-on-a-bound.md) and [`make check-fast` stopped before the tests](features/repo-guards/docs/troubleshooting/make-check-fast-stopped-before-the-tests.md) have the common causes.

`features/repo-guards/tests/test_no_comments.py` fails `make check` on a comment in the files the `comments` part of `.repo-standard.yml` sweeps, other than a shebang, `# type:` or `# pragma`.
It fails a `# noqa` too: write the code so that ruff reports nothing on it.

`verify-jstack` drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox, with stand-ins for T3 Code and GitHub.
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
The maintainer merges it once the findings are fixed and `check`, `borders` and `macos` pass.

## The repo's CI

| Workflow | Runs on | What it does |
|---|---|---|
| `check` | each push of a pull request, a draft too, each push to `main`, and by hand | On a pull request, a `reuse` job first: where a green run already checked the same tree, the pull request reuses it and runs nothing more. The `reuse` job also checks for AI co-author lines, and a `lint` job beside it runs the prose lint and `make lint`. Without a reuse, the `reuse` job also runs `scripts/select_tests.py --pull-request --parts 8 HEAD^1 HEAD` in plain `python3`: it selects the tests the change needs, where `--pull-request` has an import reach only the tests near the change (the tests that import a changed module, and those that import a module that names a name the diff touched), adds the tests that failed on `main` in the last 30 days, and deals the selected files out to 8 parts, `check 1 of 8` to `check 8 of 8`, which run side by side, each `make test` on its own files. On a push to `main`, `make check` in 4 parts, skipped where a green tree marker shows the tree passed already. |
| `macos` | each pull request, and each push to `main` | On macOS, the tests of `testing/macos-quick.txt` that the change reaches, selected by `scripts/select_tests.py --within`. |
| `macos-nightly` | each night, and by hand | `make check` on macOS over `main`, the whole suite. |
| `borders` | each pull request, and each change of its labels | `scripts/lint-borders.py`: every path has one owner, and a pull request that touches two features carries the `cross-cutting` label, which a maintainer adds. Then `features/jbus/scripts/kept_shots.py`: a pull request that changes a kept shot of the view changes nothing else. |
| `browser` | each night, a `v<version>` tag, each published release, by hand, and a pull request into `main` that changes the view, its browser tests, their kept shots or `browser.yml` | `make check-browser`, the tests that open a real browser. |
| `release` | a `v<version>` tag | Builds and publishes the release. It runs no check of its own: `make release-green` reuses `main`'s check of the same tree. |
| `pstack-drift` | each Monday, and by hand | `make pstack-drift`: what changed upstream in the files taken from pstack. |

A pull request into `main` needs `check`, `borders` and `macos` to pass before it merges.

## Release

One command cuts a release from a clean `main` that is `origin/main`:

```sh
make release
```

It checks that `v<version>`, the version of `pyproject.toml`, is the version of `plugin.json` too (`make release-tag`).
Then `make release-green` checks that a green run of `check.yml` left the marker `green-tree-<tree>` for the tree of `HEAD`.
`main`'s full run leaves that marker once its suite passes, and keeps it 7 days.
Without the marker, `make release-green` fails and names the fix: wait for `main`'s run to pass, or, where the marker expired, run `gh workflow run check.yml --ref main`.
`make release` refuses to tag until the marker exists, then tags it and pushes the tag.
If the push fails, it drops the tag again, so the next `make release` starts clean.
The tag runs `.github/workflows/release.yml`.
It checks that the tag is the version of both `pyproject.toml` and `plugin.json` (`make release-tag`), then runs `make release-green` again on the tag's checkout and `make dist`.
The tag runs no check of its own: the tag's tree is `main`'s, which already passed.
It installs the wheel in a `HOME` of its own and runs `jinstall --check`, and only then makes the GitHub release.
The release's assets are what `make dist` writes: the wheel, the sdist, and `install.sh` with the version written in.

A version bump is an ordinary pull request: run `uv version --bump <major|minor|patch>`, and write the same version in `plugin.json`.
The pull request's check fails while the two differ, since `scripts/generate-jstack-trees.py --check` holds `plugin.json` to `pyproject.toml`.
