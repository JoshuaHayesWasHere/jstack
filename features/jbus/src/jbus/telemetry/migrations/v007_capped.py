"""Each read of which instances are capped (`jgauge.limits.note`), the machine's."""

from jbus.telemetry.migrations import tables

SQL = tables("capped_reads") + "CREATE INDEX capped_reads_at ON capped_reads (at);\n"
