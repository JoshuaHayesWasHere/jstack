"""Each code that held a wait `jmerge` recorded, of `jmerge_waits`, and its seconds."""

SQL = (
    "SELECT w.project, w.pr, w.day, w.week, b.key AS code, b.value AS seconds "
    "FROM jmerge_waits w, json_each(w.blockers) b WHERE w.how = 'jmerge'"
)
