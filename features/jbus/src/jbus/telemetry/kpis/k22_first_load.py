from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Crew first load, KB (jstack's own)",
    "cost",
    "skill and playbook read before a crew's work",
    "KB",
    16,
    "lower",
    Lacks("the installed files' size as a record a week: it is measured by hand"),
)
