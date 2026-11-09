"""What each brief version's `Pull request:` line asks (`history.pull`): `open`, `ask` or `none`.
The cursors of `brief_versions` go, so the next build reads each `brief-versions.jsonl` again and
fills `pull` for the lines written before `history.brief` wrote it, from each version's kept text
where that is there (`records._kept_pull`). A line whose text is gone keeps no `pull`."""

SQL = (
    "ALTER TABLE brief_versions ADD COLUMN pull TEXT;\n"
    "DELETE FROM cursors WHERE source = 'brief_versions';\n"
)
