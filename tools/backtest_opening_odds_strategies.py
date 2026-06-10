import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGED_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_merged.json"
OUT_PATH = ROOT / "data" / "oddsportal_worldcup2022_strategy_backtest.json"
REPORT_PATH = ROOT / "data" / "oddsportal_worldcup2022_strategy_backtest.md"


def settle_1x2(row, side, odds):
    outcome = "1" if row["home_score"] > row["away_score"] else "2" if row["away_score"] > row["home_score"] else "X"
    return odds - 1 if outcome == side else -1


def settle_asian(row, side, odds):
    diff = row["home_score"] - row["away_score"]
    line = row["ah_line"]
    adjusted = diff + line if side == "home" else -diff - line
    if adjusted > 0:
        return odds - 1
    if adjusted == 0:
        return 0
    return -1


def settle_total(row, side, odds):
    goals = row["home_score"] + row["away_score"]
    line = row["total_line"]
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


def drop_pct(open_odds, close_odds):
    if not open_odds or not close_odds:
        return None
    return (open_odds - close_odds) / open_odds


def all_candidates(row):
    candidates = []
    for side, key in [("1", "h2h_home"), ("X", "h2h_draw"), ("2", "h2h_away")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        d = drop_pct(op, cl)
        if d is not None:
            candidates.append({
                "market": "1x2",
                "side": side,
                "open": op,
                "close": cl,
                "drop": d,
                "pnl": settle_1x2(row, side, cl),
                "match": row["match"],
            })
    for side, key in [("home", "ah_home"), ("away", "ah_away")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        d = drop_pct(op, cl)
        if d is not None:
            candidates.append({
                "market": "asian",
                "side": side,
                "open": op,
                "close": cl,
                "drop": d,
                "pnl": settle_asian(row, side, cl),
                "match": row["match"],
            })
    for side, key in [("over", "over"), ("under", "under")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        d = drop_pct(op, cl)
        if d is not None:
            candidates.append({
                "market": "total",
                "side": side,
                "open": op,
                "close": cl,
                "drop": d,
                "pnl": settle_total(row, side, cl),
                "match": row["match"],
            })
    return candidates


def evaluate(rows, rule):
    bets = []
    for row in rows:
        candidates = []
        for c in all_candidates(row):
            if c["drop"] < rule["min_drop"]:
                continue
            if c["close"] < rule["min_odds"] or c["close"] > rule["max_odds"]:
                continue
            if c["market"] not in rule["markets"]:
                continue
            score = c["drop"] * 100
            if c["market"] == "1x2":
                score *= 0.9
            if 1.75 <= c["close"] <= 2.35:
                score *= 1.12
            if c["close"] < 1.6:
                score *= 0.65
            c = dict(c)
            c["score"] = score
            candidates.append(c)
        if rule["one_per_match"] and candidates:
            bets.append(max(candidates, key=lambda x: x["score"]))
        else:
            bets.extend(candidates)
    if not bets:
        return None
    profit = sum(b["pnl"] for b in bets)
    return {
        "rule": rule,
        "bets": len(bets),
        "wins": sum(1 for b in bets if b["pnl"] > 0),
        "pushes": sum(1 for b in bets if b["pnl"] == 0),
        "losses": sum(1 for b in bets if b["pnl"] < 0),
        "profit_units": round(profit, 3),
        "roi": round(profit / len(bets), 4),
        "sample_bets": bets[:8],
    }


def main():
    rows = json.loads(MERGED_PATH.read_text(encoding="utf-8"))
    rules = []
    market_sets = [
        ["1x2"],
        ["asian"],
        ["total"],
        ["1x2", "asian", "total"],
        ["asian", "total"],
    ]
    for min_drop, min_odds, max_odds, one_per_match, markets in product(
        [0.0, 0.02, 0.04, 0.06, 0.08],
        [1.45, 1.6, 1.7, 1.8],
        [2.4, 2.8, 3.5, 6.0],
        [True, False],
        market_sets,
    ):
        if min_odds >= max_odds:
            continue
        rules.append({
            "min_drop": min_drop,
            "min_odds": min_odds,
            "max_odds": max_odds,
            "one_per_match": one_per_match,
            "markets": markets,
        })
    results = [r for r in (evaluate(rows, rule) for rule in rules) if r]
    results.sort(key=lambda r: (r["roi"], r["profit_units"], r["bets"]), reverse=True)
    filtered = [r for r in results if r["bets"] >= 12]
    best = filtered[:20]
    OUT_PATH.write_text(json.dumps({"top_rules": best, "all_results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# OddsPortal 2022 World Cup Strategy Backtest",
        "",
        "Rules use bet365 opening-to-closing movement. Profit is flat 1 unit per bet.",
        "",
        "| Rank | Markets | Min Drop | Odds Range | One Per Match | Bets | W-P-L | Profit | ROI |",
        "|---:|---|---:|---|---|---:|---|---:|---:|",
    ]
    for i, r in enumerate(best[:12], 1):
        rule = r["rule"]
        lines.append(
            f"| {i} | {','.join(rule['markets'])} | {rule['min_drop']:.0%} | "
            f"{rule['min_odds']}-{rule['max_odds']} | {rule['one_per_match']} | "
            f"{r['bets']} | {r['wins']}-{r['pushes']}-{r['losses']} | "
            f"{r['profit_units']:.2f} | {r['roi']:.2%} |"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
