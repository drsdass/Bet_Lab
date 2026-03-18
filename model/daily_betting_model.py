from __future__ import annotations

import csv
import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "parsed_lines.csv"
OUT_PATH = DATA_DIR / "ranked_card.json"


def f(x):
    try:
        return float(x)
    except:
        return 0


def project_spread(spread, market):
    factor = 0.65
    if market == "1H":
        factor = 0.58
    if market == "1Q":
        factor = 0.52
    return spread * factor


def project_total(total, market):
    factor = 0.98
    if market == "1H":
        factor = 0.96
    if market == "1Q":
        factor = 0.94
    return total * factor


def tier(edge):
    if edge > 5.5:
        return "MAX_ELITE"
    if edge > 4:
        return "ELITE"
    if edge > 2.5:
        return "STRONG"
    return "PASS"


def run():
    rows = []

    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)

        for r in reader:
            t1 = r["team_a"]
            t2 = r["team_b"]
            market = r["market"]

            spread = f(r["spread_b"])
            total = f(r["total"])

            proj_s = project_spread(spread, market)
            proj_t = project_total(total, market)

            edge_spread = abs(proj_s - spread)
            edge_total = abs(proj_t - total)

            if edge_total > edge_spread:
                bet = f"Under {total}"
                edge = edge_total
                btype = "TOTAL"
            else:
                bet = f"{t2} {spread}"
                edge = edge_spread
                btype = "SPREAD"

            rows.append({
                "game": f"{t1} vs {t2}",
                "market": market,
                "bet_type": btype,
                "best_bet": bet,
                "score": round(edge,2),
                "tier": tier(edge),
                "win_prob": min(75, 50 + edge*3),
                "signals": [market, btype]
            })

    rows = sorted(rows, key=lambda x: x["score"], reverse=True)

    with open(OUT_PATH, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} picks")


if __name__ == "__main__":
    run()
