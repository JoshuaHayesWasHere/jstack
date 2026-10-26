# jleak

`jleak` keeps text that is private to your machine out of what you push and post.
Your home path, your name and the names of your private repos are patterns in a file of your own.
`jleak` refuses a push or a pull request command whose text matches one of them, or matches the shape of a key.
It also keeps AI co-author trailers out of your commits and pull requests, as [AI trailers](#ai-trailers) describes.

## Before your first push

- **Fill in your patterns.**
  The install makes `${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml` once, with your home path in it.
  The file also holds your name, your machine's name and your private repos as examples behind a `#`.
  Take the `#` off each line you need, and put in your own names.
- **With no patterns file, the hooks refuse.**
  While the file is missing, the `pre-push` hook refuses every push.
  The Claude Code hook then refuses every `gh pr create`, `gh pr edit`, `gh pr comment` and `gh pr review`, and every `git push` that skips the `pre-push` hook.
  When you run `jleak` by hand, it checks only the built-in patterns and says so on stderr.
- **Know which repos get the git hooks.**
  The install links `pre-push` and `commit-msg` into three kinds of repo: jstack's own checkout when the install runs from one, the checkout of each project in `jbus`'s config, and each repo you set up with `jinstall --repo`.
  To add them to another repo, run `jinstall --repo` in it.
  The Claude Code hooks live in your own settings, so they read the commands of every repo on the machine, as [Which repos get the git hooks](#which-repos-get-the-git-hooks) describes.

## The private patterns

`jleak` reads the private patterns from a file of your own, outside every repo, `${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml`:

```toml
[patterns]
home-path = '/home/alex(?![\w-])'
user-name = '(?i)\b(?:alex|alexandra)\b'
private-repo = '\b(?:a-private-repo|another-one)\b'
```

The file is one table, `[patterns]`.
Each key is a pattern's name: lower case, with digits and `-`, and not the name of a built-in pattern.
Each value is a string, a regular expression of Python's `re`.
`jleak` matches a pattern against one line at a time, and the match is case-sensitive.
To match any case, start the pattern with `(?i)`.

The install (`jinstall`, or `jinstall --setup`) makes the file once and never writes it again.
When the install first makes the file, the file holds your home directory, the shape of a thread id, and the shapes of a tailnet's names and addresses.
Your name, the machine's name and the names of your private repos are examples behind a `#`.
Take the `#` off and fill them in.

jstack's source holds only the built-in patterns, which are the shapes of keys: `private-key`, `github-token`, `aws-access-key`, `slack-token` and `anthropic-key`.

## What it prints

```sh
jleak --all
jleak [--as <field>] <file>...
```

`--all` checks every tracked file of the repo you run it in, and each file's own name.
`jleak <file>` checks the file as it is on disk.
A `-` in place of a file means the text piped in, and `--as <field>` gives the name that its findings use.
`--patterns <file>` reads the private patterns from another file.

Each finding is one line, `<file or field>:<line>: <pattern's name>`, and the last line is the count:

```text
notes.md:3: user-name
secret-plan.md:0: private-repo
2 findings
```

Line 0 is the file's own name.
`jleak` never prints the text that matched.

| Exit code | Meaning |
|---|---|
| 0 | No finding. |
| 1 | A finding. |
| 2 | Nothing could be checked, and stderr says why. With `--command`, a finding also exits 2. |

With no private patterns file, `jleak` checks the built-in patterns and says so on stderr.
With `--strict` it exits 2.

## The two hooks

Both hooks run `jleak --strict`, so both refuse everything while the private patterns file is missing.

`features/jleak/hooks/pre-push.sh` is git's `pre-push` hook.
It runs `jleak --push`, which reads each ref git is about to send.
It runs `git ls-remote` on the push's URL to learn what the destination already has.
It checks the ref's name.
For each commit the destination does not have yet, it checks the message, each line the commit adds, and the name of each file the commit creates.
`jleak` refuses the push on any finding:

```text
branch:1: user-name
commit 1a2b3c4 message:3: private-repo
commit 1a2b3c4 notes.md:12: home-path
jleak: 3 findings, so the push is refused
```

The install links it at `.git/hooks/pre-push` of each repo jstack works in, as [Which repos get the git hooks](#which-repos-get-the-git-hooks) says.
The repo's worktrees run the same hook.

`features/jleak/hooks/outbound-command.sh` is a `PreToolUse` hook on Claude Code's shell commands.
It runs `jleak --command` and refuses, with exit code 2:

- A `gh pr create`, `gh pr edit`, `gh pr comment` or `gh pr review` whose text matches a pattern.
  The hook reads the whole command, except a `cd` in front, and the file named by `gh pr create --body-file` or by the same flag of the other three.
- A `git push --no-verify`, and a `git push` that sets `core.hooksPath`, since either one skips the `pre-push` hook.

It reads the command as the shell would, so it does not mistake a word in a commit message, or in another program's arguments, for a push or a body file.
It refuses a body that is piped in, since it cannot read one.
It does not see a body that the command builds from a variable, or a command inside a quoted string.

The `PreToolUse` entry lives in your own settings, so the hook reads the commands of every repo on the machine.
The `pre-push` link is only in the repos jstack works in.
Once a private repo's name is a pattern, the hook refuses a `gh pr comment` in that repo that names it.

## AI trailers

`jleak` keeps lines that say an AI wrote the work out of commits and pull requests.
`jleak.trailers` (`features/jleak/src/jleak/trailers.py`) defines those lines, and both guards below read it:

- `ai-co-author`: a `Co-authored-by:` trailer that names Claude, Codex, OpenAI, Cursor or Copilot, or an `@anthropic.com` address, in any case.
- `generated-with-claude-code`: the "Generated with Claude Code" line.

A `Co-authored-by:` line that names a person matches neither pattern, and both guards leave it in place.

`features/jleak/hooks/ai-trailer.sh` is a `PreToolUse` hook on the shell commands of Claude Code and Codex.
It runs `jleak --trailers`, which needs no private patterns.
It reads each `git commit` and each `gh pr create`, `gh pr edit` or `gh pr merge` in the command.
It reads every word, each here-document, and the message file that `git commit -F` or `gh pr create --body-file` names.
It also reads a message that `cat` writes from a here-document for `git commit -F` to read.
If a line matches, `jleak` refuses the command with exit code 2:

```text
command:3: ai-co-author
jleak: 1 AI trailer, so the command is refused: drop the line and commit again
```

It does not read a message file that does not exist yet, or a message piped in.
For those, the `commit-msg` hook below takes the trailer out.

`features/jleak/hooks/commit-msg.sh` is git's `commit-msg` hook, for Cursor and every other tool that `ai-trailer.sh` does not see.
It runs `jleak --commit-msg`, which removes each such line from the message, then removes the blank lines left at its end.
It prints one line that names what it removed, and leaves a message with no such line exactly as it was:

```text
jleak: took out of the commit message: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

It never stops a commit, even when it cannot clean the message.
The install links it at `.git/hooks/commit-msg` of each repo jstack works in, beside `pre-push`, and the repo's worktrees run it too.

## Infra's files

Infra's files, port 3773 and T3 Code's tailnet setup are the infra home's to change.
`features/jleak/hooks/infra-files.sh` is a `PreToolUse` hook on Claude Code's `Bash`, `Write`, `Edit`, `MultiEdit` and `NotebookEdit` calls.
It runs `jleak --infra`, and `jleak.infra` (`features/jleak/src/jleak/infra.py`) says in full what it refuses, with exit code 2:

- A call that writes `~/.config/jstack/roles`, `~/.config/jbus/config.toml`, the file a link of either points to, `~/.t3/userdata/server-runtime.json` (T3 Code's host and port), a `~/.config/systemd/user/t3-port-*` unit, or `~/.local/bin/t3-port-follow`.
- A command that changes port 3773 or T3 Code's tailnet setup: `tailscale serve` or `funnel` on 3773, or its `reset`, a `systemctl` verb that is not a read on a `t3-port-*` unit, a listener on 3773, or `fuser -k` on it.

A shell command writes a file when it redirects into it, or names it and is not a command that only reads it.
It reads `~`, `$HOME` and `${HOME}` as the shell does, and follows a `cd`.
`cat`, `grep`, `jq` and `diff` read, `cp` reads its sources, and `sed` and `perl` write only with `-i`.
A program it does not know is taken to write.
The refusal says to send the lines to the infra home:

```text
jleak: ~/.config/jbus/config.toml is infra's, so the call is refused: send the infra home the lines to change, and it makes the change
```

The infra home and its crew are let through.
The hook's test of which home runs a call reads the project the session started in, Claude Code's `CLAUDE_PROJECT_DIR`, and the hook's `cwd` when that is not set.
A call passes when that folder is a checkout of the repo named `infra`, or a worktree of it.
A thread of another repo whose shell moves into infra's checkout is still refused, since its project has not changed.

## Which repos get the git hooks

The install links both git hooks into jstack's own checkout, the checkout of each project of `jbus`'s config, and each repo set up with `jinstall --repo`.
`/new-home` runs `jinstall --repo` for the repo it sets up.
To add them to any other repo, run `jinstall --repo` in it, or `jinstall --repo <path>` from anywhere.
Each hook links to its script in the release's source or the checkout.
A release's script runs jleak on the release's own Python, so the hooks need no checkout.
The install never writes over a hook the repo already has.
For such a hook, `jinstall --check` names the hook's file.
It also prints the line to add to that file to run jstack's hook, as [jinstall's page](../../jinstall/docs/jinstall.md#git-hooks-in-your-repos) shows.
