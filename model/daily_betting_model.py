from __future__ import annotations

import csv
import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "parsed_lines.csv"
OUT_PATH = DATA_DIR / "ranked_card.json"


def to_num(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def project_spread(spread: float, market: str) -> float:
    factor = 0.65
    if market == "1H":
        factor = 0.58
    elif market in {"1Q", "F5", "1P"}:
        factor = 0.52
    return spread * factor


def project_total(total: float, market: str) -> float:
    factor = 0.98
    if market == "1H":
        factor = 0.96
    elif market in {"1Q", "F5", "1P"}:
        factor = 0.94
    return total * factor


def valid_game(row: dict) -> bool:
    team_a = row.get("team_a", "").strip()
    team_b = row.get("team_b", "").strip()
    game = f"{team_a} vs {team_b}"

    if " vs " not in game:
        return False
    if len(team_a) < 3 or len(team_b) < 3:
        return False

    bad = ["USER ID", "CONTINUE", "HTTP", "WT=0", "LINES FROM", "PLEASE SELECT"]
    if any(b in game.upper() for b in bad):
        return False

    market = row.get("market", "").strip().upper()
    if market not in {"FULL", "1H", "1Q", "F5", "1P"}:
        return False

    spread_b = to_num(row.get("spread_b", ""))
    if abs(spread_b) > 30:
        return False

    return True


def tier(edge: float, market: str, bet_type: str, spread: float) -> str:
    adj = edge

    if bet_type == "SPREAD":
        if market == "FULL" and abs(spread) >= 10:
            adj -= 1.5
        if market == "FULL" and abs(spread) in {8.5, 9.5, 10.5}:
            adj -= 1.0

    if adj > 5.5:
        return "MAX_ELITE"
    if adj > 4:
        return "ELITE"
    if adj > 2.5:
        return "STRONG"
    return "PASS"


def choose_pick(team_a: str, team_b: str, spread_a: float, spread_b: float, total: float, market: str):
    proj_s = project_spread(spread_b, market) if spread_b else 0.0
    proj_t = project_total(total, market) if total else 0.0

    edge_spread = abs(proj_s - spread_b) if spread_b else 0.0
    edge_total = abs(proj_t - total) if total else 0.0

    # Favor short spread sides over weak total edges
    short_side_preferred = spread_b and abs(spread_b) <= 4.5 and edge_spread >= 1.25

    if short_side_preferred:
        if proj_s < spread_b:
            return f"{team_a} {spread_a:+}", edge_spread, "SPREAD"
        return f"{team_b} {spread_b:+}", edge_spread, "SPREAD"

    # Only choose total if clearly stronger
    if total and edge_total >= edge_spread + 0.75:
        if proj_t > total:
            return f"Over {total}", edge_total, "TOTAL"
        return f"Under {total}", edge_total, "TOTAL"

    if spread_b:
        if proj_s < spread_b:
            return f"{team_a} {spread_a:+}", edge_spread, "SPREAD"
        return f"{team_b} {spread_b:+}", edge_spread, "SPREAD"

    if total:
        return f"Under {total}", edge_total, "TOTAL"

    return "", 0.0, ""


def build_signals(market: str, bet_type: str, spread: float) -> list[str]:
    signals = [market, bet_type]
    if bet_type == "SPREAD" and market == "FULL" and abs(spread) >= 10:
        signals.insert(0, "BLOWOUT_RISK")
    if bet_type == "SPREAD" and market == "FULL" and abs(spread) in {8.5, 9.5, 10.5}:
        signals.insert(0, "HOOK_RISK")
    return signals


def run():
    rows = []

    with open(CSV_PATH, encoding="utf-8") as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            if not valid_game(row):
                continue

            team_a = row["team_a"].strip()
            team_b = row["team_b"].strip()
            market = row["market"].strip().upper()

            spread_a = to_num(row.get("spread_a", ""))
            spread_b = to_num(row.get("spread_b", ""))
            total = to_num(row.get("total", ""))

            best_bet, edge, bet_type = choose_pick(team_a, team_b, spread_a, spread_b, total, market)
            if not best_bet:
                continue

            rows.append(
                {
                    "game": f"{team_a} vs {team_b}",
                    "market": market,
                    "bet_type": bet_type,
                    "best_bet": best_bet,
                    "score": round(edge, 2),
                    "tier": tier(edge, market, bet_type, spread_b),
                    "win_prob": round(min(75, 50 + edge * 3), 1),
                    "signals": build_signals(market, bet_type, spread_b),
                }
            )

    rows = [r for r in rows if r["tier"] in {"MAX_ELITE", "ELITE", "STRONG"}]
    rows = sorted(rows, key=lambda x: x["score"], reverse=True)

    with open(OUT_PATH, "w", encoding="utf-8") as outfile:
        json.dump(rows, outfile, indent=2)

    print(f"Wrote {len(rows)} picks")


if __name__ == "__main__":
    run()
