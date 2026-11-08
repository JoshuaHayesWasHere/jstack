# The standard's guards

Four guards hold a repo to the standard: its layout's borders, its generated files, its docs and its size and comment limits.
Each reads what it checks from the repo's `.repo-standard.yml` and its feature manifests, not from code, so any repo runs them as they are.
They use the Python standard library alone, so CI runs them before any install.

## Run a guard

Run a guard from the repo's checkout, with the package's source on the path:

```sh
PYTHONPATH=<jstack>/features/repo-standard/src python3 -m repo_standard borders --hard
```

The guards are `borders`, `stale`, `docs`, `size` and `comments`.
`--root` names another checkout, and `--config` another config file.
A guard prints one line for each fault it finds and exits 1 on any.
`borders` prints each fault as a warning GitHub reads as an annotation, and exits 1 only under `--hard`.
With `--base <ref>` it also reads the diff from that ref, and `--labels a,b` gives the pull request's labels.
A guard exits 2 when it cannot read the config, the tree or the base, and when the config has no part for it, so a guard that cannot look never passes.

## The config

`.repo-standard.yml` sits at the repo's root.
It is YAML in a small subset: maps and lists by indent, flow lists such as `[a, "b"]`, strings, numbers, `true`, `false` and `#` comments.
The guards refuse anything else, and refuse a key the standard does not know, so a misspelt key fails instead of turning a check off.

```yaml
standard: 1
features: features
manifest-schema: schemas/feature.core.schema.json
layout: [features/, schemas/, scripts/, .github/]
owners:
  INFRA: [Makefile, README.md, "schemas/**", ".github/**"]
cross-cutting: cross-cutting
generators:
  - [python3, scripts/generate-jstack-trees.py]
docs:
  pages: ["*.md", "features/*/docs/**/*.md"]
  exclude: []
  roots: [features, scripts, schemas]
  elsewhere:
    scripts/deploy: another repo's deploy command
size:
  - files: ["features/*/src/**/*.py"]
    cap: 800
    over:
      features/jbus/src/jbus/queue.py: 1219
comments:
  files: ["features/*/src/**"]
  exclude: ["features/*/src/**/fixtures/**"]
  readers:
    .go: script
  allow: ["# type:", "# pragma"]
  links: [.js, .html]
```

A glob's `**` crosses folders, and its `*` and `?` stay in one.
Each path is from the repo's root.

## borders

A feature is a folder of `features`, and it owns that folder and every path in it.
Its `feature.json` validates against the schema `manifest-schema` names, and names its folder.
The schema is read with the subset of JSON Schema the standard's schemas use, and a `$ref` may name a file beside it, which is how a repo's own extension takes the standard's core, `schemas/feature.core.schema.json`.
The repo owns the paths its `owners` globs match, each group by its name.

The guard warns on a feature folder whose manifest is missing, is not JSON, breaks the schema or names another folder.
It warns on a path with no owner or with two, and on a path outside each folder of `layout` that the repo does not own.
With `--base`, it warns on a diff that changes two features or more, unless the pull request carries the `cross-cutting` label.

The code is `features/repo-standard/src/repo_standard/borders.py`.

## stale

Each command of `generators` is a list of words, run with `--check` appended in the repo's root, with no shell.
In `--check` mode a generator writes nothing and exits 1 when what it would write differs from the file on disk.
A generator that exits other than 0, or cannot run, fails the guard with the last lines it printed.

The code is `features/repo-standard/src/repo_standard/stale.py`.

## docs

The pages are the files `docs.pages` matches and `docs.exclude` does not.
A path on a page that starts at a folder of `docs.roots` exists in the tree, or is a key of `docs.elsewhere`, whose value says why it does not.
A path with a placeholder or a glob after it, such as `features/<name>/`, is a pattern and is not read.
A path with a `/` or a word before it starts somewhere else and is not read either.

A `make` command, in a code span or on a line of a fenced block, names only targets the root `Makefile` defines.
Words that set a variable, such as `TESTS=a`, and flags are not targets, and a command with `-C` or `-f` runs another makefile, so the guard does not read it.

The code is `features/repo-standard/src/repo_standard/docs_true.py`.

## size and comments

Each rule of `size` picks files by `files`, less `exclude`, and none of them grows past `cap` lines unless `over` lists it.
`over` holds each file that was over the cap when the cap was set, with its length then.
A listed file that is back under the cap, or gone, fails until it leaves the list, so the list only shrinks.

`comments` picks files the same way, and none of them holds a plain comment.
The guard reads a file's comments the way its language does, by the file's extension:

| Reader | Extensions it takes by default | What it reads as a comment |
|---|---|---|
| `python` | `.py` | a `#` comment, read with `tokenize` |
| `shell` | `.sh`, `.bash`, `.yml`, `.yaml`, `.toml` | a `#` that starts a word, outside quotes |
| `script` | `.js`, `.mjs`, `.ts`, `.css` | `//` and `/* */`, outside strings and regular expressions |
| `page` | `.html` | a `script` comment in a `<script>` or `<style>` |
| `unit` | `.service`, `.timer` | a line that starts with `#` or `;` |
| `hash` | none | a line that starts with `#` |

`readers` maps any other extension to one of them, as `.go: script` does.
A file whose extension no reader takes is refused, not passed unread.
A comment passes when it is a shebang on the first line, when it starts with one of `allow`, or when its file's extension is one of `links` and it holds an `https://` link.

The code is `features/repo-standard/src/repo_standard/size.py`, with the readers in `features/repo-standard/src/repo_standard/lexers.py`.
