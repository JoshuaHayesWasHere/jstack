# jbriefs

`jbriefs` writes one HTML page of every home under `~/.local/state/home/`: each repo's handoff, its open plan entries, and every brief with its result. It prints the page's path. It reads the files alone, and asks neither T3 Code nor GitHub.

| Argument | What it does |
|---|---|
| `state` | The directory that holds one home per repo. Defaults to `~/.local/state/home`. |
| `--out <path>` | Where to write the page. Defaults to `$XDG_CACHE_HOME/jbriefs/briefs.html`, or `~/.cache/jbriefs/briefs.html`. |
| `--skills-run <brief>` | Writes no page. Prints the artifact the brief's Results hold under `Skills run:` for each skill its `Skills:` line names, as `jmerge` reads it, or `- <name>: no artifact`. The reviewer's intent has it. |
| `--findings <brief>` | Writes no page. Prints the findings of every `## Review` section of the brief as one triaged list, the same on every run: each by its id (`F1`, `F2`, ...), with its bucket, severity, place and principle, the reviewers that raised it, the head, the answer it has by id and whether that answer counts, and for a blocking decline the scoped pass's ruling on it, `upheld` or `not upheld` with the disproof. A dismissal another reviewer wrote of the same place is printed beside the finding it contradicts. The last line, `next:`, says what the crew is to do. With `--left` it prints only that line, the crew skill's count; with `--rounds` it prints how many sections ran, the head the last saw, every head a section names and the blocking declines no scoped pass has ruled on, which the crew's "A second pass" reads. `features/jbriefs/src/jbriefs/findings.py` is the one parser of findings and answers: `jmerge`, the crew skill and jbus's `expedite` read briefs through it. |
| `--skills <brief>` | Writes no page. Prints in full each skill or principle the brief's `Skills:` line names, under a line `loaded: <names>`, then the artifact each owes under `Skills run:` in the Result (`features/skill-library/templates/skill-artifacts.md`). A name it does not resolve gets a line `unknown skill: <name> ...`. The crew and scout skills run it at their start. |

## `jbriefs pick`

`jbriefs pick <path | ->` prints which skill takes a piece of work, which playbook it follows, and which other skills its words call for. The `/poteto-help` skill runs it. It reads the tree it is installed from and the file it is given, and writes nothing.

| Given | Role line |
|---|---|
| a file under `tasks/` (a brief) | `role crew: /crew <slug> (features/crew/SKILL.md)` |
| a file under `scouts/` (a scout's request) | `role scout: /scout <slug> (features/scout/SKILL.md)` |
| `-`, text on stdin, or any other file | `role home: /home (features/home/skills/home/SKILL.md)` |

The lines after the role line:

- `playbook <name>: <its path> (<why>)`, the path as `skills.json` lists it, such as `features/crew/playbooks/feature.md` or `features/scout/playbooks/investigation.md`.
  The name comes from the file's `Playbook:` line.
  A file with no such line gets a `Run by:` row of its role's runner: first a row whose `in a brief with` lines the file has, then a row whose backticked path covers every path on the file's `Where:` and `Change:` lines (tests aside), then the role's default, which is `feature` for a crewmate, `investigation` for a scout and `none` for the home.
- `tip <skill>: ...`: at most three skills whose `tip:` phrases the words say, by the rule of `features/skill-library/hooks/skill-tips.sh`, the most literal words first.
  A brief or a request is read by its title, its `Task:` and its list items.
  Other text is read whole.
- `named <skill>: ...`: each skill the text names as `/<name>` or as `skills/<name>`, read from a brief's or a request's head (no Result or Review under it) and from other text whole. A path such as `/tmp/x` names none.
- `unknown <name>: ...`: a name from a `Playbook:` line, a `/<name>` or a `skills/<name>` that is no file here. It is printed, never dropped.

Every path it prints is from the root of the jstack checkout.

## What an approval binds to

A go from the user is bound to the brief's goal, scope and done-when: its title, `Task:`, `Done when:`, `Where:`, `Do not touch:` and `Size:` (`MEANING` in `features/jbriefs/src/jbriefs/meaning.py`, a fingerprint made with no model).
An edit to `Skills:`, `Decisions:`, `Design:`, `Proves it:`, `Review:`, `Playbook:`, `Pull request:` or a note keeps the go (`NOT_MEANING` lists them), and a change to any of the six asks again.
The checks of `jbriefs.parse.faults` run when a row is first queued; a row with a go is grandfathered, so a check added later refuses neither its brief nor its launch.
[What an approval is bound to](../../jbus/docs/jbus/the-queue.md#what-an-approval-is-bound-to) has the rules.

## Skills a brief names

A brief's `Skills:` line names skills and principles by pstack's names, so that a name reads the same in a Grok Bot brief, which pstack drives, and in T3, which jstack drives.
The names are listed in `skills.json` at the repo root, and the resolver reads them from there, not from the directories.
The canonical form of a skill is its directory under `skills/`, `architect`; of a principle, its directory under `features/principles/skills/`, `principle-model-the-domain`.
Three aliases resolve too: an item's `pstack_name` in `skills.json`, where pstack names it otherwise; a principle's name from before it took pstack's prefix, `model-the-domain`; and `arena` and `swarm`, pstack skills that jstack keeps as playbooks.
A brief writes the canonical form, the one the resolver reads at once: `principle-build-the-lever`, not `build-the-lever`, which it reaches only after looking for an item of that name.
The two spellings are one name, on the `Skills:` line and under the Result's `Skills run:` alike, and `jmerge`'s wait names a skill as the brief spelled it.
A pstack skill jstack did not take, `poteto-mode` and the `Not taken:` line of `THIRD_PARTY.md`, is no name.
`features/jbriefs/src/jbriefs/skills.py` is the one resolver: `jbus queue add` refuses a brief that names anything else when its row is first queued (a row with a go is grandfathered, and launches), `jbriefs --skills` loads the files, and `jmerge` waits on a pull request whose Results leave a named skill with no artifact.

### skills.json

`skills.json` is written by `python3 scripts/generate-jstack-trees.py` (`make trees`, which `jbriefs.skills` does not import) from `features/`, the skills, principles, playbooks and templates they own, and the pstack map of `THIRD_PARTY.md`, and nobody edits it by hand.
`make check` and `make check-fast` fail when it is stale, with the names of the items that differ, so a pull request that adds, renames or removes a skill or principle commits the file it regenerates.
It is also what a reader outside this repo takes the set from: another provider, another machine, a persona.
Its `items` are sorted by kind, then name, and each has these keys:

| Key | What it holds |
| --- | --- |
| `name` | The canonical name a `Skills:` line uses; for a template, its path under `templates/`. |
| `kind` | `skill`, `principle`, `playbook` or `template`. |
| `path` | The file it loads, from the repo root. |
| `source` | `pstack` for pstack's item of the same name, brought over one to one; `adapted` for one built from pstack's item with other material beside it, or from a pstack item of another name; `josh` for jstack's own, with no pstack skill or principle behind it. |
| `pstack_name` | Only where pstack's name for it differs from `name`: an alias the resolver maps to `name`. |
| `description` | A skill's frontmatter `description`, or the paragraph under a principle's title. |
| `nameable` | Only on a playbook a `Skills:` line may name, because its feature lists it as `nameable`. |

`jbriefs.skills.where(kind, name)` is the one way the runtime finds any of these files, as `where("template", "gates.md")`: no module reads a path of the checkout from its own place in it.
The source is read from the `Upstream map:` block of `THIRD_PARTY.md`, the paths each file was written from, so there is no second list to keep.
`THIRD_PARTY.md` says what changed in each, and how deep: one brought over one to one still has jstack's frontmatter and pointers.
`josh` means only that no pstack skill or principle is behind the item, and it may still borrow a passage: `crew` and `pr-review` take theirs from pstack's `interrogate` reference files, which the map lists, and `grilling` is from Matt Pocock, as `THIRD_PARTY.md` says.
