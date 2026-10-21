# jleak

`jleak` finds what must not leave this machine for a public repo, before it leaves.

## The private patterns

What is private to a machine is in no repo. `jleak` reads it from a file of your own, `${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml`:

```toml
[patterns]
home-path = '/home/alex(?![\w-])'
user-name = '(?i)\b(?:alex|alexandra)\b'
private-repo = '\b(?:a-private-repo|another-one)\b'
```

The file is one table, `[patterns]`. Each key is a pattern's name: lower case, with digits and `-`, and not the name of a built-in pattern. Each value is a string, a regular expression of Python's `re`. A pattern is held against one line at a time, in the case it is written in. Start it with `(?i)` for any case.

`sh install.sh` makes the file once and never writes it again. As made, it holds your home directory and the shapes of a thread id and of a tailnet's names and addresses. Your name, the machine's name and the names of your private repos are examples behind a `#`: fill them in.

The tree holds only the built-in patterns, which are the shapes of keys: `private-key`, `github-token`, `aws-access-key`, `slack-token` and `anthropic-key`.

## What it prints

```sh
jleak --all
jleak [--as <field>] <file>...
```

`--all` checks every tracked file of the repo it is run in, and each file's own name. A `<file>` is checked as it is, and `-` is the text piped in, named as `--as` says. `--patterns <file>` reads the private patterns from another file.

Each finding is one line, `<file or field>:<line>: <pattern's name>`, and the last line is the count:

```text
notes.md:3: user-name
secret-plan.md:0: private-repo
2 findings
```

Line 0 is the file's own name. The text that matched is never printed.

| Exit code | Meaning |
|---|---|
| 0 | No finding. |
| 1 | A finding. |
| 2 | Nothing could be checked, and stderr says why. Also a finding with `--command`. |

With no private patterns file, `jleak` checks the built-in patterns and says so on stderr. With `--strict` it exits 2.

## The two hooks

Both hooks run `jleak --strict`, so neither passes anything while the private patterns are missing.

`features/jleak/hooks/pre-push.sh` is git's `pre-push` hook.
It runs `jleak --push`, which reads each ref git is about to send.
It asks the URL of the push what it has, with `git ls-remote`.
It checks the ref's name, and for each commit the destination does not have yet: the message, each line the commit adds, and the name of each file it creates.
A finding refuses the push:

```text
branch:1: user-name
commit 1a2b3c4 message:3: private-repo
commit 1a2b3c4 notes.md:12: home-path
jleak: 3 findings, so the push is refused
```

`sh install.sh` links it at `.git/hooks/pre-push` of the main checkout. The repo's worktrees run the same hook.

`features/jleak/hooks/outbound-command.sh` is a `PreToolUse` hook on Claude Code's shell commands.
It runs `jleak --command` and refuses, with exit code 2:

- a `gh pr create`, `gh pr edit`, `gh pr comment` or `gh pr review` whose text matches a pattern. It reads the whole command, less a `cd` in front, and reads the file that `gh pr create --body-file`, or the same flag of the other three, names;
- a `git push --no-verify`, and a `git push` that sets `core.hooksPath`, since either skips the first hook.

It reads the command as the shell would, so a word in a commit message or in another program's arguments is not taken for a push or a body file. It refuses a body that is piped in, since it cannot read one. It does not see a body that the command builds from a variable, or a command inside a quoted string.

The `PreToolUse` entry is in your own settings, so the hook reads the commands of every repo on the machine, and the `pre-push` link is this checkout's alone. A `gh pr comment` in a private repo that names that repo is refused once its name is a pattern.
