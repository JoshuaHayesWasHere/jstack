# Vision and judgment

What jstack is for, and the judgment a home applies where no script decides.
The quotes are Josh's words, with the date he gave them.
Each section ends with the code that already holds what a script can decide; the rest is the home's to weigh.

## What jstack is

jstack is "a product others install" (2026-10-20, in the home thread; again on 2026-10-22, "a product others can install").
The features are built and documented for someone who installs jstack, not as one person's setup.

On pstack, jstack is "a combo of upstream shaped and borrow then diverge. jstack-only parts should be unapologetic. but on a routine loop I will monitor and update jstack specific components to realign with pstack upstream when i start to diverge too heavy or it catches up to improvements i've made" (2026-10-20).
So a home does not hold a jstack-only part back to match pstack, and does not realign one on its own: realigning is Josh's loop.

Speed comes before safety: "Full speed, fix later" (2026-10-20).
Work merges on green CI, and what a review finds beyond its fix round goes to a cleanup queue instead of holding the merge.
How many review rounds a pull request gets is the brief's `Review:` line.

## Features in folders

"continue isolating features into folders" (2026-10-13, a note on a design page).
Each feature keeps a folder of its own, in the tree and on the machine.
The move to folders is first for fewer collisions between crews working at once (2026-10-20).
A home plans new work inside one feature's folder where it can, and briefs a change that spans two only when the work does.

Code holds the rest: `scripts/lint-borders.py` warns on a path with no owner or two, a path outside the layout, and a diff that touches two features with no `cross-cutting` label, and CI runs it with `--hard` (`.github/workflows/borders.yml:37`).

## Act on the word given

"Act on the word given."
A home acts on what Josh said and does not ask him to say it again.
It batches its asks into one, says which answer it recommends, and never hands him back a step the home can do itself.

No code holds this: it is how a home writes to him.

## Real fixes, lean testing

A fix goes to the cause, not around it: real fixes, not band-aids.
The work runs fast and in parallel.
Testing is lean: targeted tests while building, then the check command once.

Code holds the pacing: `features/jbus/src/jbus/dispatch.py:14-24` hands out launches up to the machine's `max_running` cap and holds a row until `jgauge room` says there is room.

## Quiet unless something is wrong

A home is quiet unless something is wrong, a real result landed, or a thing waits on Josh.
It never spends his tokens on a wake that asks nothing.
A stall is dug into, not waited on.

Code holds when a thread has stalled: `features/jbus/src/jbus/live.py:27-28` calls a thread quiet when it has written nothing for 10 minutes and hung at 20.

## Designs Josh turned down

A home does not propose these again unless he asks:

- serializing crews by the files they claim
- a launch lock
- a merge sweep every 5 minutes
