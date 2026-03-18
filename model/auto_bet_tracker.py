from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

RANKED_CARD_PATH = DATA_DIR / "ranked_card.json"
TRACKER_PATH = DATA_DIR / "bet_tracker.csv"
ROI_SUMMARY_PATH = DATA_DIR / "roi_summary.json"


TRACKER_FIELDS = [
    "date",
    "league",
    "game",
    "market",
    "pick",
    "line",
    "odds",
    "stake",
    "tier",
    "score",
    "edge_pct",
    "win_prob",
    "signals",
    "result",
    "final_score",
    "closing_line",
    "clv",
    "profit",
    "notes",
]


@dataclass
class BetRecord:
    date: str
    league: str
    game: str
    market: str
    pick: str
    line: float
    odds: int
    stake: float
    tier: str
    score: float
    edge_pct: float
    win_prob: float
    signals: str = ""
    result: str = "PENDING"
    final_score: str = ""
    closing_line: str = ""
    clv: str = ""
    profit: str = ""
    notes: str = ""


@dataclass
class GradeInput:
    game: str
    market: str
    team_a: str
    team_b: str
    final_a: int
    final_b: int
    closing_line: Optional[float] = None


@dataclass
class RoiSummary:
    total_bets: int
    graded_bets: int
    wins: int
    losses: int
    pushes: int
    pending: int
    total_staked: float
    total_profit: float
    roi_pct: float
    avg_edge_pct: float
    avg_clv: float
    by_tier: dict[str, dict[str, Any]]


def ensure_tracker(path: Path = TRACKER_PATH) -> None:
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS)
        writer.writeheader()


def load_ranked_card(path: Path = RANKED_CARD_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def load_tracker(path: Path = TRACKER_PATH) -> list[dict[str, str]]:
    ensure_tracker(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_tracker(rows: list[dict[str, Any]], path: Path = TRACKER_PATH) -> None:
    ensure_tracker(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in TRACKER_FIELDS})


def american_profit(stake: float, odds: int) -> float:
    if odds > 0:
        return round(stake * odds / 100.0, 2)
    return round(stake * 100.0 / abs(odds), 2)


def infer_market_and_line(best_bet: str) -> tuple[str, float]:
    text = best_bet.strip()
    if text.lower().startswith("over "):
        return "TOTAL", float(text.split(" ", 1)[1])
    if text.lower().startswith("under "):
        return "TOTAL", float(text.split(" ", 1)[1])

    parts = text.rsplit(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"Could not parse best_bet: {best_bet}")
    line = float(parts[1])
    return "SPREAD", line


def ranked_card_to_bets(
    ranked_rows: Iterable[dict[str, Any]],
    *,
    default_date: str,
    default_odds: int = -110,
    stake_map: Optional[dict[str, float]] = None,
) -> list[BetRecord]:
    stake_map = stake_map or {
        "MAX_ELITE": 150.0,
        "ELITE": 100.0,
        "STRONG": 50.0,
        "PASS": 0.0,
    }
    bets: list[BetRecord] = []

    for row in ranked_rows:
        best_bet = row.get("best_bet") or row.get("pick")
        if not best_bet:
            continue

        market, line = infer_market_and_line(best_bet)
        tier = str(row.get("tier", "PASS"))
        stake = float(stake_map.get(tier, 0.0))
        if stake <= 0:
            continue

        raw_signals = row.get("signals", [])
        signals = ",".join(raw_signals) if isinstance(raw_signals, list) else str(raw_signals)

        bets.append(
            BetRecord(
                date=str(row.get("date", default_date)),
                league=str(row.get("league", "")),
                game=str(row.get("game", "")),
                market=market,
                pick=str(best_bet),
                line=line,
                odds=default_odds,
                stake=stake,
                tier=tier,
                score=float(row.get("score", 0.0)),
                edge_pct=float(row.get("edge_pct", 0.0)),
                win_prob=float(row.get("win_prob", 0.0)),
                signals=signals,
            )
        )

    return bets


def append_new_bets(bets: Iterable[BetRecord], path: Path = TRACKER_PATH) -> int:
    rows = load_tracker(path)
    seen = {(r["date"], r["game"], r["pick"], r["market"]) for r in rows}
    added = 0

    for bet in bets:
        key = (bet.date, bet.game, bet.pick, bet.market)
        if key in seen:
            continue

        rows.append({field: getattr(bet, field) for field in TRACKER_FIELDS})
        seen.add(key)
        added += 1

    save_tracker(rows, path)
    return added


def _grade_spread(pick: str, team_a: str, team_b: str, final_a: int, final_b: int, line: float) -> str:
    margin_a = final_a - final_b

    if pick.startswith(team_a):
        adjusted = margin_a + line
    elif pick.startswith(team_b):
        adjusted = -margin_a + line
    else:
        raise ValueError(f"Pick does not match teams for spread grading: {pick}")

    if adjusted > 0:
        return "WIN"
    if adjusted < 0:
        return "LOSS"
    return "PUSH"


def _grade_total(pick: str, final_a: int, final_b: int, line: float) -> str:
    total = final_a + final_b

    if pick.lower().startswith("over"):
        if total > line:
            return "WIN"
        if total < line:
            return "LOSS"
        return "PUSH"

    if pick.lower().startswith("under"):
        if total < line:
            return "WIN"
        if total > line:
            return "LOSS"
        return "PUSH"

    raise ValueError(f"Invalid total pick: {pick}")


def _calc_profit(stake: float, odds: int, result: str) -> float:
    if result == "WIN":
        return american_profit(stake, odds)
    if result == "LOSS":
        return round(-stake, 2)
    return 0.0


def _calc_clv(market: str, pick: str, placed_line: float, closing_line: Optional[float]) -> str:
    if closing_line is None:
        return ""

    if market == "TOTAL":
        if pick.lower().startswith("over"):
            value = closing_line - placed_line
        else:
            value = placed_line - closing_line
    else:
        value = abs(closing_line) - abs(placed_line)

    return f"{value:+.2f}"


def grade_bets(results: Iterable[GradeInput], path: Path = TRACKER_PATH) -> int:
    rows = load_tracker(path)
    result_map = {(r.game, r.market): r for r in results}
    updated = 0

    for row in rows:
        key = (row["game"], row["market"])
        if key not in result_map:
            continue

        grade = result_map[key]
        line = float(row["line"])
        odds = int(row["odds"])
        stake = float(row["stake"])

        if row["market"] == "SPREAD":
            result = _grade_spread(row["pick"], grade.team_a, grade.team_b, grade.final_a, grade.final_b, line)
        else:
            result = _grade_total(row["pick"], grade.final_a, grade.final_b, line)

        profit = _calc_profit(stake, odds, result)
        row["result"] = result
        row["profit"] = f"{profit:.2f}"
        row["final_score"] = f"{grade.team_a} {grade.final_a} - {grade.team_b} {grade.final_b}"
        row["closing_line"] = "" if grade.closing_line is None else f"{grade.closing_line:.2f}"
        row["clv"] = _calc_clv(row["market"], row["pick"], line, grade.closing_line)
        updated += 1

    save_tracker(rows, path)
    return updated


def build_roi_summary(path: Path = TRACKER_PATH, out_path: Path = ROI_SUMMARY_PATH) -> RoiSummary:
    rows = load_tracker(path)
    graded = [r for r in rows if r.get("result") in {"WIN", "LOSS", "PUSH"}]

    wins = sum(1 for r in graded if r["result"] == "WIN")
    losses = sum(1 for r in graded if r["result"] == "LOSS")
    pushes = sum(1 for r in graded if r["result"] == "PUSH")
    pending = len(rows) - len(graded)

    total_staked = round(sum(float(r.get("stake") or 0.0) for r in rows), 2)
    total_profit = round(sum(float(r.get("profit") or 0.0) for r in graded), 2)
    roi_pct = round((total_profit / total_staked * 100.0), 2) if total_staked else 0.0
    avg_edge_pct = round(
        sum(float(r.get("edge_pct") or 0.0) for r in graded) / len(graded), 2
    ) if graded else 0.0

    clv_values: list[float] = []
    for r in graded:
        raw = str(r.get("clv") or "").strip()
        if raw:
            try:
                clv_values.append(float(raw))
            except ValueError:
                pass

    avg_clv = round(sum(clv_values) / len(clv_values), 2) if clv_values else 0.0

    by_tier: dict[str, dict[str, Any]] = {}
    for row in rows:
        tier = row.get("tier", "UNKNOWN")
        by_tier.setdefault(
            tier,
            {
                "bets": 0,
                "graded": 0,
                "wins": 0,
                "losses": 0,
                "pushes": 0,
                "staked": 0.0,
                "profit": 0.0,
            },
        )
        slot = by_tier[tier]
        slot["bets"] += 1
        slot["staked"] = round(slot["staked"] + float(row.get("stake") or 0.0), 2)

        if row.get("result") in {"WIN", "LOSS", "PUSH"}:
            slot["graded"] += 1
            slot["profit"] = round(slot["profit"] + float(row.get("profit") or 0.0), 2)
            if row["result"] == "WIN":
                slot["wins"] += 1
            elif row["result"] == "LOSS":
                slot["losses"] += 1
            else:
                slot["pushes"] += 1

    summary = RoiSummary(
        total_bets=len(rows),
        graded_bets=len(graded),
        wins=wins,
        losses=losses,
        pushes=pushes,
        pending=pending,
        total_staked=total_staked,
        total_profit=total_profit,
        roi_pct=roi_pct,
        avg_edge_pct=avg_edge_pct,
        avg_clv=avg_clv,
        by_tier=by_tier,
    )

    out_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    return summary


def auto_track_from_ranked_card(default_date: str) -> dict[str, Any]:
    ranked = load_ranked_card()
    bets = ranked_card_to_bets(ranked, default_date=default_date)
    added = append_new_bets(bets)
    summary = build_roi_summary()
    return {"added": added, "summary": asdict(summary)}
