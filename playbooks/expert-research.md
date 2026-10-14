# Expert research

Run by: an expert, for a `research` ask: a longer question about its subject, answered in a report file in its folder, where the bulk reading goes to a subagent.

Source: this repo

<!-- card: An expert runs it | 5 | A `research` ask: a longer question about the expert's subject, answered in a report file in its folder, where the bulk reading goes to a subagent. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/expert/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the report.** It is a file in your folder that a fresh thread can answer from. Research only reads, but for writes in the folder: `skills/expert/SKILL.md` "An ask" says how an answer is found.

1. State the question as you read it, in one line, and what would count as an answer. If the scope is unclear, say which reading you took and go on. When the question rests on something false, say so first, with what shows it, and research the question that is left (`principles/attack-the-premise.md`).
2. See what the folder already holds, before anything new is read: the corrections, the notes `notes/INDEX.md` points at for this question, and the earlier reports in `reports/`. Write two lists: what is answered already and by which file, and what is still to read. With nothing left to read, step 3 is `skip: the folder answers it`, and step 4 checks what those files rest on.
3. Send the reading to a subagent (`Explore`), read-only, and keep its conclusion, not its output (`principles/guard-the-context-window.md`). Split a wide question into two to four angles, one subagent each. Give each the question, its angle, the sources from `sources.md` and what step 2 found. Ask each for its findings, each with a file and line at the revision it read, or a link, and for what it could not read. Run it in the background where the session can.
4. Check each finding the report will rest on against the source itself: open the file at the line, as it is now, and name the revision you read (`principles/prove-it-works.md`). A subagent's word is no proof. A finding you did not check goes under "Not checked" or out of the report. Keep three things apart: what was found, what you infer from it, and what is not known. A number comes with what limits it (`principles/explain-the-number.md`).
5. Write the report, `reports/<a few words>.md` in your folder, under a name `reports/` does not hold yet. Read `templates/expert-answer.md` now: the report's headings at that level are its four parts, in its order, and no other. Under the first, the conclusion comes first, then the long form with `###` headings: an explanation as Overview, Key Concepts, How It Works, Where Things Live, Gotchas, dropping any that do not apply, and a choice between alternatives as one recommendation with a table of tradeoffs. The report points at a source, by file and line at a revision, and does not copy it (`principles/laziness-protocol.md`).
6. Add the report's line to `notes/INDEX.md`: the file, what it answers, the revision it was checked at. Write what else was new as "An ask" says: a note, a case, a line in `unknowns.md` for what could not be answered. Then run this with the skill's block at the top, with the report's file name and this thread's id in their places, until it prints `report:`. On `not the expert`, write nothing more in the folder:

   ```sh
   F='<file>'
   ME='<threadId>'
   R="$E/reports/$F"
   want=$(grep '^## ' "$T/expert-answer.md")
   case $F$ME in
   '' | *'<'* | *'>'* | */*) echo "not filled in: put the file name and this thread's id in their places" ;;
   *)
       if [ "$(cat "$E/home-id" 2> /dev/null)" != "$ME" ]; then
           echo "not the expert: $E/home-id does not hold this thread's id"
       elif [ -z "$want" ]; then
           echo "no template: $T/expert-answer.md gave no heading"
       elif [ ! -f "$R" ]; then
           echo "no report: $R is not there"
       elif [ "$(grep '^## ' "$R")" != "$want" ]; then
           echo "not the four parts: the headings of $R must be these, in order, and no other:"
           echo "$want"
       elif ! grep -qF "reports/$F" "$E/notes/INDEX.md" 2> /dev/null; then
           echo "not indexed: notes/INDEX.md has no line for reports/$F"
       else
           echo "report: $R"
       fi ;;
   esac
   ```

7. Reply in the four parts of `templates/expert-answer.md`, short: the answer is the path the block printed and the conclusion in one to three lines, and the other three parts are the report's own, cut to what the conclusion rests on.

Never done here, and who does it:

- **The change the report points to.** The home that owns it decides, with the user: the finding goes to it as a gate, as "What an expert never does" in `skills/expert/SKILL.md` says.
- **A run that writes, or a write outside the folder.** Nobody does here: the report says under "Not checked" what run would answer the question.
- **A copy of a source in the report.** Nobody makes one.
- **Moving a pin in `sources.md`.** A `refresh` ask does. The report says under "Not checked" that the pin is behind.

**Hand over:** in the reply, to whoever asked: the path of the report, its conclusion, what the conclusion rests on, and what was not checked.
