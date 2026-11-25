"""Run InterviewLoop with isolated, disposable data for demo capture."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = PROJECT_ROOT / "demo" / ".capture"
CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("demo_mode", "true")
os.environ.setdefault("INTERVIEWLOOP_DB_PATH", str(CAPTURE_ROOT / "interview_loop.db"))

import interview_loop.config as config

config.DEMO_MODE = True
config.ADMIN_MODE = os.getenv("capture_admin", "false").lower() in {"1", "true", "yes", "on"}
config.SAVE_DIR = CAPTURE_ROOT / "sessions"
config.RECORD_DIR = CAPTURE_ROOT / "records"
config.GLOBAL_STATS_PATH = CAPTURE_ROOT / "weak_stats.json"
config.SAVE_DIR.mkdir(parents=True, exist_ok=True)
config.RECORD_DIR.mkdir(parents=True, exist_ok=True)

runpy.run_path(str(PROJECT_ROOT / "app.py"), run_name="__main__")
