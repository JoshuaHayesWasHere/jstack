# <slug>: <one line>
Task: "<the request, in the user's words>"
Done when:
- <a check>
Proves it: <what outside the agent shows it holds: a test or a command, a metric, a dataset, an external judge or the user, never the crew's own review>
Size: S | M | L
Where: <files or areas it concerns>
Do not touch: <what is out of bounds>
Decisions: <any the user already made, in their words>
<The two lines below may be left out where they would say none.>
Design: <the path of the design `/architect` wrote for this task> | none, <why it needs no design call>
Skills: <the skills and principles the crewmate runs, comma-separated, by pstack's names: a skill's directory of `skills/`, `architect`, and a principle's directory of `features/principles/skills/`, `principle-model-the-domain`> | none
Pull request: open one when done | ask first
Review: twice | review | none | after
<`after` needs the user's words for it on the Decisions: line.>
Playbook: <a row `a crewmate` runs, from the home skill's block that prints a row for each playbook> | none
<The line below is there only in a brief a scoped home writes, and it is the scope's name, never a thread id. The root home's brief has no `Home:` line.>
Home: <scope>
<The line below is there only for a row queued with `--depends`, and names each row it depends on before a colon with what of its work this row starts from after it, the code this row changes, calls or imports, one item for each and `;` between them, while a plan layer, docs order or a shared file is no such need and an order that is only about merging is `--merge-after` with no line.>
Builds on: <slug>: <what of its work this row starts from>; <slug>: <what of its work>
<The five lines below are there when a scout wrote this brief. A home that writes one from a light scout's answer may fill `Read:`, `Change:` and `Rests on:` from it; any other brief the home writes leaves all five out.>
Read: <the files to read first, each with its path and line and what is there>
Change: <the files to change, each with its path and line and what changes>
Rests on: <each finding the brief depends on, with its evidence>
Sources: <the docs used: the path or URL, and the part that matters>
Ruled out: <what was looked at and set aside, and why>
