"""Dutch date formatting helpers – registered as Jinja filters.

No ``locale`` module – pure string operations.
"""

from datetime import date, datetime

from app.config import TIMEZONE

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef]

_LOCAL_TZ = ZoneInfo(TIMEZONE)

_WD = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_WD_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]

_MONTHS = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]
_MONTHS_KORT = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def datum(d: date) -> str:
    """ "maandag 16 november" (full weekday + day + full month, no year)."""
    if isinstance(d, datetime):
        d = d.date()
    wd = _WD[d.weekday()]
    mo = _MONTHS[d.month - 1]
    return f"{wd} {d.day} {mo}"


def datum_kort(d: date) -> str:
    """ "ma 16 nov" (short weekday + day + short month)."""
    if isinstance(d, datetime):
        d = d.date()
    wd = _WD_KORT[d.weekday()]
    mo = _MONTHS_KORT[d.month - 1]
    return f"{wd} {d.day} {mo}"


def relatief(d: date, today: date | None = None) -> str:
    """Relative label: \"vandaag\" / \"morgen\" / \"over 3 dagen\" /
    \"gisteren\" / \"3 dagen geleden\"."""
    if today is None:
        from app.clock import today_local

        today = today_local()

    delta = (d - today).days
    if delta == 0:
        return "vandaag"
    if delta == 1:
        return "morgen"
    if delta == -1:
        return "gisteren"
    if delta > 0:
        return f"over {delta} dagen"
    # delta < -1
    abs_d = abs(delta)
    return f"{abs_d} dagen geleden"


def register_filters(app) -> None:  # type: ignore[no-untyped-def]
    """Register the formatting functions as Jinja2 template filters."""
    app.jinja_env.filters["datum"] = datum
    app.jinja_env.filters["datum_kort"] = datum_kort
    app.jinja_env.filters["relatief"] = relatief
