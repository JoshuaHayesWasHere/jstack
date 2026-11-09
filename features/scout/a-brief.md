**A brief, when the request asks for one.**
Write `$H/tasks/<slug>.md` in the brief's usual shape, `$T/brief.md`.
The "Done when" list is checks a person or a command can run.
Fill in the six lines the template keeps for a scout, `Read:`, `Instruments:`, `Change:`, `Rests on:`, `Sources:` and `Ruled out:`, so that a fresh crewmate can trust the brief and not research again.
Its `Rests on:` line holds each finding of the Report that the brief depends on, with that finding's evidence.
Its `Ruled out:` line holds each item of the Report's `Ruled out:` that concerns a file on the brief's `Where:` line.
Before you end, read the brief against the Report once, and fix each line of the brief that says what the Report does not say, or the opposite of what it says.
Its `Playbook:` line is picked from the rows that the block in `$T/../skills/home/SKILL.md` "Handing a task to a crewmate" prints, one for each playbook: run that block and pick as the text under it says.
Its `Home:` line is the request's, copied: the crewmate reports to the home that sent the scout.
A request with no `Home:` line, or one from before that names `root`, is the catch-all's: write `Home: uncategorized`, and never leave the template's placeholder in.
