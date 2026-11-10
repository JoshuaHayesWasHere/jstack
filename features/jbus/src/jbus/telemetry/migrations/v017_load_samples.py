"""Each row of jgauge's load.tsv (`jgauge.sample`), the machine's."""

from jbus.telemetry.migrations import tables

SQL = tables("load_samples") + "CREATE INDEX load_samples_at ON load_samples (at);\n"
