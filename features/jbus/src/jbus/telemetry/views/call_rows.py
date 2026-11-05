"""Each agent call with its session's thread, project, role and slug, the reasoning `effort` its
transcript named (NULL where it named none, as a Codex call's and one an older agent wrote),
its spend in `jgauge spend`'s units (`jbus.telemetry.schema.UNITS`), and its estimated dollars
at `jgauge.spend`'s price table (`jbus.telemetry.schema.DOLLARS`), NULL for a model the table
does not price."""

from jbus.telemetry.schema import DOLLARS, UNITS

SQL = (
    "SELECT c.provider, c.call, c.session, c.agent, c.at, c.day, c.model, c.input, "
    "c.cache_write, c.cache_read, c.output, c.final, c.effort, s.thread, s.instance, s.project, "
    "s.role, s.slug, "
    f"{UNITS} AS units, {DOLLARS} AS dollars FROM calls c "
    "LEFT JOIN sessions s ON s.provider = c.provider AND s.session = c.session"
)
