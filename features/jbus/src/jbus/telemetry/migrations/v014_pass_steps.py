"""Each pass's `step_times`, the `[wall, cpu]` seconds of each of its steps by name as JSON, and
the CPU seconds of its `children` (`jbus.record`). The view `pass_steps` reads a row a step. A
pass the store read before this, or whose line has neither, has neither."""

SQL = (
    "ALTER TABLE passes ADD COLUMN step_times TEXT;\nALTER TABLE passes ADD COLUMN children REAL;\n"
)
