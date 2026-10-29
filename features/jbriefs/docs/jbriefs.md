# jbriefs

`jbriefs` shows you, on one HTML page, what every home on this machine is doing: each repo's handoff, its open plan entries, and every brief with its result.
It reads only the files under `~/.local/state/home/`, and asks neither T3 Code nor GitHub.
The crew, scout and pr-review skills also run it to read a brief's skills and findings.

## See every home's work

1. Run `jbriefs`.
   It writes the page and prints its path.
2. Open that path in a browser.

To write the page somewhere else, run `jbriefs --out <path>`.

## Arguments

| Argument | What it does |
|---|---|
| `state` | The directory that holds one home per repo. Defaults to `~/.local/state/home`. |
| `--out <path>` | Where to write the page. Defaults to `$XDG_CACHE_HOME/jbriefs/briefs.html`, or `~/.cache/jbriefs/briefs.html`. |
| `--skills-run <brief>` | Writes no page. Prints the artifact the brief's Results hold under `Skills run:` for each skill its `Skills:` line names, as `jmerge` reads it, or `- <name>: no artifact`. The pr-review skill puts this output in the intent it gives the reviewer. |
| `--findings <brief>` | Writes no page. Prints the findings of every `## Review` section of the brief as one triaged list, the same on every run. Each finding has its id (`F1`, `F2`, ...), its bucket, severity, place and principle, the reviewers that raised it, and the head. It also has the answer the finding has by id, and whether that answer counts. A blocking decline also has the scoped pass's ruling on it, `upheld` or `not upheld`, with the disproof. A finding of a review after the first that is not the crew's says it goes nowhere, since only an error or a warning of such a review goes to the crew. When another reviewer wrote a dismissal of the same place, the list prints it beside the finding it contradicts. The last line, `next:`, says what the crew does next. With `--left` it prints only what that line says, with no `next:`, and the crew skill reads it. With `--rounds` it prints how many sections ran, the head the last one saw, every head a section names, and the blocking declines that no scoped pass has ruled on. The crew skill's "A second pass" reads that output. `features/jbriefs/src/jbriefs/findings.py` is the one parser of findings and answers. `jmerge`, the crew skill and jbus's `expedite` read briefs through it. |
| `--skills <brief>` | Writes no page. Prints in full each skill or principle the brief's `Skills:` line names, under a line `loaded: <names>`, then the artifact each owes under `Skills run:` in the Result (`features/skill-library/templates/skill-artifacts.md`). A name it does not resolve gets a line `unknown skill: <name> ...`. The crew and scout skills run it at their start. |

## `jbriefs pick`

`jbriefs pick <path | ->` prints which skill handles a piece of work, which playbook that skill follows, and which other skills the work's text points to.
The `/poteto-help` skill runs it.
It reads the tree it is installed from and the file it is given, and writes nothing.

| Given | Role line |
|---|---|
| a file under `tasks/` (a brief) | `role crew: /crew <slug> (features/crew/SKILL.md)` |
| a file under `scouts/` (a scout's request) | `role scout: /scout <slug> (features/scout/SKILL.md)` |
| `-`, text on stdin, or any other file | `role home: /home (features/home/skills/home/SKILL.md)` |

These lines follow the role line:

- `playbook <name>: <its path> (<why>)`, with the path as `skills.json` lists it, such as `features/crew/playbooks/feature.md` or `features/scout/playbooks/investigation.md`.
  The name comes from the file's `Playbook:` line.
  For a file with no such line, `jbriefs pick` looks at the `Run by:` rows of the playbooks that the role's skill runs.
  It takes the playbook from the first of these that fits:
  - a row whose `in a brief with` lines all appear in the file
  - a row whose backticked path covers every path on the file's `Where:` and `Change:` lines, not counting test paths
  - the role's default, which is `feature` for a crewmate, `investigation` for a scout and `none` for the home
- `tip <skill>: ...`: up to three skills whose `tip:` phrases appear in the text, matched by the rule of `features/skill-library/hooks/skill-tips.sh`, with the closest match first.
  In a brief or a request, `jbriefs pick` reads only the title, the `Task:` line and the list items.
  It reads other text whole.
- `named <skill>: ...`: each skill the text names as `/<name>` or as `skills/<name>`.
  In a brief or a request, `jbriefs pick` reads only the part above the Result and the Review.
  It reads other text whole.
  A path such as `/tmp/x` names no skill.
- `unknown <name>: ...`: a name from a `Playbook:` line, a `/<name>` or a `skills/<name>` that matches no file here.
  `jbriefs pick` always prints such a name, and never drops it.

Every path it prints starts from the root of jstack's source tree, which is the checkout it runs from or the `share/jstack` folder of a release.

## What an approval binds to

The user's go applies to the brief's goal, scope and done-when: its title, `Task:`, `Done when:`, `Where:`, `Do not touch:` and `Size:`.
`MEANING` in `features/jbriefs/src/jbriefs/meaning.py` lists those fields.
The fingerprint of those fields uses no model.
An edit to `Skills:`, `Decisions:`, `Design:`, `Proves it:`, `Review:`, `Playbook:`, `Pull request:` or a note keeps the go (`NOT_MEANING` lists them).
After a change to any of the six fields, the user must give the go again.
`jbus queue add` runs the checks of `jbriefs.parse.faults` when it first queues a row.
Among them, one refuses a brief whose head asks for a load that takes every core (`stress-ng --cpu 0`, `stress-ng --cpu $(nproc)`, every core), and names a bounded load inside `jgauge test-slot` instead.
Another, `layered`, refuses a brief whose `Builds on:` line gives a plan layer as its reason (`the base of layer 2`), since a row stacks only on a parent whose code it changes, calls or imports.
`features/jbriefs/src/jbriefs/standing.py` holds the two.
A check added after a row got its go does not apply to that row, so it refuses neither the row's brief nor its launch.
[What an approval is bound to](../../jbus/docs/jbus/the-queue.md#what-an-approval-is-bound-to) has the rules.

## Skills a brief names

A brief's `Skills:` line names skills and principles by pstack's names, so that a name reads the same in pstack and in jstack.
`skills.json`, at the root of jstack's source tree, lists the names, and the resolver reads them from that file, not from the directories.
The canonical form of a skill is its directory under `skills/`, such as `architect`.
The canonical form of a principle is its directory under `features/principles/skills/`, such as `principle-model-the-domain`.
Three aliases resolve too:

- an item's `pstack_name` in `skills.json`, where pstack names the item otherwise
- a principle's name from before it took pstack's prefix, such as `model-the-domain`
- `arena` and `swarm`, pstack skills that jstack keeps as playbooks

A brief uses the canonical form, which the resolver finds on its first lookup: `principle-build-the-lever`, not `build-the-lever`.
The resolver reaches `build-the-lever` only after it looks for an item of that name.
The two spellings count as one name, both on the `Skills:` line and under the Result's `Skills run:`.
`jmerge`'s wait message names a skill as the brief spelled it.
A pstack skill that jstack did not take does not resolve: `poteto-mode`, and each skill on the `Not taken:` line of `THIRD_PARTY.md`.
`features/jbriefs/src/jbriefs/skills.py` is the one resolver, and these use it:

- `jbus queue add` refuses a brief that names any other skill when its row is first queued.
  A check added after a row got its go does not apply to that row, so the row still launches.
- `jbriefs --skills` loads the files.
- `jmerge` waits on a pull request whose Results leave a named skill with no artifact.

## Reference for jstack developers

### skills.json

`python3 scripts/generate-jstack-trees.py` (`make trees`) writes `skills.json`, and nobody edits it by hand.
The script reads `features/`, the skills, principles, playbooks and templates they own, and the pstack map of `THIRD_PARTY.md`.
`jbriefs.skills` does not import the script.
`make check` and `make check-fast` fail when `skills.json` is stale, and name the items that differ.
So a pull request that adds, renames or removes a skill or principle also commits the regenerated `skills.json`.
A reader outside this repo, such as another provider, another machine or a persona, also reads the set of skills from `skills.json`.
Its `items` are sorted by kind, then by name, and each item has these keys:

| Key | What it holds |
| --- | --- |
| `name` | The canonical name a `Skills:` line uses; for a template, its path under `templates/`. |
| `kind` | `skill`, `principle`, `playbook` or `template`. |
| `path` | The file it loads, from the repo root. |
| `source` | `pstack` for pstack's item of the same name, brought over one to one; `adapted` for one built from pstack's item with other material beside it, or from a pstack item of another name; `jstack` for jstack's own, with no pstack skill or principle behind it. |
| `pstack_name` | Only where pstack's name for it differs from `name`: an alias the resolver maps to `name`. |
| `description` | A skill's frontmatter `description`, or the paragraph under a principle's title. |
| `nameable` | Only on a playbook a `Skills:` line may name, because its feature lists it as `nameable`. |

At runtime, code finds any of these files only through `jbriefs.skills.where(kind, name)`, as in `where("template", "gates.md")`.
No module computes a path in the checkout from its own location in the checkout.
`source` comes from the `Upstream map:` block of `THIRD_PARTY.md`.
That block lists the paths each file was written from, so nobody keeps a second list.
`THIRD_PARTY.md` says what changed in each item, and how much.
An item brought over one to one still has jstack's frontmatter and pointers.
`jstack` means only that the item is not based on a pstack skill or principle, and the item may still borrow a passage.
`crew` and `pr-review` take passages from pstack's `interrogate` reference files, which the map lists.
`grilling` is from Matt Pocock, as `THIRD_PARTY.md` says.
