from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_OUTPUT = DATA_DIR / "parsed_lines.csv"


SPORT_ALIASES = {
    "NBA": "NBA",
    "NCAAB": "NCAAB",
    "NCAA BASKETBALL": "NCAAB",
    "COLLEGE BASKETBALL": "NCAAB",
    "MLB": "MLB",
    "BASEBALL": "MLB",
    "NFL": "NFL",
    "NCAAF": "NCAAF",
    "NCAA FOOTBALL": "NCAAF",
    "COLLEGE FOOTBALL": "NCAAF",
    "NHL": "NHL",
    "HOCKEY": "NHL",
}

MARKET_PATTERNS = [
    (re.compile(r"\b1ST\s*HALF\b", re.I), "1H"),
    (re.compile(r"\b2ND\s*HALF\b", re.I), "2H"),
    (re.compile(r"\b1ST\s*Q(TR|UARTER)?\b", re.I), "1Q"),
    (re.compile(r"\b2ND\s*Q(TR|UARTER)?\b", re.I), "2Q"),
    (re.compile(r"\b3RD\s*Q(TR|UARTER)?\b", re.I), "3Q"),
    (re.compile(r"\b4TH\s*Q(TR|UARTER)?\b", re.I), "4Q"),
    (re.compile(r"\b1ST\s*PERIOD\b", re.I), "1P"),
    (re.compile(r"\b2ND\s*PERIOD\b", re.I), "2P"),
    (re.compile(r"\b3RD\s*PERIOD\b", re.I), "3P"),
    (re.compile(r"\b1ST\s*5\b", re.I), "F5"),
    (re.compile(r"\bFIRST\s*5\b", re.I), "F5"),
    (re.compile(r"\b1ST\s*FIVE\b", re.I), "F5"),
    (re.compile(r"\bTEAM\s*TOTALS?\b", re.I), "TEAM_TOTAL"),
    (re.compile(r"\bGAME\s*LINES?\b", re.I), "FULL"),
    (re.compile(r"\bFULL\s*GAME\b", re.I), "FULL"),
]

HEADER_SKIP_PATTERNS = [
    re.compile(r"^\s*rotation\s*$", re.I),
    re.compile(r"^\s*money\s*line\s*$", re.I),
    re.compile(r"^\s*moneyline\s*$", re.I),
    re.compile(r"^\s*spread\s*$", re.I),
    re.compile(r"^\s*total\s*$", re.I),
    re.compile(r"^\s*teams?\s*$", re.I),
    re.compile(r"^\s*odds?\s*$", re.I),
    re.compile(r"^\s*live .* odds .* movement\s*$", re.I),
    re.compile(r"^\s*page \d+\s*$", re.I),
]

TEAM_ONLY_RE = re.compile(r"^[A-Za-z0-9 .&'()/:-]+$")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
MONEYLINE_RE = re.compile(r"[-+]\d{2,4}")
SPREAD_WITH_ODDS_RE = re.compile(
    r"(?P<spread>[-+]\d+(?:\.\d+)?)\s*(?:\((?P<odds1>[-+]\d{2,4})\)|(?P<odds2>[-+]\d{2,4}))?"
)
TOTAL_RE = re.compile(
    r"\b(?P<ou>O/U|OVER/UNDER|OVER|UNDER)?\s*(?P<total>\d+(?:\.\d+)?)\b",
    re.I,
)


@dataclass
class ParsedLine:
    source_file: str
    sport: str
    market: str
    matchup: str
    team_a: str
    team_b: str
    spread_a: str = ""
    spread_b: str = ""
    spread_odds_a: str = ""
    spread_odds_b: str = ""
    total: str = ""
    over_odds: str = ""
    under_odds: str = ""
    moneyline_a: str = ""
    moneyline_b: str = ""
    notes: str = ""


CSV_FIELDS = list(ParsedLine.__dataclass_fields__.keys())


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_sport(text: str) -> Optional[str]:
    cleaned = normalize_whitespace(text).upper()
    for key, value in SPORT_ALIASES.items():
        if key in cleaned:
            return value
    return None


def detect_market(text: str) -> str:
    for pattern, market in MARKET_PATTERNS:
        if pattern.search(text):
            return market
    return "FULL"


def should_skip_line(line: str) -> bool:
    s = normalize_whitespace(line)
    if not s:
        return True
    for pattern in HEADER_SKIP_PATTERNS:
        if pattern.match(s):
            return True
    return False


def looks_like_team_line(line: str) -> bool:
    s = normalize_whitespace(line)
    if not s:
        return False
    if len(s) < 2:
        return False
    if re.search(r"\b(OVER|UNDER|TOTAL|MONEYLINE|SPREAD)\b", s, re.I):
        return False
    return bool(TEAM_ONLY_RE.match(s))


def extract_moneylines(text: str) -> list[str]:
    return MONEYLINE_RE.findall(text)


def extract_totals(text: str) -> list[str]:
    return [m.group("total") for m in TOTAL_RE.finditer(text)]


def extract_spreads(text: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for m in SPREAD_WITH_ODDS_RE.finditer(text):
        spread = m.group("spread")
        odds = m.group("odds1") or m.group("odds2") or ""
        results.append((spread, odds))
    return results


def infer_market_from_sport_and_team_count(sport: str, market: str) -> str:
    if market == "FULL":
        return "FULL"
    return market


def parse_pdf_text(text: str, source_name: str = "uploaded.pdf") -> list[ParsedLine]:
    lines = [normalize_whitespace(x) for x in text.splitlines()]
    lines = [x for x in lines if x]

    parsed: list[ParsedLine] = []

    current_sport = ""
    current_market = "FULL"

    i = 0
    while i < len(lines):
        line = lines[i]

        maybe_sport = normalize_sport(line)
        if maybe_sport:
            current_sport = maybe_sport
            current_market = detect_market(line)
            i += 1
            continue

        detected_market = detect_market(line)
        if detected_market != "FULL" or "GAME LINES" in line.upper() or "FULL GAME" in line.upper():
            current_market = detected_market
            i += 1
            continue

        if should_skip_line(line):
            i += 1
            continue

        # Pattern 1: team on one line, odds on next line
        if i + 3 < len(lines) and looks_like_team_line(lines[i]) and looks_like_team_line(lines[i + 2]):
            team_a = lines[i]
            odds_a = lines[i + 1]
            team_b = lines[i + 2]
            odds_b = lines[i + 3]

            spreads_a = extract_spreads(odds_a)
            spreads_b = extract_spreads(odds_b)
            totals_a = extract_totals(odds_a)
            totals_b = extract_totals(odds_b)
            mls_a = extract_moneylines(odds_a)
            mls_b = extract_moneylines(odds_b)

            total = totals_a[0] if totals_a else (totals_b[0] if totals_b else "")

            spread_a, spread_odds_a = spreads_a[0] if spreads_a else ("", "")
            spread_b, spread_odds_b = spreads_b[0] if spreads_b else ("", "")

            ml_a = mls_a[0] if mls_a else ""
            ml_b = mls_b[0] if mls_b else ""

            parsed.append(
                ParsedLine(
                    source_file=source_name,
                    sport=current_sport or "UNKNOWN",
                    market=infer_market_from_sport_and_team_count(current_sport or "UNKNOWN", current_market),
                    matchup=f"{team_a} vs {team_b}",
                    team_a=team_a,
                    team_b=team_b,
                    spread_a=spread_a,
                    spread_b=spread_b,
                    spread_odds_a=spread_odds_a,
                    spread_odds_b=spread_odds_b,
                    total=total,
                    moneyline_a=ml_a,
                    moneyline_b=ml_b,
                    notes="parsed_team_block",
                )
            )
            i += 4
            continue

        # Pattern 2: single-line matchup with separators
        if " vs " in line.lower() or " v " in line.lower():
            matchup_line = line
            team_split = re.split(r"\bvs\b|\bv\b", matchup_line, flags=re.I)
            if len(team_split) == 2:
                team_a = normalize_whitespace(team_split[0])
                team_b = normalize_whitespace(team_split[1])

                next_chunk = " ".join(lines[i + 1 : min(i + 4, len(lines))])
                spreads = extract_spreads(next_chunk)
                totals = extract_totals(next_chunk)
                moneylines = extract_moneylines(next_chunk)

                spread_a, spread_odds_a = spreads[0] if len(spreads) > 0 else ("", "")
                spread_b, spread_odds_b = spreads[1] if len(spreads) > 1 else ("", "")
                total = totals[0] if totals else ""
                ml_a = moneylines[0] if len(moneylines) > 0 else ""
                ml_b = moneylines[1] if len(moneylines) > 1 else ""

                parsed.append(
                    ParsedLine(
                        source_file=source_name,
                        sport=current_sport or "UNKNOWN",
                        market=current_market,
                        matchup=f"{team_a} vs {team_b}",
                        team_a=team_a,
                        team_b=team_b,
                        spread_a=spread_a,
                        spread_b=spread_b,
                        spread_odds_a=spread_odds_a,
                        spread_odds_b=spread_odds_b,
                        total=total,
                        moneyline_a=ml_a,
                        moneyline_b=ml_b,
                        notes="parsed_matchup_line",
                    )
                )
                i += 1
                continue

        i += 1

    return dedupe_rows(parsed)


def dedupe_rows(rows: Iterable[ParsedLine]) -> list[ParsedLine]:
    seen = set()
    output: list[ParsedLine] = []
    for row in rows:
        key = (
            row.sport,
            row.market,
            row.matchup,
            row.spread_a,
            row.spread_b,
            row.total,
            row.moneyline_a,
            row.moneyline_b,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def write_csv(rows: Iterable[ParsedLine], out_path: Path = DEFAULT_OUTPUT) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Uses pypdf if available.
    Install with:
        pip install pypdf
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF extraction. Add 'pypdf' to requirements.txt."
        ) from exc

    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def parse_pdf_file(pdf_path: Path, out_path: Path = DEFAULT_OUTPUT) -> list[ParsedLine]:
    text = extract_text_from_pdf(pdf_path)
    rows = parse_pdf_text(text, source_name=pdf_path.name)
    write_csv(rows, out_path)
    return rows


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Parse sportsbook PDF into structured betting lines CSV.")
    parser.add_argument("pdf_path", help="Path to sportsbook PDF")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to output CSV (default: data/parsed_lines.csv)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    out_path = Path(args.output)

    rows = parse_pdf_file(pdf_path, out_path)
    print(f"Parsed {len(rows)} rows into {out_path}")


if __name__ == "__main__":
    main()
