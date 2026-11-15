"""`python -m app.worker` must start the loop (it is the worker Deployment's command)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_m_app_worker_starts_the_loop() -> None:
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://x:y@127.0.0.1:1/none"}
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, the test runs this interpreter
        [sys.executable, "-m", "app.worker"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    assert "worker started" in out, out[-500:]
