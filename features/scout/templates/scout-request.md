# <slug>: <one line on what to find out>
Request: "<what the user asked for, in their words>"
Questions:
- <a question the report must answer, with where to start looking>
Deliver:
- Under "## Report" in this file: the findings with their evidence, a recommendation, and proposed plan entries, each with a "Done when" list.
- <a brief for the crewmate, at `tasks/<slug>.md` | a visual, an HTML file saved under `reports/` | leave this line out>
Playbook: <a row `a scout` runs, from the home skill's block that prints a row for each playbook> | none
Model: <a model id, such as claude-fable-5-2, that the scout launches on in place of the role map's scout model, on that line's provider, pool and options> | <leave this line out to launch on the role map's scout model>
Out of bounds: read-only. <what the scout must not run, start or touch>
<Every request has the line below, and it names the home the scout reports to: `uncategorized` where no scope owns the work, and the scope's name for a scoped home, never `root` or a thread id, since the root home owns no row and `jbus queue add` refuses a request with no such line, one that names `root`, or one that names no home of the project.>
Home: <uncategorized, or the scope's name>
