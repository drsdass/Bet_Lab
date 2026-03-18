from __future__ import annotations

import csv
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

PARSED_CSV = DATA_DIR / "parsed_lines.csv"
RANKED_JSON = DATA_DIR / "ranked_card.json"


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def infer_proj_spread(spread_a: float, spread_b: float, market: str, sport: str) -> float:
    """
    Placeholder projection logic until the full pro engine is wired back in.
    Slightly discounts market spreads so we can still rank edges.
    """
    base = spread_b if spread_b != 0 else -spread_a
    factor = 0.65

    if market in {"1H", "2H"}:
        factor = 0.58
    elif market in {"1Q", "2Q", "3Q", "4Q", "1P", "2P", "3P", "F5"}:
        factor = 0.52

    if sport in {"NCAAB", "NCAAF"}:
        factor -= 0.03

    return round(base * factor, 2)


def infer_proj_total(total: float, market: str, sport: str) -> float:
    """
    Placeholder total projection logic.
    """
    if total == 0:
        return 0.0

    factor = 0.985
    if market in {"1H", "2H"}:
        factor = 0.97
    elif market in {"1Q", "2Q", "3Q", "4Q", "1P", "2P", "3P", "F5"}:
        factor = 0.95

    if sport in {"NCAAB", "NCAAF"}:
        factor -= 0.01

    return round(total * factor, 2)


def classify_tier(edge: float, market: str, spread_b: float) -> tuple[str, list[str]]:
    notes: list[str] = []

    abs_spread = abs(spread_b)

    if market == "FULL" and abs_spread >= 10:
        notes.append("BLOWOUT_RISK")
    if market == "FULL" and abs_spread in {8.5, 9.5, 10.5}:
        notes.append("HOOK_RISK")

    adjusted_edge = edge
    if "BLOWOUT_RISK" in notes:
        adjusted_edge -= 1.5
    if "HOOK_RISK" in notes:
        adjusted_edge -= 1.0

    if adjusted_edge >= 5.5:
        return "MAX_ELITE", notes
    if adjusted_edge >= 4.0:
        return "ELITE", notes
    if adjusted_edge >= 2.5:
        return "STRONG", notes
    return "PASS", notes


def choose_best_bet(
    team_a: str,
    team_b: str,
    spread_a: float,
    spread_b: float,
    total: float,
    proj_spread: float,
    proj_total: float,
) -> tuple[str, float]:
    spread_edge = abs(proj_spread - spread_b) if spread_b != 0 else 0.0
    total_edge = abs(proj_total - total) if total != 0 else 0.0

    if total > 0 and total_edge > spread_edge:
        if proj_total > total:
            return f"Over {total}", total_edge
        return f"Under {total}", total_edge

    if spread_b != 0:
        if proj_spread < spread_b:
            return f"{team_a} {spread_a:+}", spread_edge
        return f"{team_b} {spread_b:+}", spread_edge

    return f"Over {total}", total_edge


def load_games_from_csv() -> list[dict]:
    games: list[dict] = []

    if not PARSED_CSV.exists():
        print(f"Parsed CSV not found: {PARSED_CSV}")
        return games

    with PARSED_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            sport = str(row.get("sport", "")).strip().upper()
            market = str(row.get("market", "FULL")).strip().upper()
            team_a = str(row.get("team_a", "")).strip()
            team_b = str(row.get("team_b", "")).strip()

            if not team_a or not team_b:
                continue

            spread_a = to_float(row.get("spread_a", ""))
            spread_b = to_float(row.get("spread_b", ""))
            total = to_float(row.get("total", ""))

            proj_spread = infer_proj_spread(spread_a, spread_b, market, sport)
            proj_total = infer_proj_total(total, market, sport)

            best_bet, edge = choose_best_bet(
                team_a=team_a,
                team_b=team_b,
                spread_a=spread_a,
                spread_b=spread_b,
                total=total,
                proj_spread=proj_spread,
                proj_total=proj_total,
            )

            tier, notes = classify_tier(edge=edge, market=market, spread_b=spread_b)

            games.append(
                {
                    "date": "auto",
                    "league": sport,
                    "market": market,
                    "game": f"{team_a} vs {team_b}",
                    "best_bet": best_bet,
                    "tier": tier,
                    "score": round(edge, 2),
                    "edge_pct": round(edge, 2),
                    "win_prob": round(min(75.0, 50.0 + edge * 3.0), 1),
                    "signals": notes + [market],
                }
            )

    return sorted(games, key=lambda x: x["score"], reverse=True)


def run() -> list[dict]:
    results = load_games_from_csv()

    with RANKED_JSON.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    rows = run()
    print(f"Wrote {len(rows)} picks to {RANKED_JSON}")
    for row in rows[:20]:
        print(
            f"{row['game']} | {row['market']} | {row['best_bet']} | "
            f"{row['tier']} | score={row['score']}"
        )
