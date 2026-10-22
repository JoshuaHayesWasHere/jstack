"""jinstall is what `install.sh` runs from a checkout, before any command is on PATH, with the
standard library alone. It is also the `jinstall` command that a release installs, with no
checkout.

    needs.py     the one list: Level, Need, needs()
    kinds.py     one class for each kind of need: its probe, and for a carried kind its
                 due, put and drop
    machine.py   every effect: files, the two programs the install runs, the record
    harnesses.py the harnesses installed for: Claude Code, Codex, Cursor
    layout.py    each harness's layout, assembled from the source, and its need
    links.py     the relative links of a Markdown file the layout places elsewhere
    terms.py     what each harness leaves out
    __main__.py  the verbs as loops over needs(), the one line shape, the exit codes
    cli.py       `jinstall`, the verbs for the checkout above it or the release's source
"""
