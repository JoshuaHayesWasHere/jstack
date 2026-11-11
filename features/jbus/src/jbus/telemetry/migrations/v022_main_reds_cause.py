"""The `cause` of the line `jbus.mainmoved.tell` writes to `main-reds.jsonl` when a spell of main
ends (`mainmoved.closing_line`), which `main_spells` prefers to the spell's first verdict. The
cursor of `main_reds` goes, so the next build reads the ledger again."""

SQL = (
    "ALTER TABLE main_reds ADD COLUMN cause TEXT;\n"
    "DELETE FROM cursors WHERE source = 'main_reds';\n"
)
