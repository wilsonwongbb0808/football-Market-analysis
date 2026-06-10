import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THREE_MARKETS = ROOT / "data" / "world_cup_2022_three_markets.csv"
OUT_DIR = ROOT / "data" / "oddsportal_opening_worldcup2022"
STATUS_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_collection_status.json"


def norm(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def row_date(row):
    if row.get("date_utc"):
        return row["date_utc"][:10]
    match = re.search(r"-(20\d{2}-\d{2}-\d{2})/", row.get("url", ""))
    if match:
        return match.group(1)
    return "00000000"


def row_slug(row):
    return f"{row_date(row).replace('-', '')}_{norm(row['match'])}"


def asian_token(value):
    n = float(str(value).strip())
    sign = "+" if n > 0 else "-" if n < 0 else ""
    abs_text = f"{abs(n):.2f}".rstrip("0").rstrip(".").replace(".", "_")
    return f"asian_handicap_{sign}{abs_text}" if sign else "asian_handicap_0"


def total_token(value):
    n = float(str(value).strip())
    line = f"{abs(n):.2f}".rstrip("0").rstrip(".").replace(".", "_")
    return f"over_under_{line}"


def read_rows():
    with THREE_MARKETS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    rows = read_rows()
    status = {
        "total_matches": len(rows),
        "saved_files": 0,
        "complete_three_markets": 0,
        "missing_files": [],
        "missing_markets": [],
        "fallback_markets": [],
    }
    for row in rows:
        slug = row_slug(row)
        file = OUT_DIR / f"{slug}.json"
        if not file.exists():
            status["missing_files"].append(row["match"])
            continue
        status["saved_files"] += 1
        data = json.loads(file.read_text(encoding="utf-8"))
        item = data[0] if data else {}
        expected = ["1x2_market", f"{total_token(row['total_line'])}_market", f"{asian_token(row['ah_home_line'])}_market"]
        missing = [key for key in expected if key not in item]
        if missing and row["match"] == "Costa Rica - Germany" and "asian_handicap_+2_market" in item:
            status["fallback_markets"].append({
                "match": row["match"],
                "expected": "asian_handicap_+2_25_market",
                "saved": "asian_handicap_+2_market",
                "reason": "OddsHarvester football market registry does not support +2.25 Asian handicap.",
            })
            missing = [key for key in missing if key != "asian_handicap_+2_25_market"]
        if missing:
            status["missing_markets"].append({"match": row["match"], "missing": missing})
        else:
            status["complete_three_markets"] += 1
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
