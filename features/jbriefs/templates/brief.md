# <slug>: <one line>
Task: "<the request, in the user's words>"
<A quote on `Task:` holds only words the user typed, as the `Asked:` file has them: the home's own words, such as which slice of the request this brief is, go outside the quotes.>
Done when:
- <a check, ending (in `path/of/the/file`), the file it lands in, under Where, or (in none)>
Proves it: <what outside the agent shows it holds: a test or a command, a metric, a dataset, an external judge or the user, never the crew's own review>
Size: S | M | L
Where: <files or areas it concerns>
Do not touch: <what is out of bounds>
<Each Done when item ends with (in `<path>`), the file the goal needs changed, or (in none) where it changes none: `jbus queue add` refuses a file outside `Where:` or under `Do not touch:`, so that goal goes to a follow-up brief with a `Follows: <slug>` line, and warns of an item with neither.>
Decisions: <any the user already made, in their words>
Asked: $H/asked/<entry>.md
<The line above names the file the home wrote once, when it took the request, with the user's messages of it word for word: every brief cut from that request names the same file.>
<A brief that comes from no message of the user's has no `Asked:` line.>
Shown: <the path of each picture the user sent with the request, as `jbriefs --shown` printed it, and what it shows in a few words, several split by `;`>
<The line above is left out where the user sent no picture.>
Holds: <a case of gates.md the task walks through, word for word, several split by commas>
<The line above is left out when the task walks through no door.>
<A row whose `Done when:` or `Proves it:` runs a door's command holds for that door all the same, and `jbus queue add` prints `holds: <case>, from <the command>` for one no `Holds:` line names.>
<The line below is there only where `/architect` wrote a design for this task.>
Design: <the path of the design `/architect` wrote for this task>
<Every brief has the `Skills:` and `Playbook:` lines, picked together by the kind of task from the table in the home skill's handing-a-task-to-a-crewmate.md: `jbus queue add` refuses a brief with no line, or one that says none.>
Skills: <at least one skill or principle the crewmate runs, comma-separated, by pstack's names: a skill's directory of `skills/`, `architect`, and a principle's directory of `features/principles/skills/`, `principle-model-the-domain`>
Pull request: open one when done | ask first
Review: review | none
<`review`: one review round, launched by jbus at the desk proof, before the pull request opens, whose blocking findings, each with a proof, are answered in the pull request, a fix for them getting no review, and which an old `twice` reads as.>
<`none`: no reviewer, and `jmerge` leaves the pull request to wait for the user's word, so `jbus queue add` warns of it beside `Pull request: open one when done`.>
<`jbus queue add` refuses any other word on the `Review:` line, and `cleanup` on any brief but the day's warnings row, which jbus files.>
Playbook: <a row `a crewmate` runs, from the home skill's block that prints a row for each playbook>
<Every brief has the line below, and it names the home the row is for: `uncategorized` where no scope owns the work, and the scope's name for a scoped home, never `root` or a thread id, since the root home owns no row and `jbus queue add` refuses a brief with no such line, one that names `root`, or one that names no home of the project.>
Home: <uncategorized, or the scope's name>
<The line below is there only for a row queued with `--depends`, and names each row it depends on before a colon with what of its work this row starts from after it, the code this row changes, calls or imports, one item for each and `;` between them, while a plan layer, docs order or a shared file is no such need and an order that is only about merging is `--merge-after` with no line.>
Builds on: <slug>: <what of its work this row starts from>; <slug>: <what of its work>
<The five lines below are there when a scout wrote this brief.>
<A home that writes one from a light scout's answer may fill `Read:`, `Change:` and `Rests on:` from it.>
<Where the home's deeper step ran, for research, perf, analysis or outcome work, the home writes `Read:` and `Instruments:` itself, and `jbus queue add` refuses such a brief without them.>
<Any other brief the home writes leaves all five out.>
Read: <the rawest material to start from: the files, logs or data to read first, each with its path and line and what is there>
Instruments: <each method the work uses, with the command that runs it here>
Change: <the files to change, each with its path and line and what changes>
Rests on: <each finding the brief depends on, with its evidence>
Ruled out: <what was looked at and set aside, and why>
