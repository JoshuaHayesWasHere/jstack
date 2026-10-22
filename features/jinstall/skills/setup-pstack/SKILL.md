---
name: setup-pstack
description: Set this machine up for jstack, or check it again - run the checkout's own `install.sh --setup`, which walks every need once, writes the configs that are not there and links the units, then the doctor, and report what was done, what was already there and the one command for each thing only the user can do. Use for /setup-pstack.
disable-model-invocation: true
card: "Run the pipeline | 9 | Sets this machine up for jstack in one pass, through `install.sh --setup`: the configs it lacks, the links, the commands and the units, and the one command for each thing only you can do. | Reach for it on a new machine, or to check one again. | op: the operator"
---

# setup-pstack

`/setup-pstack` sets this machine up for jstack, or checks it again, from any thread. It is typed, never loaded by itself. The name is pstack's, and the work is jstack's: pstack's skill of this name writes a Cursor rule of models and budgets, and here the role map is `~/.config/jstack/roles`, written with every role `inherit`, so no role runs above medium effort.

The skill does no step of its own. `install.sh --setup` in the checkout this skill is linked from holds the one list of what a machine needs, the same list the doctor reads, and does each step once: it says `already` for what is there, writes each config that is not there and never one that is, links the skills, hooks, commands and units, and names the one command for each thing only the user can do. A second run writes nothing, so this skill can be typed again at any time.

This thread changes nothing else. It writes no config by hand, runs none of the commands it reports, starts no thread and asks for no secret: a sign-in, a webhook and its key stay the user's.

## 1. Run the setup and the doctor

Run this:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
C=
for root in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
    S=$(realpath "$root/setup-pstack" 2> /dev/null) || continue
    S=${S%/skills/setup-pstack}
    S=$(realpath "$S/source" 2> /dev/null || echo "$S")
    if [ -f "$S/install.sh" ]; then
        C=$S
        break
    fi
done
if [ -z "$C" ]; then
    echo "not set up: no ~/.claude/skills/setup-pstack or ~/.agents/skills/setup-pstack links into a jstack checkout. Nothing is done."
    echo "needs you: clone jstack and run sh <checkout>/install.sh --setup in its main checkout"
else
    echo "checkout: $C"
    said=$(sh "$C/install.sh" --setup 2>&1)
    code=$?
    printf '%s\n' "$said"
    printf '%s\n' "$said" | awk -v code="$code" '
        $(1) == "done" {done++}
        $(1) == "already" {already++}
        $(1) == "needs" && $(2) == "you" {you++}
        END {printf "setup: %d done, %d already, %d needs you, exit %d\n", done, already, you, code}'
    doctor=$(sh "$C/install.sh" --doctor 2>&1)
    printf '%s\n' "$doctor" | tail -n 1
fi
```

It prints the checkout, every line of the setup, a count, and the doctor's last line. The setup's lines are:

- `done <name>`: this run wrote it.
- `already <name>`: it was there.
- `needs you <name> -> <command>`: only the user can do it, with the one command that does.
- `install.sh: <checkout> is a linked worktree, and HOME is your own: set up from the main checkout`: nothing was written. The skill is linked from a worktree, which the setup refuses under the account's own HOME.

On `not set up`, the machine has no jstack yet: the skill is linked by the setup itself, so the first run is the user's, by hand.

## 2. Report

Tell the user, in at most eight lines:

1. The count line, as printed.
2. Each `needs you` line, as printed, the command after `->` in backticks. Hard needs first: the setup exits 1 while one is left.
3. The doctor's last line, `doctor: ok` or `doctor: not ok, <n> hard`.
4. When a `needs you` line was left: run each command, then type `/setup-pstack` again.

Do not list the `done` and `already` lines one by one: the count says them.
Where the user asks what a line means, `features/jinstall/docs/troubleshooting/setup.md` in the checkout has each one.
