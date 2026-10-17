# jbriefs

`jbriefs` writes one HTML page of every home under `~/.local/state/home/`: each repo's handoff, its open plan entries, and every brief with its result. It prints the page's path. It reads the files alone, and asks neither T3 Code nor GitHub.

| Argument | What it does |
|---|---|
| `state` | The directory that holds one home per repo. Defaults to `~/.local/state/home`. |
| `--out <path>` | Where to write the page. Defaults to `$XDG_CACHE_HOME/jbriefs/briefs.html`, or `~/.cache/jbriefs/briefs.html`. |
| `--skills-run <brief>` | Writes no page. Prints the artifact the brief's Results hold under `Skills run:` for each skill its `Skills:` line names, as `jmerge` reads it, or `- <name>: no artifact`. The reviewer's intent has it. |
| `--skills <brief>` | Writes no page. Prints in full each skill or principle the brief's `Skills:` line names, under a line `loaded: <names>`, then the artifact each owes under `Skills run:` in the Result (`templates/skill-artifacts.md`). A name it does not resolve gets a line `unknown skill: <name> ...`. The crew and scout skills run it at their start. |

## `jbriefs pick`

`jbriefs pick <path | ->` prints which skill takes a piece of work, which playbook it follows, and which other skills its words call for. The `/poteto-help` skill runs it. It reads the tree it is installed from and the file it is given, and writes nothing.

| Given | Role line |
|---|---|
| a file under `tasks/` (a brief) | `role crew: /crew <slug> (skills/crew/SKILL.md)` |
| a file under `scouts/` (a scout's request) | `role scout: /scout <slug> (skills/scout/SKILL.md)` |
| `-`, text on stdin, or any other file | `role home: /home (skills/home/SKILL.md)` |

The lines after the role line:

- `playbook <name>: playbooks/<name>.md (<why>)`. The name comes from the file's `Playbook:` line. A file with no such line gets a `Run by:` row of its role's runner: first a row whose `in a brief with` lines the file has, then a row whose backticked path covers every path on the file's `Where:` and `Change:` lines (tests aside), then the role's default, which is `feature` for a crewmate, `investigation` for a scout and `none` for the home.
- `tip <skill>: ...`: at most three skills whose `tip:` phrases the words say, by the rule of `hooks/skill-tips.sh`, the most literal words first. A brief or a request is read by its title, its `Task:` and its list items. Other text is read whole.
- `named <skill>: ...`: each skill the text names as `/<name>` or as `skills/<name>`, read from a brief's or a request's head (no Result or Review under it) and from other text whole. A path such as `/tmp/x` names none.
- `unknown <name>: ...`: a name from a `Playbook:` line, a `/<name>` or a `skills/<name>` that is no file here. It is printed, never dropped.

Every path it prints is from the root of the jstack checkout.

## What an approval binds to

A go from the user is bound to the brief's goal, scope and done-when: its title, `Task:`, `Done when:`, `Where:`, `Do not touch:` and `Size:` (`MEANING` in `src/jbriefs/meaning.py`, a fingerprint made with no model). An edit to `Skills:`, `Decisions:`, `Design:`, `Proves it:`, `Review:`, `Playbook:`, `Pull request:` or a note keeps the go (`NOT_MEANING` lists them), and a change to any of the six asks again. The checks of `jbriefs.parse.faults` run when a row is first queued; a row with a go is grandfathered, so a check added later refuses neither its brief nor its launch. [What an approval is bound to](jbus.md#what-an-approval-is-bound-to) has the rules.

## Skills a brief names

A brief's `Skills:` line names skills and principles by pstack's names, so that a name reads the same in a Grok Bot brief, which pstack drives, and in T3, which jstack drives. The canonical form of a skill is its directory under `skills/`, `architect`; of a principle, its file under `principles/` without `.md`, `principle-model-the-domain`. Two aliases resolve too: a principle's name from before it took pstack's prefix, `model-the-domain`, and `arena` and `swarm`, pstack skills that jstack keeps as playbooks. A pstack skill jstack did not take, `poteto-mode` and the `Not taken:` line of `THIRD_PARTY.md`, is no name. `src/jbriefs/skills.py` is the one resolver: `jbus queue add` refuses a brief that names anything else, the launch gates one queued before, `jbriefs --skills` loads the files, and `jmerge` waits on a pull request whose Results leave a named skill with no artifact.
