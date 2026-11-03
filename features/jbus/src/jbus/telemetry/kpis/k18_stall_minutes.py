from jbus.telemetry.kpis import Covers, Kpi, Measured

KPI = Kpi(
    "Stall minutes per merged row",
    "speed",
    "minutes a running row's threads were quiet or hung, from their last write, over the "
    "rows merged in the week",
    "min",
    None,
    "lower",
    Measured(
        "weekly_stall",
        "per_row",
        "merged",
        covers=Covers("stall_projects", "stall_gaps", "stall record"),
    ),
)
