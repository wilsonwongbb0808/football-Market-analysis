import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ODDSHARVESTER = ROOT / "tools" / "python312" / "Scripts" / "oddsharvester.exe"
THREE_MARKETS = ROOT / "data" / "world_cup_2022_three_markets.csv"
LINKS_PATH = ROOT / "data" / "oddsportal_worldcup2022_links.json"
OUT_DIR = ROOT / "data" / "oddsportal_opening_worldcup2022"
MERGED_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_merged.json"
CSV_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_backtest.csv"
SUMMARY_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_backtest_summary.json"


def norm(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def row_slug(row):
    date = row_date(row).replace("-", "")
    return f"{date}_{norm(row['match'])}"


def row_date(row):
    if row.get("date_utc"):
        return row["date_utc"][:10]
    match = re.search(r"-(20\d{2}-\d{2}-\d{2})/", row.get("url", ""))
    if match:
        return match.group(1)
    return "00000000"


def asian_token(value):
    n = float(str(value).strip())
    sign = "+" if n > 0 else "-" if n < 0 else ""
    abs_text = f"{abs(n):.2f}".rstrip("0").rstrip(".").replace(".", "_")
    return f"asian_handicap_{sign}{abs_text}" if sign else "asian_handicap_0"


def total_token(value):
    n = float(str(value).strip())
    line = f"{abs(n):.2f}".rstrip("0").rstrip(".").replace(".", "_")
    return f"over_under_{line}"


def read_three_markets():
    with THREE_MARKETS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_links():
    if not LINKS_PATH.exists():
        raise SystemExit(f"Missing {LINKS_PATH}. Run collect_oddsportal_worldcup_links.py first.")
    data = json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    by_key = {}
    for item in data:
        if item.get("home") and item.get("away"):
            by_key[f"{norm(item['match'])}-{item.get('date_utc', '')}"] = item["url"]
            by_key[f"{norm(item['home'])}-{norm(item['away'])}"] = item["url"]
    return by_key


def result_value(row, market, side):
    key = f"{market}_market"
    if market == "1x2":
        order = ["1", "X", "2"]
    elif market.startswith("over_under_"):
        order = ["odds_over", "odds_under"]
    elif market.startswith("asian_handicap_"):
        order = ["team1_handicap", "team2_handicap"]
    else:
        order = []

    for item in row.get(key, []):
        if str(item.get("bookmaker_name", "")).lower() != "bet365":
            continue
        current = item.get(side)
        if current in ("", None):
            return None, None
        histories = item.get("odds_history_data") or []
        idx = order.index(side) if side in order else None
        opening = ""
        if idx is not None and idx < len(histories):
            opening = histories[idx].get("opening_odds", {}).get("odds", "")
        return float(opening or current), float(current)
    return None, None


def settle_1x2(home_score, away_score, side, odds):
    outcome = "1" if home_score > away_score else "2" if away_score > home_score else "X"
    return odds - 1 if outcome == side else -1


def settle_asian(home_score, away_score, line, side, odds):
    diff = home_score - away_score
    adjusted = diff + line if side == "home" else -diff - line
    if adjusted > 0:
        return odds - 1
    if adjusted == 0:
        return 0
    return -1


def settle_total(home_score, away_score, line, side, odds):
    goals = home_score + away_score
    if side == "over":
        if goals > line:
            return odds - 1
        if goals == line:
            return 0
        return -1
    if goals < line:
        return odds - 1
    if goals == line:
        return 0
    return -1


def source_scores(src, item):
    if src.get("home_score") != "" and src.get("away_score") != "":
        return int(src["home_score"]), int(src["away_score"])
    item_home = norm(item.get("home_team", ""))
    item_away = norm(item.get("away_team", ""))
    src_home = norm(src["home"])
    src_away = norm(src["away"])
    if src_home == item_home and src_away == item_away:
        return int(item["home_score"]), int(item["away_score"])
    if src_home == item_away and src_away == item_home:
        return int(item["away_score"]), int(item["home_score"])
    raise ValueError(f"Cannot map score for {src['match']}")


def run_one(row, url, limit_seconds):
    out = OUT_DIR / f"{row_slug(row)}.json"
    if out.exists():
        print(f"exists {row['match']} -> {out.name}", flush=True)
        return out

    markets = f"1x2,{total_token(row['total_line'])},{asian_token(row['ah_home_line'])}"
    cmd = [
        str(ODDSHARVESTER),
        "historic",
        "-s", "football",
        "--season", "2022",
        "--match-link", url,
        "-m", markets,
        "--target-bookmaker", "bet365",
        "--odds-history",
        "-f", "json",
        "-o", str(out),
        "--headless",
        "--request-delay", "0.2",
        "-c", "1",
    ]
    print(f"fetch {row['match']} markets={markets}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=limit_seconds)
    if proc.returncode != 0:
        combined = proc.stdout + "\n" + proc.stderr
        match = re.search(r"fragment mismatch detected: requested=([A-Za-z0-9]+) page=([A-Za-z0-9]+)", combined)
        if match and match.group(2) and match.group(1) != match.group(2):
            fixed_url = re.sub(r"#[-A-Za-z0-9]+$", f"#{match.group(2)}", url)
            fixed_cmd = cmd[:]
            fixed_cmd[fixed_cmd.index("--match-link") + 1] = fixed_url
            print(f"retry fixed-hash {row['match']} -> {match.group(2)}", flush=True)
            proc = subprocess.run(fixed_cmd, cwd=ROOT, text=True, capture_output=True, timeout=limit_seconds)
            if proc.returncode == 0:
                return out
            combined = proc.stdout + "\n" + proc.stderr
        fail = out.with_suffix(".error.txt")
        fail.write_text(combined, encoding="utf-8")
        print(f"failed {row['match']} -> {fail.name}", flush=True)
        return None
    return out


def collection_status(source_rows):
    saved = []
    missing = []
    failed = []
    for row in source_rows:
        base = OUT_DIR / f"{row_slug(row)}.json"
        err = OUT_DIR / f"{row_slug(row)}.error.txt"
        if base.exists():
            saved.append(row["match"])
        else:
            missing.append(row["match"])
        if err.exists():
            failed.append(row["match"])
    return saved, missing, failed


def merge_and_backtest(source_rows):
    rows = []
    by_slug = {row_slug(r): r for r in source_rows}
    for file in OUT_DIR.glob("*.json"):
        src = by_slug.get(file.stem)
        if not src:
            continue
        data = json.loads(file.read_text(encoding="utf-8"))
        if not data:
            continue
        item = data[0]
        hs, aas = source_scores(src, item)
        total_market = total_token(src["total_line"])
        asian_market = asian_token(src["ah_home_line"])
        h_open, h_close = result_value(item, "1x2", "1")
        x_open, x_close = result_value(item, "1x2", "X")
        a_open, a_close = result_value(item, "1x2", "2")
        over_open, over_close = result_value(item, total_market, "odds_over")
        under_open, under_close = result_value(item, total_market, "odds_under")
        ah_home_open, ah_home_close = result_value(item, asian_market, "team1_handicap")
        ah_away_open, ah_away_close = result_value(item, asian_market, "team2_handicap")
        rows.append({
            "match": src["match"],
            "home": src["home"],
            "away": src["away"],
            "home_score": hs,
            "away_score": aas,
            "h2h_home_open": h_open,
            "h2h_draw_open": x_open,
            "h2h_away_open": a_open,
            "h2h_home_close": h_close,
            "h2h_draw_close": x_close,
            "h2h_away_close": a_close,
            "ah_line": float(src["ah_home_line"]),
            "ah_home_open": ah_home_open,
            "ah_away_open": ah_away_open,
            "ah_home_close": ah_home_close,
            "ah_away_close": ah_away_close,
            "total_line": float(src["total_line"]),
            "over_open": over_open,
            "under_open": under_open,
            "over_close": over_close,
            "under_close": under_close,
        })
    MERGED_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    flat = []
    for r in rows:
        candidates = []
        for side, key in [("1", "h2h_home"), ("X", "h2h_draw"), ("2", "h2h_away")]:
            op, cl = r.get(f"{key}_open"), r.get(f"{key}_close")
            if op and cl and cl < op:
                candidates.append(("1x2_" + side, settle_1x2(r["home_score"], r["away_score"], side, cl)))
        if r.get("ah_home_open") and r.get("ah_home_close") and r["ah_home_close"] < r["ah_home_open"]:
            candidates.append(("ah_home", settle_asian(r["home_score"], r["away_score"], r["ah_line"], "home", r["ah_home_close"])))
        if r.get("ah_away_open") and r.get("ah_away_close") and r["ah_away_close"] < r["ah_away_open"]:
            candidates.append(("ah_away", settle_asian(r["home_score"], r["away_score"], r["ah_line"], "away", r["ah_away_close"])))
        if r.get("over_open") and r.get("over_close") and r["over_close"] < r["over_open"]:
            candidates.append(("over", settle_total(r["home_score"], r["away_score"], r["total_line"], "over", r["over_close"])))
        if r.get("under_open") and r.get("under_close") and r["under_close"] < r["under_open"]:
            candidates.append(("under", settle_total(r["home_score"], r["away_score"], r["total_line"], "under", r["under_close"])))
        for name, pnl in candidates:
            flat.append({"match": r["match"], "pick": name, "pnl": pnl})

    if flat:
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=flat[0].keys())
            writer.writeheader()
            writer.writerows(flat)
    profit = sum(x["pnl"] for x in flat)
    summary = {
        "matches_with_opening": len(rows),
        "bets_when_closing_improved": len(flat),
        "wins": sum(1 for x in flat if x["pnl"] > 0),
        "pushes": sum(1 for x in flat if x["pnl"] == 0),
        "losses": sum(1 for x in flat if x["pnl"] < 0),
        "profit_units": round(profit, 3),
        "roi": round(profit / len(flat), 4) if flat else 0,
        "note": "Uses bet365 opening and closing odds from OddsPortal history.",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("max_matches", nargs="?", type=int, default=0, help="0 means collect every linked match")
    parser.add_argument("--backtest", action="store_true", help="merge and backtest only after all raw files are saved")
    parser.add_argument("--timeout", type=int, default=240, help="seconds per match")
    parser.add_argument("--start-row", type=int, default=1, help="1-based first source row")
    parser.add_argument("--end-row", type=int, default=0, help="1-based last source row, 0 means the final row")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_rows = read_three_markets()
    end_row = args.end_row or len(source_rows)
    rows_to_fetch = source_rows[args.start_row - 1:end_row]
    links = load_links()
    completed_this_run = 0
    for row in rows_to_fetch:
        key = f"{norm(row['match'])}-{row.get('date_utc', '')}"
        url = links.get(key) or links.get(f"{norm(row['home'])}-{norm(row['away'])}")
        if not url:
            print(f"missing link {row['match']}", flush=True)
            continue
        try:
            if run_one(row, url, args.timeout):
                completed_this_run += 1
        except subprocess.TimeoutExpired:
            print(f"timeout {row['match']}", flush=True)
        time.sleep(0.5)
        if args.max_matches and completed_this_run >= args.max_matches:
            break

    saved, missing, failed = collection_status(source_rows)
    print(f"status saved={len(saved)}/{len(source_rows)} missing={len(missing)} failed_logs={len(failed)}", flush=True)
    if missing:
        print("missing first:", " | ".join(missing[:12]), flush=True)
    if failed:
        print("failed logs first:", " | ".join(failed[:12]), flush=True)
    if args.backtest:
        if len(saved) < len(source_rows):
            raise SystemExit("Raw odds are not fully saved yet. Backtest skipped.")
        merge_and_backtest(source_rows)


if __name__ == "__main__":
    main()
