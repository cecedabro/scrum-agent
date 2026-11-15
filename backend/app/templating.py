"""Shared Jinja2 environment for all routers.

Globals ``datum``, ``datum_kort``, ``relatief``, ``TIMEZONE`` and
``STATUS_LABELS`` plus the ``datum_kort`` filter are registered once
here; every router imports ``templates`` from this module.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import TIMEZONE
from app.fmt import datum, datum_kort, relatief

STATUS_LABELS = {
    "queued": "in de wachtrij",
    "running": "bezig",
    "done": "klaar",
    "failed": "mislukt",
}

_templates_dir = Path(__file__).resolve().parent / "templates"
env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=select_autoescape(),
)
env.globals["datum"] = datum
env.globals["datum_kort"] = datum_kort
env.globals["relatief"] = relatief
env.globals["TIMEZONE"] = TIMEZONE
env.globals["STATUS_LABELS"] = STATUS_LABELS
env.filters["datum_kort"] = datum_kort

templates = Jinja2Templates(env=env)
