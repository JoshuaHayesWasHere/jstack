from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Gates closed by silence that were wrong (S8)",
    "attention",
    "gates silence closed that a scout labelled corrected or other_done, over those labelled "
    "stood, corrected or other_done; the user's word's own closes counted apart",
    "%",
    5,
    "lower",
    Measured(
        "weekly_wrong_closes",
        "silence_share",
        "silence",
        missing="no scout's gate labels kept for the week",
        detail="'your word ' || word_wrong || ' of ' || word",
    ),
)
