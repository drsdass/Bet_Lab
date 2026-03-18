from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path

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
    "NCAAB - GAME LINES": ("NCAAB", "FULL"),
    "NCAAB - 1H": ("NCAAB", "1H"),
    "MLB - GAME LINES": ("MLB", "FULL"),
    "MLB - 1ST 5": ("MLB", "F5"),
    "NFL - GAME LINES": ("NFL", "FULL"),
    "NFL - 1H": ("NFL", "1H"),
    "NFL - QUARTERS FIRST QUARTER LINES": ("NFL", "1Q"),
    "NCAAF - GAME LINES": ("NCAAF", "FULL"),
    "NCAAF - 1H": ("NCAAF", "1H"),
    "NHL - GAME LINES": ("NHL", "FULL"),
    "NHL - 1ST PERIOD": ("NHL", "1P"),
}

JUNK_PATTERNS = [
    r"^PLEASE SELECT YOUR BETS",
    r"^USER ID:",
    r"^BALANCE:",
    r"^AVAILABLE:",
    r"^AT RISK:",
    r"^FREE PLAY:",
    r"^LINES FROM:",
    r"^\d+/\d+/\d+",
    r"^DATE TEAM SPREAD TOTAL M LINE",
    r"^SPORTSBOOK$",
    r"^MENU$",
    r"^CONTINUE$",
    r"^https?://",
    r"^\d+$",
    r"^\d{1,2}:\d{2}\s*PM$",
]

ODDS_LINE_RE = re.compile(r"^[+-]")
SPREAD_TOTAL_RE = re.compile(
    r"""
    (?P<spread>[+-]\d+(?:\.\d+)?)
    (?P<spread_odds>[+-]\d{3})?
    (?:\s+(?P<ou>[ou])(?P<total>\d+(?:\.\d+)?)(?P<total_odds>[+-]\d{3}))?
    (?:\s+(?P<moneyline>[+-]\d{3,4}))?
    """,
    re.VERBOSE | re.I,
)

TEAM_CLEAN_PREFIX_RE = re.compile(
    r"""
    ^
    (?:
        MAR\s+\d+\s+\d+\s* |          # Mar 18 535
        \d{1,2}:\d{2}\s*PM\s+\d+\s* | # 7:40 PM 538
        \d+\s+                        # 538
    )+
    """,
    re.I | re.VERBOSE,
)

MARKET_PREFIX_RE = re.compile(r"^(1H|2H|1Q|2Q|3Q|4Q|1P|2P|3P|F5)\s+", re.I)


def normalize(line: str) -> str:
    return (
        line.replace("\xa0", " ")
        .replace("½", ".5")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )


def is_junk(line: str) -> bool:
    upper = line.upper().strip()
    if not upper:
        return True
    for p in JUNK_PATTERNS:
        if re.match(p, upper):
            return True
    return False


def detect_section(line: str):
    upper = line.upper()
    for key, val in SECTION_HEADERS.items():
        if key in upper:
            return val
    return None


def clean_team(line: str) -> str:
    s = normalize(line)
    s = re.sub(r"\bC\s+MORE BETS\b", "", s, flags=re.I)
    s = re.sub(r"\bMORE BETS\b", "", s, flags=re.I)
    s = re.sub(r"https?://\S+", "", s, flags=re.I)
    s = TEAM_CLEAN_PREFIX_RE.sub("", s)
    s = MARKET_PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


def looks_like_team(line: str) -> bool:
    s = clean_team(line)
    if not s:
        return False

    upper = s.upper()
    banned_substrings = [
        "GAME LINES",
        "QUARTERS",
        "FIRST QUARTER",
        "SECOND QUARTER",
        "THIRD QUARTER",
        "FOURTH QUARTER",
        "DATE TEAM SPREAD TOTAL",
        "PLEASE SELECT YOUR BETS",
        "USER ID",
        "LINES FROM",
        "CONTINUE",
        "HTTP",
        "WT=0",
    ]
    if any(b in upper for b in banned_substrings):
        return False

    if ODDS_LINE_RE.match(s):
        return False

    # Must contain letters and not be just metadata
    if not re.search(r"[A-Z]", upper):
        return False

    # Avoid bare time fragments
    if re.fullmatch(r"\d{1,2}:\d{2}\s*PM", upper):
        return False

    return True


def parse_odds(line: str) -> dict:
    m = SPREAD_TOTAL_RE.search(normalize(line))
    if not m:
        return {}
    return {
        "spread": m.group("spread") or "",
        "spread_odds": m.group("spread_odds") or "",
        "total": m.group("total") or "",
        "total_side": (m.group("ou") or "").lower(),
        "total_odds": m.group("total_odds") or "",
        "moneyline": m.group("moneyline") or "",
    }


def split_sections(lines: list[str]):
    sections = []
    current = []
    sport = market = None

    for raw in lines:
        line = normalize(raw)
        sec = detect_section(line)
        if sec:
            if sport and current:
                sections.append((sport, market, current))
            sport, market = sec
            current = []
            continue
        current.append(line)

    if sport and current:
        sections.append((sport, market, current))

    return sections


def valid_spread(value: str) -> bool:
    if not value:
        return True
    try:
        return abs(float(value)) <= 30
    except Exception:
        return False


def valid_matchup(team_a: str, team_b: str) -> bool:
    if not team_a or not team_b:
        return False
    if team_a == team_b:
        return False

    bad = ["USER ID", "CONTINUE", "HTTP", "WT=0", "LINES FROM", "PLEASE SELECT"]
    upper_a = team_a.upper()
    upper_b = team_b.upper()
    if any(b in upper_a for b in bad) or any(b in upper_b for b in bad):
        return False

    # Must look like real team names
    if len(team_a) < 3 or len(team_b) < 3:
        return False

    return True


def parse_section(sport: str, market: str, lines: list[str], source: str):
    teams = []
    odds = []

    for line in lines:
        line = normalize(line)
        if is_junk(line):
            continue
        if ODDS_LINE_RE.match(line):
            odds.append(line)
        elif looks_like_team(line):
            team = clean_team(line)
            if team:
                teams.append(team)

    rows = []
    n = min(len(teams) // 2, len(odds) // 2)

    for i in range(n):
        t1 = teams[i * 2]
        t2 = teams[i * 2 + 1]

        if not valid_matchup(t1, t2):
            continue

        o1 = parse_odds(odds[i * 2])
        o2 = parse_odds(odds[i * 2 + 1])

        spread_a = o1.get("spread", "")
        spread_b = o2.get("spread", "")

        if not valid_spread(spread_a) or not valid_spread(spread_b):
            continue

        total = o1.get("total", "") or o2.get("total", "")
        over_odds = o1.get("total_odds", "") if o1.get("total_side") == "o" else ""
        under_odds = o2.get("total_odds", "") if o2.get("total_side") == "u" else ""

        rows.append(
            ParsedLine(
                source_file=source,
                sport=sport,
                market=market,
                matchup=f"{t1} vs {t2}",
                team_a=t1,
                team_b=t2,
                spread_a=spread_a,
                spread_b=spread_b,
                spread_odds_a=o1.get("spread_odds", ""),
                spread_odds_b=o2.get("spread_odds", ""),
                total=total,
                over_odds=over_odds,
                under_odds=under_odds,
                moneyline_a=o1.get("moneyline", ""),
                moneyline_b=o2.get("moneyline", ""),
                notes=f"paired_from_section_{market}",
            )
        )

    return rows


def dedupe_rows(rows):
    seen = set()
    out = []
    for row in rows:
        key = (
            row.sport,
            row.market,
            row.matchup,
            row.spread_a,
            row.spread_b,
            row.total,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def extract_text_from_pdf(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_pdf_text(text: str, source: str):
    lines = [normalize(x) for x in text.splitlines()]
    sections = split_sections(lines)

    rows = []
    for sport, market, sec_lines in sections:
        if market not in {"FULL", "1H", "1Q", "F5", "1P"}:
            continue
        rows.extend(parse_section(sport, market, sec_lines, source))

    return dedupe_rows(rows)


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))


def main():
    import argparse
    from pypdf import PdfReader  # noqa: F401

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    text = extract_text_from_pdf(pdf_path)
    rows = parse_pdf_text(text, pdf_path.name)
    write_csv(rows, DEFAULT_OUTPUT)
    print(f"Parsed {len(rows)} rows")


if __name__ == "__main__":
    main()
