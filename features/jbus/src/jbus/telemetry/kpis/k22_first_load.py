from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Crew first load, KB (jstack's own)",
    "cost",
    "the installed crew SKILL.md and its largest playbook print, read before a crew's work",
    "KB",
    16,
    "lower",
    Measured("weekly_first_load", "kb", "installs", machine=True),
)
