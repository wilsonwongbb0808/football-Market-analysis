import json
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seal_and_optimize_odds_model import ROOT, FEATURES_PATH, RESULTS_PATH, drop_pct, pnl_for_pick

OUT_PATH = ROOT / "data" / "football_analyzer_market_edges.md"


def picks_for(row, market):
    if market == "1x2":
        specs = [("1", "h2h_home"), ("X", "h2h_draw"), ("2", "h2h_away")]
    elif market == "asian":
        specs = [("home", "ah_home"), ("away", "ah_away")]
    else:
        specs = [("over", "over"), ("under", "under")]
    out = []
    for side, key in specs:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        if op is None or cl is None:
            continue
        out.append({
            "market": market,
            "side": side,
            "odds": cl,
            "drop": drop_pct(op, cl),
        })
    return out


def run_rule(features, results, market, cfg):
    bets = []
    for row in features:
        rows = []
        for pick in picks_for(row, market):
            if pick["drop"] < cfg["min_drop"]:
                continue
            if not (cfg["min_odds"] <= pick["odds"] <= cfg["max_odds"]):
                continue
            if cfg["side"] != "all" and pick["side"] != cfg["side"]:
                continue
            score = pick["drop"] * cfg["drop_weight"] + pick["odds"] * cfg["odds_weight"]
            rows.append({**pick, "score": score})
        if rows:
            rows.sort(key=lambda x: (x["score"], x["drop"]), reverse=True)
            pick = rows[0]
            bets.append({**pick, "match": row["match"], "pnl": pnl_for_pick(row, results[row["match_id"]], pick)})
    if not bets:
        return None
    profit = sum(b["pnl"] for b in bets)
    return {
        "market": market,
        "config": cfg,
        "bets": len(bets),
        "wins": sum(1 for b in bets if b["pnl"] > 0),
        "pushes": sum(1 for b in bets if b["pnl"] == 0),
        "losses": sum(1 for b in bets if b["pnl"] < 0),
        "profit": round(profit, 3),
        "roi": round(profit / len(bets), 4),
    }


def main():
    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    results = {r["match_id"]: r for r in json.loads(RESULTS_PATH.read_text(encoding="utf-8"))}
    all_rows = []
    side_options = {
        "1x2": ["all", "1", "X", "2"],
        "asian": ["all", "home", "away"],
        "total": ["all", "over", "under"],
    }
    for market in ["total", "asian", "1x2"]:
        for min_drop, min_odds, max_odds, drop_weight, odds_weight, side in product(
            [-0.2, -0.05, 0, 0.015, 0.03, 0.05, 0.08],
            [1.45, 1.6, 1.75, 1.85, 2.0],
            [2.15, 2.4, 2.8, 3.5, 6.0],
            [0, 50, 100],
            [-1, 0, 1],
            side_options[market],
        ):
            if min_odds >= max_odds:
                continue
            cfg = {
                "min_drop": min_drop,
                "min_odds": min_odds,
                "max_odds": max_odds,
                "drop_weight": drop_weight,
                "odds_weight": odds_weight,
                "side": side,
            }
            row = run_rule(features, results, market, cfg)
            if row and row["bets"] >= 10 and row["profit"] > 0:
                all_rows.append(row)
    all_rows.sort(key=lambda x: (x["roi"], x["profit"], x["bets"]), reverse=True)
    lines = [
        "# Market Specific Edge Search",
        "",
        "| Rank | Market | Side | Bets | W-P-L | Profit | ROI | Min Drop | Odds |",
        "|---:|---|---|---:|---|---:|---:|---:|---|",
    ]
    for i, row in enumerate(all_rows[:30], 1):
        cfg = row["config"]
        lines.append(
            f"| {i} | {row['market']} | {cfg['side']} | {row['bets']} | {row['wins']}-{row['pushes']}-{row['losses']} | "
            f"{row['profit']:.2f} | {row['roi']:.2%} | {cfg['min_drop']:.1%} | {cfg['min_odds']}-{cfg['max_odds']} |"
        )
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
