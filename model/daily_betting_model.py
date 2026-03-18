from __future__ import annotations

import csv
import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "parsed_lines.csv"
OUT_PATH = DATA_DIR / "ranked_card.json"


def to_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def project_spread(spread: float, market: str) -> float:
    factor = 0.65
    if market == "1H":
        factor = 0.58
    elif market == "1Q":
        factor = 0.52
    return spread * factor


def project_total(total: float, market: str) -> float:
    factor = 0.98
    if market == "1H":
        factor = 0.96
    elif market == "1Q":
        factor = 0.94
    return total * factor


def classify_tier(edge: float) -> str:
    if edge > 5.5:
        return "MAX_ELITE"
    if edge > 4.0:
        return "ELITE"
    if edge > 2.5:
        return "STRONG"
    return "PASS"


def valid_market(market: str) -> bool:
    return market in {"FULL", "1H", "1Q", "F5", "1P"}


def valid_spread(value: float) -> bool:
    return abs(value) <= 30


def run():
    rows = []

    if not CSV_PATH.exists():
        print(f"Missing parsed CSV: {CSV_PATH}")
        with open(OUT_PATH, "w", encoding="utf-8") as out_file:
            json.dump([], out_file, indent=2)
        return

    with open(CSV_PATH, "r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for record in reader:
            team_a = str(record.get("team_a", "")).strip()
            team_b = str(record.get("team_b", "")).strip()
            market = str(record.get("market", "")).strip().upper()
            league = str(record.get("sport", "")).strip().upper()

            if not team_a or not team_b:
                continue
            if team_a == team_b:
                continue
            if not valid_market(market):
                continue

            spread_a = to_float(record.get("spread_a", "0"))
            spread_b = to_float(record.get("spread_b", "0"))
            total = to_float(record.get("total", "0"))

            if not valid_spread(spread_a) or not valid_spread(spread_b):
                continue

            proj_spread = project_spread(spread_b, market)
            proj_total = project_total(total, market)

            edge_spread = abs(proj_spread - spread_b) if spread_b != 0 else 0.0
            edge_total = abs(proj_total - total) if total != 0 else 0.0

            if total > 0 and edge_total > edge_spread:
                if proj_total > total:
                    best_bet = f"Over {total}"
                else:
                    best_bet = f"Under {total}"
                bet_type = "TOTAL"
                edge = edge_total
            else:
                if proj_spread < spread_b:
                    best_bet = f"{team_a} {spread_a:+}"
                else:
                    best_bet = f"{team_b} {spread_b:+}"
                bet_type = "SPREAD"
                edge = edge_spread

            tier = classify_tier(edge)

            rows.append(
                {
                    "game": f"{team_a} vs {team_b}",
                    "league": league,
                    "market": market,
                    "bet_type": bet_type,
                    "best_bet": best_bet,
                    "score": round(edge, 2),
                    "tier": tier,
                    "win_prob": round(min(75, 50 + edge * 3), 1),
                    "signals": [market, bet_type],
                }
            )

    rows = sorted(rows, key=lambda x: x["score"], reverse=True)

    with open(OUT_PATH, "w", encoding="utf-8") as out_file:
        json.dump(rows, out_file, indent=2)

    print(f"Wrote {len(rows)} picks")


if __name__ == "__main__":
    run()
