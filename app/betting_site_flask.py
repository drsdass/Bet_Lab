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


def load_ranked_card() -> list[dict]:
    if not RANKED_CARD_PATH.exists():
        return []
    try:
        raw = RANKED_CARD_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def load_tracker_rows() -> list[dict]:
    if not TRACKER_PATH.exists():
        return []
    try:
        with TRACKER_PATH.open("r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_roi_summary() -> dict[str, Any]:
    if not ROI_SUMMARY_PATH.exists():
        summary = build_roi_summary()
        return {
            "total_bets": summary.total_bets,
            "graded_bets": summary.graded_bets,
            "wins": summary.wins,
            "losses": summary.losses,
            "pushes": summary.pushes,
            "pending": summary.pending,
            "total_staked": summary.total_staked,
            "total_profit": summary.total_profit,
            "roi_pct": summary.roi_pct,
            "avg_edge_pct": summary.avg_edge_pct,
            "avg_clv": summary.avg_clv,
            "by_tier": summary.by_tier,
        }
    try:
        raw = ROI_SUMMARY_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            raise ValueError("Empty ROI summary")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        summary = build_roi_summary()
        return {
            "total_bets": summary.total_bets,
            "graded_bets": summary.graded_bets,
            "wins": summary.wins,
            "losses": summary.losses,
            "pushes": summary.pushes,
            "pending": summary.pending,
            "total_staked": summary.total_staked,
            "total_profit": summary.total_profit,
            "roi_pct": summary.roi_pct,
            "avg_edge_pct": summary.avg_edge_pct,
            "avg_clv": summary.avg_clv,
            "by_tier": summary.by_tier,
        }


def build_run_output(stdout: str | None, stderr: str | None) -> str:
    out = stdout or ""
    if stderr:
        out += "\n" + stderr
    return out


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_email"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def run_subprocess(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    output = build_run_output(result.stdout, result.stderr)
    return result.returncode, output


def auto_run_pipeline_for_pdf(pdf_path: Path) -> tuple[bool, str]:
    python_exec = get_python_exec()
    logs: list[str] = []

    code, output = run_subprocess(
        [python_exec, "-m", "model.pdf_line_parser", str(pdf_path), "--output", str(PARSED_LINES_PATH)]
    )
    logs.append("=== PDF PARSER ===")
    logs.append(output or "(no parser output)")
    if code != 0:
        return False, "\n\n".join(logs)

    code, output = run_subprocess([python_exec, "-m", "model.daily_betting_model"])
    logs.append("=== DAILY MODEL ===")
    logs.append(output or "(no model output)")
    if code != 0:
        return False, "\n\n".join(logs)

    try:
        tracking = auto_track_from_ranked_card(default_date="2026-03-18")
        added = tracking.get("added", 0)
        roi = tracking.get("summary", {}).get("roi_pct", 0.0)
        logs.append("=== AUTO TRACKER ===")
        logs.append(f"Added {added} new bets")
        logs.append(f"ROI: {roi}%")
    except Exception as exc:
        logs.append("=== AUTO TRACKER ===")
        logs.append(f"Tracker update failed: {exc}")
        return False, "\n\n".join(logs)

    return True, "\n\n".join(logs)


BASE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
    .wrap { max-width:1300px; margin:40px auto; padding:24px; }
    .card { background:#111827; border:1px solid #334155; border-radius:16px; padding:20px; margin-bottom:20px; }
    .btn { display:inline-block; background:#2563eb; color:white; padding:10px 14px; border-radius:10px; text-decoration:none; border:none; cursor:pointer; }
    .btn.secondary { background:#334155; }
    input, select { width:100%; padding:10px; border-radius:8px; border:1px solid #475569; background:#0f172a; color:#e2e8f0; }
    table { width:100%; border-collapse:collapse; }
    th, td { padding:10px; border-bottom:1px solid #334155; text-align:left; vertical-align:top; }
    .flash { padding:12px; margin-bottom:16px; border-radius:10px; }
    .error { background:#7f1d1d; }
    .success { background:#14532d; }
    a { color:#93c5fd; }
    .grid { display:grid; grid-template-columns:repeat(4, 1fr); gap:16px; }
    .metric { font-size:28px; font-weight:bold; margin-top:8px; }
    .subtle { color:#94a3b8; font-size:14px; }
    .pill { display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; margin-right:6px; background:#1e293b; }
    .pill.max { background:#14532d; }
    .pill.elite { background:#1d4ed8; }
    .pill.strong { background:#92400e; }
    .pill.pass { background:#475569; }
    pre { white-space:pre-wrap; }
    h2 { margin-top:0; }
    @media (max-width: 900px) {
      .grid { grid-template-columns:repeat(2, 1fr); }
    }
  </style>
</head>
<body>
<div class="wrap">
  {{ body|safe }}
</div>
</body>
</html>
"""


def render_page(title: str, body: str) -> str:
    return render_template_string(BASE_HTML, title=title, body=body)


def tier_badge(tier: str) -> str:
    t = (tier or "").upper()
    css = "pass"
    if t == "MAX_ELITE":
        css = "max"
    elif t == "ELITE":
        css = "elite"
    elif t == "STRONG":
        css = "strong"
    return f'<span class="pill {css}">{t}</span>'


def market_badge(market: str) -> str:
    m = (market or "").upper()
    color = "#334155"
    if m == "FULL":
        color = "#1d4ed8"
    elif m == "1H":
        color = "#7c3aed"
    elif m == "1Q":
        color = "#0f766e"
    elif m == "F5":
        color = "#92400e"
    elif m == "1P":
        color = "#be123c"
    return f'<span class="pill" style="background:{color};">{m}</span>'


def bet_type_badge(bet_type: str) -> str:
    b = (bet_type or "").upper()
    color = "#475569"
    if b == "SPREAD":
        color = "#2563eb"
    elif b == "TOTAL":
        color = "#059669"
    elif b == "MONEYLINE":
        color = "#b45309"
    return f'<span class="pill" style="background:{color};">{b}</span>'


@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_email") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if email == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
            session["user_email"] = email
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")

    body = """
    <div class="card">
      <h1>Satish’s Betting Lab</h1>
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endwith %}
      <form method="post">
        <p>Email</p>
        <input type="email" name="email" value="satishsdass@gmail.com">
        <p>Password</p>
        <input type="password" name="password">
        <br><br>
        <button class="btn" type="submit">Sign in</button>
      </form>
    </div>
    """
    return render_page("Login", render_template_string(body))


@app.route("/dashboard")
@login_required
def dashboard():
    summary = load_roi_summary()

    by_tier_rows = ""
    by_tier = summary.get("by_tier", {})
    for tier, values in by_tier.items():
        by_tier_rows += f"""
        <tr>
          <td>{tier}</td>
          <td>{values.get('bets', 0)}</td>
          <td>{values.get('graded', 0)}</td>
          <td>{values.get('wins', 0)}</td>
          <td>{values.get('losses', 0)}</td>
          <td>{values.get('pushes', 0)}</td>
          <td>{values.get('profit', 0.0)}</td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h1>Dashboard</h1>
      <p>
        <a href="{url_for('picks')}">Picks</a> |
        <a href="{url_for('tracker')}">Tracker</a> |
        <a href="{url_for('uploads')}">Uploads</a> |
        <a href="{url_for('logout')}">Logout</a>
      </p>
    </div>

    <div class="grid">
      <div class="card"><div class="subtle">Total Bets</div><div class="metric">{summary.get('total_bets', 0)}</div></div>
      <div class="card"><div class="subtle">Graded Bets</div><div class="metric">{summary.get('graded_bets', 0)}</div></div>
      <div class="card"><div class="subtle">ROI %</div><div class="metric">{summary.get('roi_pct', 0.0)}%</div></div>
      <div class="card"><div class="subtle">Profit</div><div class="metric">{summary.get('total_profit', 0.0)}</div></div>
    </div>

    <div class="card">
      <h3>Performance by Tier</h3>
      <table>
        <thead>
          <tr>
            <th>Tier</th><th>Bets</th><th>Graded</th><th>Wins</th><th>Losses</th><th>Pushes</th><th>Profit</th>
          </tr>
        </thead>
        <tbody>
          {by_tier_rows or '<tr><td colspan="7">No tier data yet.</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    return render_page("Dashboard", body)


@app.route("/picks")
@login_required
def picks():
    ranked = load_ranked_card()

    max_elite = [r for r in ranked if r.get("tier") == "MAX_ELITE"]
    elite = [r for r in ranked if r.get("tier") == "ELITE"]

    def build_rows(items: list[dict]) -> str:
        rows = ""
        for r in items:
            signals = ", ".join(r.get("signals", [])) if isinstance(r.get("signals"), list) else str(r.get("signals", ""))
            rows += f"""
            <tr>
              <td>{r.get('game')}</td>
              <td>{market_badge(r.get('market', ''))}</td>
              <td>{bet_type_badge(r.get('bet_type', ''))}</td>
              <td><strong>{r.get('best_bet')}</strong></td>
              <td>{tier_badge(r.get('tier', ''))}</td>
              <td>{r.get('score')}</td>
              <td>{r.get('win_prob')}%</td>
              <td>{signals}</td>
            </tr>
            """
        return rows

    body = f"""
    <div class="card">
      <h1>Picks</h1>
      <p><a href="{url_for('dashboard')}">Dashboard</a></p>
      <p class="subtle">
        FULL = full game, 1H = first half, 1Q = first quarter, F5 = first 5 innings, 1P = first period
      </p>
    </div>

    <div class="card">
      <h2>MAX ELITE</h2>
      <table>
        <thead>
          <tr>
            <th>Game</th>
            <th>Market</th>
            <th>Type</th>
            <th>Pick</th>
            <th>Tier</th>
            <th>Score</th>
            <th>Win Prob</th>
            <th>Signals</th>
          </tr>
        </thead>
        <tbody>
          {build_rows(max_elite) or '<tr><td colspan="8">No Max Elite picks.</td></tr>'}
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>ELITE</h2>
      <table>
        <thead>
          <tr>
            <th>Game</th>
            <th>Market</th>
            <th>Type</th>
            <th>Pick</th>
            <th>Tier</th>
            <th>Score</th>
            <th>Win Prob</th>
            <th>Signals</th>
          </tr>
        </thead>
        <tbody>
          {build_rows(elite) or '<tr><td colspan="8">No Elite picks.</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    return render_page("Picks", body)


@app.route("/tracker")
@login_required
def tracker():
    rows_data = load_tracker_rows()

    rows = ""
    for r in rows_data:
        market = r.get("market", "")
        pick = r.get("pick", "")
        tier = r.get("tier", "")
        result = r.get("result", "")
        profit = r.get("profit", "")
        clv = r.get("clv", "")
        final_score = r.get("final_score", "")

        bet_type = "SPREAD"
        if str(pick).lower().startswith(("over ", "under ")):
            bet_type = "TOTAL"

        rows += f"""
        <tr>
          <td>{r.get('date')}</td>
          <td>{r.get('game')}</td>
          <td>{market_badge(market)}</td>
          <td>{bet_type_badge(bet_type)}</td>
          <td><strong>{pick}</strong></td>
          <td>{tier_badge(tier)}</td>
          <td>{r.get('stake')}</td>
          <td>{result}</td>
          <td>{profit}</td>
          <td>{clv}</td>
          <td>{final_score}</td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h1>Bet Tracker</h1>
      <p><a href="{url_for('dashboard')}">Dashboard</a></p>
      <p class="subtle">
        FULL = full game, 1H = first half, 1Q = first quarter, F5 = first 5 innings, 1P = first period
      </p>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Game</th>
            <th>Market</th>
            <th>Type</th>
            <th>Pick</th>
            <th>Tier</th>
            <th>Stake</th>
            <th>Result</th>
            <th>Profit</th>
            <th>CLV</th>
            <th>Final</th>
          </tr>
        </thead>
        <tbody>
          {rows or '<tr><td colspan="11">No tracker rows yet.</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    return render_page("Tracker", body)


@app.route("/uploads", methods=["GET", "POST"])
@login_required
def uploads():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Please choose a file.", "error")
            return redirect(url_for("uploads"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("uploads"))

        filename = secure_filename(file.filename)
        destination = UPLOAD_DIR / filename
        file.save(destination)

        if destination.suffix.lower() == ".pdf":
            success, pipeline_output = auto_run_pipeline_for_pdf(destination)
            session["run_output"] = pipeline_output
            if success:
                flash(f"Uploaded {filename} and auto-ran the full pipeline.", "success")
            else:
                flash(f"Uploaded {filename}, but the auto-run pipeline failed.", "error")
        else:
            session["run_output"] = f"Uploaded {filename}. Auto-run is enabled only for PDFs."
            flash(f"Uploaded {filename}", "success")

        return redirect(url_for("uploads"))

    uploaded = sorted(UPLOAD_DIR.iterdir()) if UPLOAD_DIR.exists() else []
    uploaded_html = "".join(f"<li>{p.name}</li>" for p in uploaded if p.is_file())
    run_output = session.pop("run_output", "")

    body = f"""
    <div class="card">
      <h1>Uploads</h1>
      <p><a href="{url_for('dashboard')}">Dashboard</a></p>
      {{% with messages = get_flashed_messages(with_categories=true) %}}
        {{% for category, message in messages %}}
          <div class="flash {{{{ category }}}}">{{{{ message }}}}</div>
        {{% endfor %}}
      {{% endwith %}}
      <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <br><br>
        <button class="btn" type="submit">Upload PDF and auto-run</button>
      </form>
      <br>
      <form method="post" action="{url_for('run_model')}">
        <button class="btn secondary" type="submit">Run model + auto track manually</button>
      </form>
      <br>
      <h3>Uploaded files</h3>
      <ul>{uploaded_html or '<li>No files yet.</li>'}</ul>
      <h3>Run output</h3>
      <pre>{run_output or 'No run output yet.'}</pre>
    </div>
    """
    return render_page("Uploads", render_template_string(body))


@app.route("/run-model", methods=["POST"])
@login_required
def run_model():
    python_exec = get_python_exec()

    code, output = run_subprocess([python_exec, "-m", "model.daily_betting_model"])
    track_msg = ""

    if code == 0:
        try:
            tracking = auto_track_from_ranked_card(default_date="2026-03-18")
            added = tracking.get("added", 0)
            roi = tracking.get("summary", {}).get("roi_pct", 0.0)
            track_msg = f"\n\n=== AUTO TRACKER ===\nAdded {added} bets\nROI: {roi}%"
        except Exception as exc:
            track_msg = f"\n\n=== AUTO TRACKER ===\nTracker update failed: {exc}"

    session["run_output"] = output + track_msg

    if code == 0:
        flash("Manual model run completed.", "success")
    else:
        flash("Manual model run failed.", "error")

    return redirect(url_for("uploads"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def safe_run_server() -> None:
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
        use_debugger=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    safe_run_server()
