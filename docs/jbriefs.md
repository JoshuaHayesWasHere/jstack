# jbriefs

`jbriefs` writes one HTML page of every home under `~/.local/state/home/`: each repo's handoff, its open plan entries, and every brief with its result. It prints the page's path. It reads the files alone, and asks neither T3 Code nor GitHub.

| Argument | What it does |
|---|---|
| `state` | The directory that holds one home per repo. Defaults to `~/.local/state/home`. |
| `--out <path>` | Where to write the page. Defaults to `$XDG_CACHE_HOME/jbriefs/briefs.html`, or `~/.cache/jbriefs/briefs.html`. |

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
- `named <skill>: ...`: each skill the text names as `/<name>` or as `skills/<name>`. A path such as `/tmp/x` names none.
- `unknown <name>: ...`: a name from a `Playbook:` line, a `/<name>` or a `skills/<name>` that is no file here. It is printed, never dropped.

Every path it prints is from the root of the jstack checkout.
