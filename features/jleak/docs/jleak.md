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

The install links it at `.git/hooks/pre-push` of each repo jstack works in ("Which repos get the git hooks").
A repo's worktrees run the same hook.

`features/jleak/hooks/outbound-command.sh` is a `PreToolUse` hook on Claude Code's shell commands.
It runs `jleak --command` and refuses, with exit code 2:

- a `gh pr create`, `gh pr edit`, `gh pr comment` or `gh pr review` whose text matches a pattern. It reads the whole command, less a `cd` in front, and reads the file that `gh pr create --body-file`, or the same flag of the other three, names;
- a `git push --no-verify`, and a `git push` that sets `core.hooksPath`, since either skips the first hook.

It reads the command as the shell would, so a word in a commit message or in another program's arguments is not taken for a push or a body file. It refuses a body that is piped in, since it cannot read one. It does not see a body that the command builds from a variable, or a command inside a quoted string.

The `PreToolUse` entry is in your own settings, so the hook reads the commands of every repo on the machine, and the `pre-push` link is in the repos jstack works in alone.
A `gh pr comment` in a private repo that names that repo is refused once its name is a pattern.

## AI trailers

No commit and no pull request says an AI wrote it.
`jleak.trailers` (`features/jleak/src/jleak/trailers.py`) names the lines that would, and both guards below read it:

- `ai-co-author`: a `Co-authored-by:` trailer that names Claude, Codex, OpenAI, Cursor or Copilot, or an `@anthropic.com` address, in any case.
- `generated-with-claude-code`: the "Generated with Claude Code" line.

A `Co-authored-by:` line that names a person matches neither, and both guards leave it.

`features/jleak/hooks/ai-trailer.sh` is a `PreToolUse` hook on the shell commands of Claude Code and Codex.
It runs `jleak --trailers`, which needs no private patterns.
It reads each `git commit` and each `gh pr create`, `gh pr edit` or `gh pr merge` in the command: every word, each here-document, and the message file that `git commit -F` or `gh pr create --body-file` names.
A message that `cat` writes from a here-document before `git commit -F` reads it is read too.
A line that matches refuses the command with exit code 2:

```text
command:3: ai-co-author
jleak: 1 AI trailer, so the command is refused: drop the line and commit again
```

It does not read a message file that is not there yet, or one piped in: the next hook takes the trailer out of those.

`features/jleak/hooks/commit-msg.sh` is git's `commit-msg` hook, for Cursor and every other tool that the first hook does not see.
It runs `jleak --commit-msg`, which takes each such line out of the message, and the blank lines that are then left at its end.
It prints one line that names what it took out, and leaves a message with no such line exactly as it was:

```text
jleak: took out of the commit message: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

It never stops a commit, even when it cannot clean the message.
The install links it at `.git/hooks/commit-msg` of each repo jstack works in, beside `pre-push`, and a repo's worktrees run it too.

## Which repos get the git hooks

The install links both git hooks into jstack's own checkout, the checkout of each project of `jbus`'s config, and each repo set up with `jinstall --repo`.
`/new-home` runs `jinstall --repo` for the repo it sets up.
To add them to any other repo, run `jinstall --repo` in it, or `sh install.sh --repo <path>` from a checkout.
Each hook links to its script in the release's source or the checkout, and a release's script runs jleak on the release's own Python, so the hooks need no checkout.
A hook of the repo's own is never written over: its line in `jinstall --check` names the file and the line that runs this hook from it, as [jinstall's page](../../jinstall/docs/jinstall.md#git-hooks-in-your-repos) shows.
