from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Drift: standing words broken (S4)",
    "attention",
    "probed standing instructions broken at the week's end",
    "",
    0,
    "lower",
    Lacks("the probes run each week: they are a fixed list run by hand"),
)
