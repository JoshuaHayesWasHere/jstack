"""Each call's reasoning effort, as its transcript's lines name it (`tokens`), and the copy of it
for the calls the store already holds: the cursor of each transcript that names one goes
(`tokens.REREAD`), so the next build reads each one still on disk again, and the copy sets only
the effort of a call it holds (`tokens.CALL_INSERT`). A call whose transcript is gone keeps no
effort."""

from jbus.telemetry.tokens import REREAD

SQL = f"ALTER TABLE calls ADD COLUMN effort TEXT;\n{REREAD}"
