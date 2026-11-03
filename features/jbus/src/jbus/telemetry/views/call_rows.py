"""Each agent call with its session's thread, project, role and slug, and its spend in `jgauge
spend`'s units (`jbus.telemetry.schema.UNITS`)."""

from jbus.telemetry.schema import UNITS

SQL = (
    "SELECT c.provider, c.call, c.session, c.agent, c.at, c.day, c.model, c.input, "
    "c.cache_write, c.cache_read, c.output, c.final, s.thread, s.instance, s.project, "
    "s.role, s.slug, "
    f"{UNITS} AS units FROM calls c "
    "LEFT JOIN sessions s ON s.provider = c.provider AND s.session = c.session"
)
