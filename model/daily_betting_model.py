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
    """
    Placeholder projection, but tuned to be less hostile to short dogs/favorites.
    """
    factor = 0.72
    if market == "1H":
        factor = 0.62
    elif market in {"1Q", "F5", "1P"}:
        factor = 0.56
    return spread * factor


def project_total(total: float, market: str) -> float:
    """
    Keep total projection conservative so totals only win when clearly stronger.
    """
    factor = 0.985
    if market == "1H":
        factor = 0.97
    elif market in {"1Q", "F5", "1P"}:
        factor = 0.95
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

    spread_a = to_num(row.get("spread_a", ""))
    spread_b = to_num(row.get("spread_b", ""))
    total = to_num(row.get("total", ""))

    if abs(spread_a) > 30 or abs(spread_b) > 30:
        return False
    if total and total < 20:
        return False

    return True


def side_bias_bonus(spread_b: float, market: str) -> float:
    """
    Boost short-number spread sides, especially the exact range where sharp cards
    often live: +1.5 to +4.5 or -1.5 to -4.5.
    """
    abs_spread = abs(spread_b)

    if market == "FULL":
        if 1.5 <= abs_spread <= 4.5:
            return 1.6
        if 4.5 < abs_spread <= 7.0:
            return 0.8
    elif market == "1H":
        if 0.5 <= abs_spread <= 3.5:
            return 1.2
    elif market in {"1Q", "F5", "1P"}:
        if 0.5 <= abs_spread <= 2.5:
            return 1.0

    return 0.0


def total_penalty(total: float, market: str) -> float:
    """
    Make totals earn their way onto the card.
    """
    penalty = 0.6
    if market in {"1Q", "F5", "1P"}:
        penalty = 0.9
    if market == "1H":
        penalty = 0.7

    if total >= 230:
        penalty += 0.3
    if 0 < total <= 120:
        penalty += 0.2

    return penalty


def classify_tier(score: float, market: str, bet_type: str, spread: float) -> tuple[str, list[str]]:
    notes: list[str] = []
    adjusted = score

    if bet_type == "SPREAD":
        if market == "FULL" and abs(spread) >= 10:
            adjusted -= 1.5
            notes.append("BLOWOUT_RISK")
        if market == "FULL" and abs(spread) in {8.5, 9.5, 10.5}:
            adjusted -= 1.0
            notes.append("HOOK_RISK")

    if adjusted >= 4.8:
        return "MAX_ELITE", notes
    if adjusted >= 3.6:
        return "ELITE", notes
    if adjusted >= 2.2:
        return "STRONG", notes
    return "PASS", notes


def choose_pick(team_a: str, team_b: str, spread_a: float, spread_b: float, total: float, market: str):
    """
    Favor short spread sides over modest total edges.
    """
    proj_s = project_spread(spread_b, market) if spread_b else 0.0
    proj_t = project_total(total, market) if total else 0.0

    edge_spread = abs(proj_s - spread_b) if spread_b else 0.0
    edge_total = abs(proj_t - total) if total else 0.0

    spread_score = edge_spread + side_bias_bonus(spread_b, market)
    total_score = edge_total - total_penalty(total, market) if total else 0.0

    # Strong preference for short spreads
    if spread_b and abs(spread_b) <= 4.5 and spread_score >= total_score - 0.25:
        if proj_s < spread_b:
            return f"{team_a} {spread_a:+}", spread_score, "SPREAD", proj_s, proj_t
        return f"{team_b} {spread_b:+}", spread_score, "SPREAD", proj_s, proj_t

    # Totals only if clearly superior
    if total and total_score >= spread_score + 0.9:
        if proj_t > total:
            return f"Over {total}", total_score, "TOTAL", proj_s, proj_t
        return f"Under {total}", total_score, "TOTAL", proj_s, proj_t

    # Default to side if spread exists
    if spread_b:
        if proj_s < spread_b:
            return f"{team_a} {spread_a:+}", spread_score, "SPREAD", proj_s, proj_t
        return f"{team_b} {spread_b:+}", spread_score, "SPREAD", proj_s, proj_t

    # Fallback
    if total:
        if proj_t > total:
            return f"Over {total}", total_score, "TOTAL", proj_s, proj_t
        return f"Under {total}", total_score, "TOTAL", proj_s, proj_t

    return "", 0.0, "", proj_s, proj_t


def build_signals(market: str, bet_type: str, spread: float, proj_s: float, proj_t: float, total: float) -> list[str]:
    signals = [market, bet_type]

    if bet_type == "SPREAD" and market == "FULL" and abs(spread) <= 4.5:
        signals.insert(0, "SHORT_SPREAD_EDGE")
    if bet_type == "SPREAD" and market == "FULL" and abs(spread) >= 10:
        signals.insert(0, "BLOWOUT_RISK")
    if bet_type == "SPREAD" and market == "FULL" and abs(spread) in {8.5, 9.5, 10.5}:
        signals.insert(0, "HOOK_RISK")
    if bet_type == "TOTAL" and total > 0 and abs(proj_t - total) >= 4:
        signals.insert(0, "TOTAL_EDGE")

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
            league = row.get("sport", "").strip().upper()

            spread_a = to_num(row.get("spread_a", ""))
            spread_b = to_num(row.get("spread_b", ""))
            total = to_num(row.get("total", ""))

            best_bet, score, bet_type, proj_s, proj_t = choose_pick(
                team_a, team_b, spread_a, spread_b, total, market
            )
            if not best_bet:
                continue

            tier, tier_notes = classify_tier(score, market, bet_type, spread_b)
            signals = build_signals(market, bet_type, spread_b, proj_s, proj_t, total)
            signals = tier_notes + [s for s in signals if s not in tier_notes]

            rows.append(
                {
                    "game": f"{team_a} vs {team_b}",
                    "league": league,
                    "market": market,
                    "bet_type": bet_type,
                    "best_bet": best_bet,
                    "score": round(score, 2),
                    "tier": tier,
                    "win_prob": round(min(75.0, 50.0 + score * 3.2), 1),
                    "signals": signals,
                    "proj_spread": round(proj_s, 2),
                    "proj_total": round(proj_t, 2),
                    "market_spread": spread_b,
                    "market_total": total,
                }
            )

    # Keep stronger actionable rows
    rows = [r for r in rows if r["tier"] in {"MAX_ELITE", "ELITE", "STRONG"}]
    rows = sorted(rows, key=lambda x: x["score"], reverse=True)

    with open(OUT_PATH, "w", encoding="utf-8") as outfile:
        json.dump(rows, outfile, indent=2)

    print(f"Wrote {len(rows)} picks")
    for row in rows[:25]:
        print(
            f"{row['game']} | {row['market']} | {row['bet_type']} | "
            f"{row['best_bet']} | {row['tier']} | score={row['score']}"
        )


if __name__ == "__main__":
    run()
