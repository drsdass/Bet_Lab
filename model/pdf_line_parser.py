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


def normalize(line: str) -> str:
    return line.replace("½", ".5").strip()


def is_junk(line: str) -> bool:
    for p in JUNK_PATTERNS:
        if re.match(p, line.upper()):
            return True
    return False


def detect_section(line: str):
    for key, val in SECTION_HEADERS.items():
        if key in line.upper():
            return val
    return None


def clean_team(line: str) -> str:
    line = re.sub(r"C\s+MORE BETS", "", line)
    return line.strip()


def parse_odds(line: str):
    m = SPREAD_TOTAL_RE.search(line)
    if not m:
        return {}
    return {
        "spread": m.group("spread") or "",
        "spread_odds": m.group("spread_odds") or "",
        "total": m.group("total") or "",
        "total_side": m.group("ou") or "",
        "total_odds": m.group("total_odds") or "",
        "moneyline": m.group("moneyline") or "",
    }


def parse_section(sport, market, lines, source):
    teams = []
    odds = []

    for line in lines:
        if is_junk(line):
            continue
        if ODDS_LINE_RE.match(line):
            odds.append(line)
        else:
            if len(line) > 3:
                teams.append(clean_team(line))

    rows = []
    n = min(len(teams)//2, len(odds)//2)

    for i in range(n):
        t1 = teams[i*2]
        t2 = teams[i*2+1]

        o1 = parse_odds(odds[i*2])
        o2 = parse_odds(odds[i*2+1])

        # skip broken spreads
        try:
            if abs(float(o1.get("spread", 0))) > 30:
                continue
        except:
            pass

        rows.append(
            ParsedLine(
                source_file=source,
                sport=sport,
                market=market,
                matchup=f"{t1} vs {t2}",
                team_a=t1,
                team_b=t2,
                spread_a=o1.get("spread",""),
                spread_b=o2.get("spread",""),
                total=o1.get("total",""),
                moneyline_a=o1.get("moneyline",""),
                moneyline_b=o2.get("moneyline",""),
            )
        )

    return rows


def parse_pdf_text(text, source):
    lines = [normalize(x) for x in text.splitlines()]

    sections = []
    current = []
    sport, market = None, None

    for line in lines:
        sec = detect_section(line)
        if sec:
            if current:
                sections.append((sport, market, current))
            sport, market = sec
            current = []
            continue
        current.append(line)

    rows = []
    for s,m,l in sections:
        if m in {"FULL","1H","1Q","F5","1P"}:
            rows += parse_section(s,m,l,source)

    return rows


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))


def main():
    import argparse
    from pypdf import PdfReader

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    args = parser.parse_args()

    reader = PdfReader(args.pdf)
    text = "\n".join([p.extract_text() or "" for p in reader.pages])

    rows = parse_pdf_text(text, args.pdf)
    write_csv(rows, DEFAULT_OUTPUT)

    print(f"Parsed {len(rows)} rows")
    

if __name__ == "__main__":
    main()
