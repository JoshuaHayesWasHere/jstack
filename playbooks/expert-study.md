# Expert study

Run by: an expert, for a `study` ask: working the syllabus into notes, each question read from its source and written down with what it rests on.

Source: this repo

<!-- card: An expert runs it | 3 | A `study` ask: working the syllabus into notes, each question read from its source and written down with what it rests on. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/expert/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the notes.** A fresh thread with only the folder answers from them, so a note holds what the source showed, where, and at which revision, and nothing you only remember. `$E` is the expert's folder, set by the block at the top of `skills/expert/SKILL.md`.

1. List the pass. Read `$E/syllabus.md`, `$E/notes/INDEX.md` and `$E/unknowns.md`, and write in this thread the questions the ask names, or with none named each question that neither file has a line for, in the syllabus's order. A note with no line in the index was cut off: its question comes first, and its file is written again whole. With no `syllabus.md`, tell the user and stop. Say how many you take now, and take them one at a time, steps 2 to 5 for one before the next is opened: the next thread starts from the files, not from this one (`principles/make-operations-idempotent.md`).
2. Find the question's source in `$E/sources.md`, and before reading write down the revision you read it at: the commit `git -C <its checkout> rev-parse HEAD` prints, or for a command or a page the command or link and the time. Then read the lines yourself. A note, a summary and your memory say where to look and prove nothing (`principles/prove-it-works.md`). Reading too wide to hold goes to one `Explore` subagent that returns paths and line ranges: keep its conclusion, and open the lines it names before you cite them (`principles/guard-the-context-window.md`).
3. Test the question, and decide. When the source shows that it rests on something false (what it names is not there, or works another way), the note says so first, with the line that shows it, and then answers the question that stands (`principles/attack-the-premise.md`). When the source does not say, or could not be read, so that the answer would be Unknown or rest on memory alone, write no note: add one line to `$E/unknowns.md`, the question, what you read and what would answer it, and go to the next question.
4. Write the note, `$E/notes/<a few words of the question>.md`, one question a file: the question as its heading, then the four parts of `templates/expert-answer.md`, in its order. Read it now. Every line under Sources is a file and line at the revision of step 2, or the link or command with its time. The note points at the source and copies none of it: quote only the line a claim turns on (`principles/laziness-protocol.md`). What you add from memory is labelled "from memory, not checked". Where the revision of step 2 is past the source's pin, say so under Not checked.
5. Add the note's line to `$E/notes/INDEX.md`, or change the one it has, in this form: `` `<file>`: <the question>, at <revision> ``. A source that had no pin gets the revision of step 2 as its pin in `$E/sources.md`.
6. Check the pass. Run this with the block at the top of `skills/expert/SKILL.md`, with the file names of the notes this pass wrote in place of the words in angle brackets:

   ```sh
   for n in <the notes of this pass>; do
       for part in Answer Sources Confidence 'Not checked'; do
           if [ "$(grep -c "^#* *$part\$" "$E/notes/$n")" != 1 ]; then echo "not once in $n: $part"; fi
       done
   done
   sh "$T/../skills/expert/scripts/lint-notes.sh" "$E"
   ```

   Fix this pass's notes until it names none. An earlier pass's note it names is never patched: its question goes in `$E/unknowns.md`. Then follow one line of each note's Sources back to the source at that revision, and see that the line is there and says what the note says (`principles/prove-it-works.md`).
7. Answer the ask in the four parts of `templates/expert-answer.md`: the notes written and the questions sent to `unknowns.md` under Answer, the sources and revisions read under Sources, and the questions of the syllabus this pass did not reach under Not checked.

Never done here, and who does it:

- **A guess written as a note.** Nobody does. What the source does not show is a line in `$E/unknowns.md`.
- **Moving a pin that is there.** A `refresh` ask does. The note names the revision it read, and says under Not checked that the pin is behind.
- **A change to the syllabus, the charter or `corrections.md`.** The user does. A question the reading raised is a line in `$E/unknowns.md`.
- **The change a finding points to.** The home that owns it decides: send it as a gate, as `skills/expert/SKILL.md` "What an expert never does" says.
- **A copy of the source in the folder.** Nobody does: `$E/sources.md` says where it is.

**Hand over:** in the answer, to the user: the notes written and their lines in `notes/INDEX.md`, the lines added to `unknowns.md`, the revision each source was read at, and the questions left for the next pass.
