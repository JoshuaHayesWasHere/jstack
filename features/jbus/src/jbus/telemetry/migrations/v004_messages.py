"""The messages of T3 Code's threads (`jbus.telemetry.messages`), and the index by which an act
finds the message it cites."""

from jbus.telemetry import messages

SQL = messages.TABLE_SQL + "CREATE INDEX acts_ref ON acts (ref);\n"
