# <slug>: <one line on what to find out>
Request: "<what the user asked for, in their words>"
Questions:
- <a question the report must answer, with where to start looking>
Deliver:
- Under "## Report" in this file: the findings with their evidence, a recommendation, and proposed plan entries, each with a "Done when" list.
- <a brief for the crewmate, at `tasks/<slug>.md` | a visual page on Lavish, saved under `reports/` | leave this line out>
Playbook: <a row `a scout` runs, from the home skill's block that prints a row for each playbook> | none
Out of bounds: read-only. <what the scout must not run, start or touch>
<Every request has the line below, and it names the home the scout reports to: `root` for the root home, and the scope's name for a scoped home, never a thread id, since `jbus queue add` refuses a request with no such line, or one that names no home of the project.>
Home: <root, or the scope's name>
