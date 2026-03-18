from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_OUTPUT = DATA_DIR / "parsed_lines.csv"


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


SECTION_HEADERS = {
    "NBA - GAME LINES": ("NBA", "FULL"),
    "NBA - 1H": ("NBA", "1H"),
    "NBA - QUARTERS FIRST QUARTER LINES": ("NBA", "1Q"),
    "NBA - QUARTERS SECOND QUARTER LINES": ("NBA", "2Q"),
    "NBA - QUARTERS THIRD QUARTER LINES": ("NBA", "3Q"),
    "NBA - QUARTERS FOURTH QUARTER LINES": ("NBA", "4Q"),
    "NCAAB - GAME LINES": ("NCAAB", "FULL"),
    "NCAAB - 1H": ("NCAAB", "1H"),
    "NCAAB - 2H": ("NCAAB", "2H"),
    "NCAAB - FIRST HALF LINES": ("NCAAB", "1H"),
    "MLB - GAME LINES": ("MLB", "FULL"),
    "MLB - 1ST 5": ("MLB", "F5"),
    "NFL - GAME LINES": ("NFL", "FULL"),
    "NFL - 1H": ("NFL", "1H"),
    "NFL - QUARTERS FIRST QUARTER LINES": ("NFL", "1Q"),
    "NCAAF - GAME LINES": ("NCAAF", "FULL"),
    "NCAAF - 1H": ("NCAAF", "1H"),
    "NHL - GAME LINES": ("NHL", "FULL"),
    "NHL - 1ST PERIOD": ("NHL", "1P"),
    "NHL - 2ND PERIOD": ("NHL", "2P"),
    "NHL - 3RD PERIOD": ("NHL", "3P"),
}

JUNK_PATTERNS = [
    r"^PLEASE SELECT YOUR BETS$",
    r"^USER ID:",
    r"^BALANCE:",
    r"^AVAILABLE:",
    r"^AT RISK:",
    r"^FREE PLAY:",
    r"^https?://",
    r"^\d+/\d+/\d+,",
    r"^DATE TEAM SPREAD TOTAL M LINE$",
    r"^LINES FROM:",
    r"^SPORTSBOOK$",
    r"^MENU$",
    r"^\d+/\d+$",
]

TEAM_LINE_RE = re.compile(
    r"^(?:MAR \d+\s+)?(?:\d{1,2}:\d{2}\s*PM\s+)?\d+\s+(?:(1H|2H|1Q|2Q|3Q|4Q|1P|2P|3P|F5)\s+)?(.+?)$",
    re.I,
)

ODDS_LINE_RE = re.compile(r"^[+-]")

SPREAD_TOTAL_RE = re.compile(
    r"""
    (?P<spread>[+-]\d+(?:[½\.]\d+)?)
    (?P<spread_odds>[+-]\d{3})?
    (?:\s+(?P<ou>[ou])(?P<total>\d+(?:[½\.]\d+)?)(?P<total_odds>[+-]\d{3}))?
    (?:\s+(?P<moneyline>[+-]\d{3,4}))?
    """,
    re.VERBOSE | re.I,
)


def normalize_line(line: str) -> str:
    return (
        line.replace("\xa0", " ")
        .replace("½", ".5")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )


def is_junk(line: str) -> bool:
    if not line:
        return True
    upper = line.upper().strip()
    for pat in JUNK_PATTERNS:
        if re.match(pat, upper):
            return True
    return False


def clean_team_name(raw: str) -> str:
    s = normalize_line(raw)
    s = re.sub(r"\bC\s+MORE BETS\b", "", s, flags=re.I)
    s = re.sub(r"\bMORE BETS\b", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_team_line(line: str) -> str | None:
    line = normalize_line(line)
    m = TEAM_LINE_RE.match(line)
    if not m:
        return None
    team = clean_team_name(m.group(2))
    if not team:
        return None
    banned = [
        "NBA - GAME LINES",
        "NBA - 1H",
        "NBA - QUARTERS",
        "NCAAB - GAME LINES",
        "LINES FROM:",
        "DATE TEAM SPREAD TOTAL M LINE",
    ]
    upper = team.upper()
    if any(b in upper for b in banned):
        return None
    return team


def parse_odds_line(line: str) -> dict:
    line = normalize_line(line)
    result = {
        "spread": "",
        "spread_odds": "",
        "total": "",
        "total_side": "",
        "total_odds": "",
        "moneyline": "",
    }

    m = SPREAD_TOTAL_RE.search(line)
    if not m:
        return result

    result["spread"] = m.group("spread") or ""
    result["spread_odds"] = m.group("spread_odds") or ""
    result["total"] = m.group("total") or ""
    result["total_side"] = (m.group("ou") or "").lower()
    result["total_odds"] = m.group("total_odds") or ""
    result["moneyline"] = m.group("moneyline") or ""
    return result


def detect_section(line: str) -> tuple[str, str] | None:
    upper = normalize_line(line).upper()
    for key, value in SECTION_HEADERS.items():
        if key in upper:
            return value
    return None


def split_sections(lines: list[str]) -> list[tuple[str, str, list[str]]]:
    sections: list[tuple[str, str, list[str]]] = []
    current_sport = ""
    current_market = ""
    buffer: list[str] = []

    for raw in lines:
        line = normalize_line(raw)
        if is_junk(line):
            continue

        section = detect_section(line)
        if section:
            if current_sport and buffer:
                sections.append((current_sport, current_market, buffer))
            current_sport, current_market = section
            buffer = []
            continue

        if current_sport:
            buffer.append(line)

    if current_sport and buffer:
        sections.append((current_sport, current_market, buffer))

    return sections


def parse_section(sport: str, market: str, lines: list[str], source_name: str) -> list[ParsedLine]:
    team_lines: list[str] = []
    odds_lines: list[str] = []

    for line in lines:
        if is_junk(line):
            continue
        if ODDS_LINE_RE.match(line.strip()):
            odds_lines.append(line)
        else:
            team = parse_team_line(line)
            if team:
                team_lines.append(team)

    rows: list[ParsedLine] = []
    game_count = min(len(team_lines) // 2, len(odds_lines) // 2)

    for i in range(game_count):
        team_a = team_lines[i * 2]
        team_b = team_lines[i * 2 + 1]

        odds_a = parse_odds_line(odds_lines[i * 2])
        odds_b = parse_odds_line(odds_lines[i * 2 + 1])

        spread_a = odds_a["spread"]
        spread_b = odds_b["spread"]

        # Reject obviously broken spreads that are really moneylines
        def valid_spread(x: str) -> bool:
            if not x:
                return True
            try:
                value = float(x)
                return abs(value) <= 30
            except Exception:
                return False

        if not valid_spread(spread_a) or not valid_spread(spread_b):
            continue

        total = odds_a["total"] or odds_b["total"]
        over_odds = odds_a["total_odds"] if odds_a["total_side"] == "o" else ""
        under_odds = odds_b["total_odds"] if odds_b["total_side"] == "u" else ""

        rows.append(
            ParsedLine(
                source_file=source_name,
                sport=sport,
                market=market,
                matchup=f"{team_a} vs {team_b}",
                team_a=team_a,
                team_b=team_b,
                spread_a=spread_a,
                spread_b=spread_b,
                spread_odds_a=odds_a["spread_odds"],
                spread_odds_b=odds_b["spread_odds"],
                total=total,
                over_odds=over_odds,
                under_odds=under_odds,
                moneyline_a=odds_a["moneyline"],
                moneyline_b=odds_b["moneyline"],
                notes=f"paired_from_section_{market}",
            )
        )

    return rows


def dedupe_rows(rows: list[ParsedLine]) -> list[ParsedLine]:
    seen = set()
    out: list[ParsedLine] = []
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
        out.append(row)
    return out


def extract_text_from_pdf(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_pdf_text(text: str, source_name: str = "uploaded.pdf") -> list[ParsedLine]:
    lines = [normalize_line(x) for x in text.splitlines()]
    sections = split_sections(lines)

    all_rows: list[ParsedLine] = []
    for sport, market, sec_lines in sections:
        # Keep only supported markets for now
        if market not in {"FULL", "1H", "1Q", "F5", "1P"}:
            continue
        all_rows.extend(parse_section(sport, market, sec_lines, source_name))

    return dedupe_rows(all_rows)


def write_csv(rows: list[ParsedLine], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def parse_pdf_file(pdf_path: Path, out_path: Path = DEFAULT_OUTPUT) -> list[ParsedLine]:
    text = extract_text_from_pdf(pdf_path)
    rows = parse_pdf_text(text, source_name=pdf_path.name)
    write_csv(rows, out_path)
    return rows


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Parse sportsbook PDF into structured lines CSV.")
    parser.add_argument("pdf_path", help="Path to sportsbook PDF")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    out_path = Path(args.output)

    rows = parse_pdf_file(pdf_path, out_path)
    print(f"Parsed {len(rows)} rows into {out_path}")


if __name__ == "__main__":
    main()
