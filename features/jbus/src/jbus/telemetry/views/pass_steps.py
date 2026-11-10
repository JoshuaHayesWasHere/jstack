"""Each step of each jbus pass (`passes.jsonl`, `jbus.record`), a row a step: the pass's key and
start, the step's name, and its wall and CPU seconds. A step named `<part>/<step>` runs inside a
part of the pass in each project, summed over projects; one with no `/` is a part of the pass."""

SQL = (
    "SELECT p.project, p.key AS pass, p.at, p.day, s.key AS step, "
    "json_extract(s.value, '$[0]') AS seconds, json_extract(s.value, '$[1]') AS cpu "
    "FROM passes AS p, json_each(p.step_times) AS s WHERE p.step_times IS NOT NULL"
)
