"""The command each name after `jstack` runs, and the function its console script runs.

scripts/generate-jstack-trees.py writes this file from each features/*/feature.json's
`commands`: edit those, then run it again."""

COMMANDS = {
    "briefs": ("jbriefs", "jbriefs.cli:main"),
    "bus": ("jbus", "jbus.cli:main"),
    "drift": ("jdrift", "jdrift.cli:main"),
    "gauge": ("jgauge", "jgauge.cli:main"),
    "install": ("jinstall", "jinstall.cli:main"),
    "leak": ("jleak", "jleak.cli:main"),
    "merge": ("jmerge", "jmerge.cli:main"),
    "pack": ("jpack", "jpack.cli:main"),
    "roles": ("jroles", "jroles.cli:main"),
}
