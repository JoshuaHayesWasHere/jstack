# Answering a question

Run by: an expert, for a `question`, an ask inside the charter that a short answer settles: what does X do, where is Y, is Z still so.

Source: this repo

<!-- card: An expert runs it | 1 | A question a short answer settles. The corrections are checked first, then the notes, then the source itself, and the answer has its four parts. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/expert/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the answer, and what the folder knows after it.** `$E` and `$T` are what the block at the top of `skills/expert/SKILL.md` sets. Every call only reads, but for writes in `$E`.

1. Write the question as you read it, and what would count as an answer. Then write what it takes for granted, in one sentence: steps 2 to 4 check that too, and where it is false the answer opens by saying so (`principles/principle-attack-the-premise.md`).
2. Read `$E/corrections.md` whole, again: it is the layer that wins. Write down each one that bears on the question, quoted with its date, or `no correction`. One that settles the question is the answer: steps 3 and 4 then check only what it leaves open.
3. Take from `$E/notes/INDEX.md` the lines the question touches, and open those notes only (`principles/principle-guard-the-context-window.md`). List each claim you will use with its source, the file and line, and the revision it was checked at. With none that fits, write `no note`.
4. Read the source itself, for each claim of step 3 and for what no note covers: a note says where to look and is not the proof (`principles/principle-prove-it-works.md`). Write down the revision you read, beside the one `$E/sources.md` pins. Where the source is past its pin, the answer rests on the source as it is now. Reading past a few files goes to one `Explore` subagent: keep its conclusion, not its output. A question that needs more is `research`: say so in the answer.
5. Put each claim in a tier of `features/why/references/epistemics.md`, which is written for why code exists. For a question, Direct: a correction or the source says it, at the place you cite. Supported: several places agree and none says it outright. Inferred: your reading of them. Speculative: thin evidence, or the model's memory, labelled `from memory, not checked`. Unknown: not found, with where you looked. The answer has the tier of the weakest claim it needs.
6. Write the answer in the four parts of `templates/expert-answer.md`, in its order: read it now. A false premise comes first. A number comes with what limits it (`principles/principle-explain-the-number.md`). Each line under Sources says its layer: a correction, the source or a note. A pin that is behind goes under the last part, with the notes written at it. Run this with the skill's top block, the answer in place of the line in angle brackets, until it prints `four parts, in order`. Then give the answer as it is, in this thread.

   ```sh
   answer=$(cat << 'THE_ANSWER_ENDS_HERE'
   <the answer>
   THE_ANSWER_ENDS_HERE
   )
   printf '%s\n' "$answer" | awk '
       FNR == 1 {file++; part = ""}
       /^## / {if (file == 1) want = want $(0) "\n"; else have = have $(0) "\n"; part = $(0); next}
       file == 1 {
           if (part == "## Confidence") {tiers = $(0); gsub(/[<>]/, " | ", tiers)}
           while (match($(0), /<[^>]*>/)) {holder[substr($(0), RSTART, RLENGTH)]; $(0) = substr($(0), RSTART + RLENGTH)}
           next
       }
       {for (h in holder) if (index($(0), h)) {left = left "\n" $(0); break}}
       NF && part != "" && !(part in filled) {
           filled[part]
           parts++
           if (part == "## Confidence") {sub(/:.*/, ""); known = index(tiers, " | " $(0) " | ")}
       }
       END {
           if (want == "" || have != want) print "not the parts of the template, in its order"
           else if (left != "") print "still the template\047s words:" left
           else if (parts < split(want, each, "\n") - 1) print "a part has nothing under it"
           else if (!known) print "no tier opens the part ## Confidence"
           else print "four parts, in order"
       }' "$T/expert-answer.md" -
   ```
7. Write back what was new, if anything, in `$E` and nowhere else. What the source showed is a note, with its line in `notes/INDEX.md`: each claim names its source and the revision it was checked at, and points there and copies nothing (`principles/principle-laziness-protocol.md`). What happened on this machine is a case in `cases/`. What could not be answered is a line in `unknowns.md`. A note that step 2 or 4 contradicted is fixed now. Read back each file you wrote, and say its path in a line after the answer, outside its four parts.

Never done here, and who does it:

- **The change the answer points to.** The home that owns it decides: the finding goes there as a gate, as `skills/expert/SKILL.md` "What an expert never does" says.
- **A line in `corrections.md`.** The user writes it: ask them to.
- **Moving the pin in `sources.md`.** A `refresh` ask does.
- **An answer outside the charter.** Nobody: one line says so.

**Hand over:** in this thread, to whoever asked: the answer in its four parts, and after it the path of each file step 7 wrote.
