"""Human-owned pytest hook for tests written ahead of the code (protected path).

A test module with `PENDING_UNTIL = "T24"` belongs to a task that is not built yet. While
that task is still open in PLAN.md (`- [ ]` or `- [~]`), its tests are skipped in a plain
`pytest` / `make check` run, so other tasks are not blocked by them. When the file is named
on the command line (the task's own `accept:` command), they always run. Once the harness
marks the task `[x]`, they run everywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLAN = Path(__file__).resolve().parents[1] / "PLAN.md"


def _open_tasks() -> set[str]:
    if not PLAN.exists():
        return set()
    return set(re.findall(r"^- \[[ ~]\] (T\d+):", PLAN.read_text(), re.MULTILINE))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    open_tasks = _open_tasks()
    base = config.invocation_params.dir
    named = {(base / a.split("::")[0]).resolve() for a in config.args if ".py" in a}
    for item in items:
        task = getattr(getattr(item, "module", None), "PENDING_UNTIL", None)
        if task in open_tasks and item.path.resolve() not in named:
            item.add_marker(pytest.mark.skip(reason=f"written ahead for {task}, not built yet"))
