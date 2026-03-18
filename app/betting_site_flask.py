from __future__ import annotations

import csv
import json
import os
import subprocess
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, flash, redirect, render_template_string, request, session, url_for
from werkzeug.utils import secure_filename

from model.auto_bet_tracker import auto_track_from_ranked_card, build_roi_summary


def resolve_base_dir() -> Path:
    file_value = globals().get("__file__")
    if file_value:
        return Path(file_value).resolve().parent.parent
    return Path(os.getcwd()).resolve()


BASE_DIR = resolve_base_dir()
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

RANKED_CARD_PATH = DATA_DIR / "ranked_card.json"
TRACKER_PATH = DATA_DIR / "bet_tracker.csv"
ROI_SUMMARY_PATH = DATA_DIR / "roi_summary.json"
PARSED_LINES_PATH = DATA_DIR / "parsed_lines.csv"

ALLOWED_EXTENSIONS = {"csv", "pdf", "json"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-render")

ADMIN_EMAIL = os.environ.get("APP_LOGIN_EMAIL", "satishsdass@gmail.com")
ADMIN_PASSWORD = os.environ.get("APP_LOGIN_PASSWORD", "airmail23")


def get_python_exec() -> str:
    return os.environ.get("PYTHON_EXECUTABLE", "/opt/render/project/src/.venv/bin/python")


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
