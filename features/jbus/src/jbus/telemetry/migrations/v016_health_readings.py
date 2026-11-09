"""Each reading of jbus's health look (`jbus.health.keep`), the machine's."""

from jbus.telemetry.migrations import tables

SQL = tables("health_readings") + "CREATE INDEX health_readings_at ON health_readings (at);\n"
