---
name: figure-it-out
description: "Frame a task no playbook fits (a large migration, an ambitious multi-part change, work reviewed after stepping away) and, in a home, turn it into plan entries whose crewmates each keep a decision log. Use for /figure-it-out or 'figure it out'."
tip: frames a task no playbook fits and plans it as entries with a decision log | figure it out | figure-it-out | no playbook fits | large migration | ambitious change
disable-model-invocation: true
card: "Settle the shape before code | 5 | Frames a task no playbook fits: done as a check that can fail, the scope counted, the rigor and why, the riskiest unit first and the check built before the work. In a home it plans the units as entries, each crewmate keeping a decision log. | Reach for it when a large or many-part task matches no playbook. | op: the operator; model: a home"
---

# Figure it out

Source: pstack, `pstack/skills/figure-it-out/SKILL.md`

When a task matches no playbook, frame it, then plan it as entries that crewmates work and a person can audit afterwards.
Every unit is a durable thread with its own file: no unit starts a subagent, here or in the threads it plans.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
if ! T=$(realpath ~/.claude/skills/figure-it-out/../../templates 2> /dev/null); then
    echo "no root: ~/.claude/skills/figure-it-out is not a link into the repo this skill lives in"
fi
```

That is **the block at the top**.
It prints nothing but `no root`, and on that the root is two directories above the real place of this file: set `T` to its `templates/`.
A path such as `playbooks/<name>.md` or `principles/<name>.md` is from `$T/..`, the repo this skill lives in.

## Where it runs

Run this with the block at the top, with this thread's id in place of `<threadId>`: the `t3-code` server's `t3_thread_configuration` gives it as `threadId`.
In a session with no tool that gives the id, put nothing in its place: that thread is the root home, as in `skills/home/SKILL.md` "The block that finds this home".

```sh
ME='<threadId>'
M=
if [ -z "$ME" ]; then M=$H; fi
for f in "$H"/home-id "$H"/*/home-id; do
    if [ -f "$f" ] && [ -n "$ME" ] && [ "$(awk 'NF {print $(1); exit}' "$f")" = "$ME" ]; then M=$(dirname "$f"); fi
done
if [ -n "$M" ]; then echo "home: $M"; else echo "not a home: no home-id under $H holds $ME"; fi
by=$(sed -n 's/^Run by: //p' "$T/../playbooks/arena.md" 2> /dev/null | head -n 1)
case ${by%%,*} in
"the home") echo "arena: a one-way door is its own entry, run by the home's playbooks/arena.md" ;;
*) echo "no arena: playbooks/arena.md is for ${by%%,*}, not the home, so a one-way door is planned with Stage: parked" ;;
esac
```

On `not a home`, this is a crewmate's thread or a plain one, and "The frame" below is yours with two changes: ground it on your own reading, since only a home sends a scout, and write its five lines in this thread, not under `$H`.
Plan nothing, write no brief, and fan nothing out.
A crewmate whose brief names this skill on its `Skills:` line puts the frame in its Result and goes on with its task.
Any other thread stops there and ends with one line: the frame is for a home, and `/home` in the repo's main checkout turns it into entries.
On `home: <dir>`, `<dir>` is `$M`, and the rest of this skill is yours.

## The frame

Ground first: a scout's Report, never your own reading, as `skills/home/SKILL.md` "Sending a scout" says.
Its request's "Deliver" list also asks what step 3 of `playbooks/multi-phase-plan.md` asks for, so that step is `skip: the frame's scout delivered it`.
Then write `$H/reports/frame-<slug>.md` with these five lines, and show them to the user before any entry is written:

- `Predicate:` done, as a check that can fail on the real thing (`principles/principle-prove-it-works.md`).
- `Scope:` the units, counted, each with a t-shirt size, and the blockers the scout found.
- `Rigor:` low, medium or high, biased high, and why.
  A one-way door or a wide blast radius raises it, and a reversible small step lowers it.
  Rigor is gates and artifacts, not effort.
- `Riskiest:` the unit whose unknown could sink the rest.
  It is planned first (`principles/principle-sequence-verifiable-units.md`).
- `Harness:` the entry that builds the check before the work, with its baseline taken from the code as it is now, so each later check reads old value against new (`principles/principle-foundational-thinking.md`).

A unit whose design is a one-way door goes by the `arena` line the block printed: on `arena`, its own entry, ahead of the entries that build on it, run as that playbook says; on `no arena`, its entry has `Stage: parked` and the reason, since that playbook's runners are subagents, and the Reply names it as open, with the entries that wait on it.
A unit whose shape is already concrete gets no arena.

## The entries

Open `multi-phase-plan` with the block of "A playbook of the home's own" in `skills/home/SKILL.md`, and work its steps with the frame in hand:

- The harness entry is first in the order paragraph, and each feature entry waits on it.
  The riskiest unit comes next.
- Each entry's `Decisions:` names the frame's path.
  The last entry's last `Done when` line is the frame's `Predicate:`.
- Each brief names `show-me-your-work` on its `Skills:` line, so its crewmate logs a row as each unit lands.
  Its `Decisions:` line says to commit the log into the tree, so the trail outlives the worktree.
- Each brief's `Decisions:` line also says that no step starts a subagent: a playbook step that would, such as `playbooks/feature.md` step 4, is a `skip:`, and its work is done in the crewmate's own thread.

Before a brief is queued, run this with the block at the top and the briefs' slugs in place of the words in angle brackets.
It runs the brief lint that `jbus queue add` runs, and reads the `Skills:` line as the crew skill loads it:

```sh
slugs='<the slugs>'
for slug in $slugs; do
    f="$H/tasks/$slug.md"
    if [ ! -f "$f" ]; then
        echo "$slug: no brief at $f"
        continue
    fi
    if said=$(uv run --project "$T/.." python -c '
import sys
from jbriefs.parse import faults
from jbriefs.skills import named
text = open(sys.argv[-1]).read()
logs = "show-me-your-work" in [one.name for one in named(text)]
print("\n".join(faults(text) + ([] if logs else ["its Skills: line does not name show-me-your-work"])))
' "$f"); then
        printf '%s\n' "$said" | sed "/^\$/d; s/^/$slug: /"
    else
        echo "$slug: the lint did not run"
    fi
done
```

It prints nothing when every brief passes.
Each line it prints is a fault: mend the brief and run it again.

**Reply:** the frame's path and its five lines, the entries in order with what each waits on, the rigor and why, and what is still open.
