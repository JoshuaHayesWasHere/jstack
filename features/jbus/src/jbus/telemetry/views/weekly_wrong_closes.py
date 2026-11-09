"""Each labelled week's wrong closes of gates (S8) over its known ones (`gate_outcomes`), of the
gates silence closed and, apart, of those the user's word closed, as the weekly report counts them
(`jbus.ci.wrongcloses`). A gate closed any other way, or still open, counts in neither."""

CLOSERS = (("silence", "silence"), ("word", "jbus answer"))
"""The closers S8 counts apart, by the name of their columns: `jbus.questions.SILENCE` and
`COMMAND`, the user's word. `jbus.questions` imports the telemetry package, so they are spelled
here, and a test holds S8 to the weekly report's count, which reads them from there."""

SQL = (
    "SELECT project, week, count(*) AS labels, "
    + ", ".join(
        f"sum(known AND closed_by IS '{closer}') AS {name}, "
        f"sum(wrong AND closed_by IS '{closer}') AS {name}_wrong, "
        f"100.0 * sum(wrong AND closed_by IS '{closer}') "
        f"/ nullif(sum(known AND closed_by IS '{closer}'), 0) AS {name}_share"
        for name, closer in CLOSERS
    )
    + " FROM gate_outcomes GROUP BY project, week"
)
