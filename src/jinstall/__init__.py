"""jinstall: what `install.sh` runs from a checkout, before any command is on PATH and on the
standard library alone, and the `jinstall` command a release installs, with no checkout.

    needs.py     the one list: Level, Need, needs()
    kinds.py     one class for each kind of need: its probe, and for a carried kind its
                 due, put and drop
    machine.py   every effect: files, the two programs the install runs, the record
    __main__.py  the verbs as loops over needs(), the one line shape, the exit codes
    cli.py       `jinstall`, the verbs for the checkout above it or the release's copy
"""
