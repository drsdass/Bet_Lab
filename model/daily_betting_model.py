from __future__ import annotations

import csv
import json
from pathlib import Path

from model.pro_betting_model import Game, run_model

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

PARSED_CSV = DATA_DIR / "parsed_lines.csv"
RANKED_JSON = DATA_DIR / "ranked_card.json"


def load_games_from_csv():
    games = []

    with PARSED_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                spread = float(row["spread_b"]) if row["spread_b"] else 0
                total = float(row["total"]) if row["total"] else 0
            except:
                continue

            games.append(
                Game(
                    game=row["matchup"],
                    spread=spread,
                    total=total,
                    proj_spread=spread * 0.6,  # placeholder projection
                    proj_total=total * 0.98,
                    pace=100,
                    off_eff_a=110,
                    def_eff_a=108,
                    off_eff_b=109,
                    def_eff_b=109,
                    league=row["sport"],
                )
            )

    return games


def run():
    games = load_games_from_csv()

    if not games:
        print("No games loaded from CSV")
        return []

    results = run_model(games)

    output = []

    for r in results:
        output.append(
            {
                "date": "auto",
                "league": "",
                "game": r["game"],
                "best_bet": r["pick"],
                "tier": r["tier"],
                "score": r["score"],
                "edge_pct": r["edge"],
                "win_prob": round(min(75, 50 + r["score"] * 2), 1),
                "signals": r["notes"],
            }
        )

    with RANKED_JSON.open("w") as f:
        json.dump(output, f, indent=2)

    return output


if __name__ == "__main__":
    results = run()
    for r in results:
        print(r)        
