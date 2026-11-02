---
name: retro
description: "Audit what happened over a past window from the raw records: build a dataset you can rerun, freeze a codebook before reading any outcome, sharpen the prompt, and send scouts, with a second labeller, a red team, and rates that show their row mix. Use for /retro, 'audit what happened over <window>', 'take a census of', 'what went wrong last week'."
disable-model-invocation: true
card: "Make the lesson stick | 4 | Audits a past window from the raw records: a dataset you can rerun, a codebook frozen before any outcome is read, a sharpened prompt and scouts, with a second labeller and a red team. | Reach for it when you want to know what happened over a week, not in one thread. | op: the operator; model: a home"
---

# retro

`reflect` reads one thread's transcript.
This skill reads every record of a window, across threads and projects, and counts before it judges.

Set these first, in every shell, with the window's first day and its length in place of the words in angle brackets:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
start='<YYYY-MM-DD>'
days='<7>'
P=$H/reports/retro-$start-prompt.md
C=$H/reports/retro-$start-codebook.md
A=$H/reports/retro-$start.md
D=$H/reports/retro-$start-data
S=$(realpath ~/.claude/skills/retro 2> /dev/null)/scripts/retro_data.py
echo "retro: $days days from $start, the dataset in $D"
```

## 1. Name the window and the question

Write the prompt, `$P`: the user's ask in their words, the window (`$start`, `$days` days, the user's zone), a base window of the same length just before it where a rate is compared, and the questions the audit answers, one line each.
It is the only input of step 3.

## 2. Build the dataset, twice

This builds every table from jbus's records and T3 Code's messages, read-only, and builds it again to show that the counts hold:

```sh
if [ ! -f "${S:-}" ] || [ -z "${D:-}" ]; then
    echo "no dataset: run the block at the top first, with the window filled in"
elif ! base=$(python3 -c 'import datetime, sys; print(datetime.date.fromisoformat(sys.argv[1]) - datetime.timedelta(days=int(sys.argv[2])))' "$start" "$days" 2> /dev/null); then
    echo "no dataset: $start is not a day or $days is not a number of days"
elif ! first=$(uv run --script "$S" build --start "$start" --days "$days" --base-start "$base" --out "$D"); then
    echo "no dataset: the build failed"
elif [ "$(uv run --script "$S" build --start "$start" --days "$days" --base-start "$base" --out "$D")" != "$first" ]; then
    echo "not rerunnable: a second build printed other counts"
else
    printf '%s\n' "$first"
    echo "rerunnable: the same counts twice"
fi
```

On `rerunnable`, go on.
On anything else, stop and say what it printed: a dataset whose counts move is no ground to label.
The script's docstring is its data dictionary: the tables, the weeks, and the typed-message filter.
Until step 3 ends, read only the counts it printed and `completeness.jsonl`, never a row's outcome.

## 3. Freeze the codebook

Write the codebook, `$C`, from the prompt alone.
It holds:

- each unit (a typed message, a row, a request) with the test that makes a record one;
- each label with its test in the records, one example that passes and one that does not;
- each rate with its numerator, its denominator, and the row mix it reports beside it: the share of each project and of each kind of row in the denominator, in each window, so a rate that moved because the mix moved shows it;
- what counts as verified (rerunnable from `$D` by a command) and what stays inferred (a label one reader gave).

Then freeze it:

```sh
if [ ! -f "${S:-}" ] || [ -z "${C:-}" ]; then
    echo "not frozen: run the block at the top first, with the window filled in"
else
    uv run --script "$S" freeze "$C"
fi
```

It prints `frozen: <sha256>`, writes it beside the codebook, and makes the codebook read-only.
Nobody edits it after that: a scout that needs a change proposes it in its Report, and a new version is a new file beside it, frozen the same way.

## 4. Sharpen the prompt

Run the `sharpen` skill on the prompt, and write its rewrite back into the file, with the dataset's path and the codebook's sha256 in it.

## 5. Send the scouts

Scouts are threads, and only a home launches them.
In a home, say in one line how many scouts start, then run `/swarm` on the sharpened prompt, one scout for each question of the prompt, and two more:

- **A second labeller**: it labels a seeded random sample of the rows the first labeller labelled, by the codebook, without its labels, and reports agreement for each label.
  A label it does not agree with stays inferred in the report.
- **A red team**: once the findings are in, it attacks the three that carry the most weight: another cause that fits the same records, a source the dataset lacks (`completeness.jsonl`), a join that lost rows, a rate whose row mix moved between the windows.

Each scout's request names the dataset, `$D`, the codebook and its sha256 (`uv run --script "$S" check "$C"` prints it), and says that each count it gives is verified or inferred and each rate shows its row mix.
In any other thread, launch nothing: park a gate whose question is whether to run `/swarm` on the prompt in the repo's home, with the default that no swarm runs.

## 6. Report

Write the report, `$A`, one finding to a section, and lead with the one that matters most.
Each finding gives its count or rate, verified or inferred, with its row mix, the second labeller's agreement on its labels, and what the red team found against it.
Close with what the dataset could not see, from `completeness.jsonl`.
