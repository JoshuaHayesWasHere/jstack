"""The parent a follow-up's go names (`queue.Approval.follows`), and each revert jbus opened
(`jmerge.reverts`): the records the view `redos` joins. The queue is read again on the next
build, so each row it already holds gets its `follows`."""

from jbus.telemetry.migrations import tables

SQL = (
    "ALTER TABLE queue ADD COLUMN follows TEXT;\n"
    + tables("reverts")
    + "DELETE FROM cursors WHERE source = 'queue';\n"
)
