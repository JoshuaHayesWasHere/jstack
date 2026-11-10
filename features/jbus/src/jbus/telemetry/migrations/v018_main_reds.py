"""Why main went red at each tip `jbus.mainmoved.tell` judged `failed` (`main-reds.jsonl`)."""

from jbus.telemetry.migrations import tables

SQL = tables("main_reds") + "CREATE INDEX main_reds_sha ON main_reds (project, sha);\n"
