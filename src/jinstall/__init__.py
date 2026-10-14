"""jinstall: what `install.sh` runs. Not a seventh command and not in the wheel: it runs
before any command is on PATH, from the checkout, on the standard library alone.

    needs.py     the one list: Level, Need, needs()
    kinds.py     one class for each kind of need: its probe, and for a carried kind its
                 due, put and drop
    machine.py   every effect: files, the two programs the install runs, the record
    __main__.py  the verbs as loops over needs(), the one line shape, the exit codes
"""
