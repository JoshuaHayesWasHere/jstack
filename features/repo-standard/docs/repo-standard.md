# repo-standard

`repo-standard` holds a repo to [the repo standard](standard.md).
Its verb `conform` checks every rule of the standard at the version the repo pins, and its other verbs run one guard each, as [the guards' page](guards.md) says.
It reads the repo's `.repo-standard.yml` and uses the Python standard library alone.

## Run it from any repo

A repo needs no copy of the tool: `uvx` runs it from jstack at the tag the repo pins.

```sh
uvx --from git+https://github.com/JoshuaHayesWasHere/jstack@repo-standard-v1 repo-standard conform
```

In jstack, the command is on the path of the project's environment, so `uv run repo-standard conform` runs it.
CI's `lint` job in `.github/workflows/check.yml` runs it there, so the required check `check` fails when it does.

## The verbs

| Verb | What it does |
|---|---|
| `conform` | Checks every rule of the standard, and exits 1 on an error. |
| `borders` | Checks the layout's borders and, with a base, that a change touches one feature. |
| `stale` | Runs each generator in its check mode, which writes nothing. |
| `docs` | Checks that the docs name only paths and make targets the tree has. |
| `size` | Checks each file's length against its cap. |
| `comments` | Checks that code holds no plain comment. |

Every verb takes `--root` for another checkout, and `--config` for another config file than `<root>/.repo-standard.yml`.
`borders` alone reads `--base <ref>`, `--labels a,b` and `--hard`, which [the guards' page](guards.md) explains.
`conform` alone reads `--upstream` and `--list`.
A verb exits 2 when it cannot read the config or the tree.

## conform

`repo-standard conform` runs one check for each `###` rule of `features/repo-standard/docs/standard.md`.
A rule's id is its heading's anchor, so `standard.md#a-change-selects-its-tests` is the text of the rule `a-change-selects-its-tests`.
`repo-standard conform --list` prints each rule's level and id, and checks nothing.

It prints one line for each fault, each waiver and each note, then a count:

```text
error a-change-selects-its-tests: Makefile: has no `select` target
waiver every-file-has-a-place: the layout moves into this file in the next pull request
note: repo-standard-v2 is out, and this repo pins v1: move the pin when ready
conform repo-standard-v1, 34 rules: errors 1, warnings 0, waived 1
```

### Levels

Each rule has a level, which `--list` shows.
A fault of an `error` rule fails the run.
A fault of a `warn` rule prints and fails nothing.

### How each rule is checked

Most rules are checked from the tree: a guard runs, or the tool reads the Makefile's targets, the workflows under `.github/workflows/`, the manifests or the config.
A guard whose part the config does not set is a fault of its rule, so a repo never passes a rule it never set up.

Some rules no check of the tree can judge in every stack, such as "a test runs the code".
For each of those, the config's `enforced-by` names the files that enforce the rule in the repo.
Each named file must be tracked, and must be a test file, a workflow, or a file a workflow or the Makefile names by its path.
A file nothing runs does not meet a rule.
The rules met this way are these:

- `a-commands-page-matches-its-help`
- `new-prose-has-one-sentence-per-line`
- `shell-runs-on-macos-as-well-as-on-linux`
- `a-test-runs-the-code`
- `a-shared-path-forces-the-whole-suite`
- `a-pair-of-trees-passes-once`
- `a-passing-tree-leaves-a-marker`
- `every-deploy-entry-refuses-a-tree-that-is-not-green-main`, which also needs the config's `deploy` part

### Waivers

The config may waive a rule, with a reason:

```yaml
waivers:
  - rule: a-change-selects-its-tests
    reason: make check-fast calls scripts/select_tests.py by name until the select target lands
```

A waived rule still runs, and its faults print as `waived` and fail nothing.
Every waiver prints with its reason.
A waiver with no reason fails the run, and so does a waiver for a rule the standard does not have.
A waived rule that passes prints a note that its waiver can go.

### Versions

The config pins a version of the standard as `standard: N`, for the tag `repo-standard-vN` of jstack.
The tool is the standard at one version, and judges by that version's rules, so a pin of another version fails the rule `a-breaking-change-takes-a-new-version`.

The tool lists the `repo-standard-vN` tags of `--upstream`, by default jstack on GitHub, and prints a note when a newer version is out.
The note fails nothing: a repo moves its pin when it chooses to.
When the tags cannot be listed, the tool prints a note and goes on.
`--upstream ""` skips the lookup.

## The config's parts for conform

Beside the guards' parts, which [the guards' page](guards.md) lists, `conform` reads these keys of `.repo-standard.yml`:

```yaml
standard: 1
deploy: [make release]
enforced-by:
  a-test-runs-the-code: [tests/test_run_not_read.py]
waivers:
  - rule: a-change-selects-its-tests
    reason: the select target lands with the python-uv adapter
```

`deploy` lists each deploy entry, and `deploy: []` says the repo deploys nothing.
Each entry names `deploy` or `release`, so the `touches prod` gate stops an agent that runs it.
