from jbus.telemetry.kpis import ROWS, Kpi, Measured

KPI = Kpi(
    "Rows finished with no further word",
    "autonomy",
    "merged rows with no message you typed after their go naming them: cited by an act on "
    "the row, or typed in its crew's thread (S1)",
    "%",
    95,
    "higher",
    Measured("weekly_no_word", "share", "merged", since="rows_since", records=ROWS),
)
