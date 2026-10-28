# What the threads noticed

A crewmate's Result, a scout's Report and a reviewer's Review each end with a `Noticed` line: what the thread saw that is outside its task. Each pass reads them in the home's `tasks/*.md` and `scouts/*.md`, from every `## Result`, `## Review` and `## Report` section, and keeps each in `~/.local/state/jbus/<project>/noticed.json`. A line is `Noticed:`, or `Noticed` with a few words after a comma or in parentheses, as `Noticed, from the review:`. The rest of the line is one record. Each line under it that starts with `- `, `* ` or a small letter, as a `follow-up: <finding>` line does, is one more, and an indented line belongs to the item above it. The list ends at a blank line, a heading or a line that starts with a capital, such as `Left:`. A line added to the list later is one new record, and the others keep their marks. A text that is empty or says `none` is no record.

A record has the slug, the section it is from, its text whole, when a pass first saw it, and its mark: `new`, `taken` or `dropped`. Its key is `<slug>:<12 hex>`, the first 12 of the sha256 of its text, so a pass that finds the same line again adds nothing. The first pass of a project, the one that finds no file, marks every line there is then as `dropped`, with the why `from before the list`. jbus writes nothing into a brief, asks you nothing about a line and makes no queue row for one: a home marks each.

| Verb | What it does |
|---|---|
| `jbus noticed` | Prints each new record, newest first, one a line: `<key> <slug>, <section>, new: <text>`. `none is new` when there is none. |
| `jbus noticed --all` | Prints every record, the marked ones with what took them or why they were dropped. |
| `jbus noticed --json` | Prints the same records as a JSON list, with `--all` or without. |
| `jbus noticed --for <home>` | Prints only the new records another home kept for that home. |
| `jbus noticed add --for <home> --from <thread id> <text>` | Keeps one record for the home `--for` names, a scope or `root`, from the home whose thread `--from` is: a finding one home has for another. It prints `kept: <line>`, or `already kept: <line>` for the same text again. A `--for` that is no home of the project, a `--from` that is no home's thread, and a home keeping a record for itself are refused. |
| `jbus noticed take <key> --row <slug> --by <name> --at "<YYYY-MM-DD HH:MM zone>"` | Marks a new record taken by the queue row or the plan entry `--row` names, of any home's `plan.md` or `plan-done.md`. A slug that is neither is refused. |
| `jbus noticed drop <key> --why <words> --by <name> --at "<YYYY-MM-DD HH:MM zone>"` | Marks a new record dropped, with why. |

A record kept with `add` has its slug `home` or `home-<scope>`, the section `from <the home that kept it>`, such as `from root`, and `for` and `from` set.
At the end of each pass, jbus wakes each home at most once for the records and the `--scope` words that are new for it, through the outbox: one message that lists them, sent only while the home has no turn running, and never to the root for a record that is not its own.
A home's start lists its records under "to read".

`--at` is taken as `jbus queue remove` takes it. `--by` is one name, the home's or yours. A record is marked once: a second mark is refused, and so is a key no record has. The view's Noticed panel lists every new record and the 20 newest marked ones, and the wait band counts the new ones.
