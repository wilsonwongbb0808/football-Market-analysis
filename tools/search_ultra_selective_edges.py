import json
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seal_and_optimize_odds_model import ROOT, FEATURES_PATH, RESULTS_PATH, drop_pct, pnl_for_pick
from search_market_specific_edges import picks_for

OUT_PATH = ROOT / "data" / "football_analyzer_ultra_selective_edges.md"


def run_rule(features, results, market, cfg):
    bets = []
    for row in features:
        candidates = []
        for pick in picks_for(row, market):
            if cfg["side"] != "all" and pick["side"] != cfg["side"]:
                continue
            if pick["drop"] < cfg["min_drop"] or pick["drop"] > cfg["max_drop"]:
                continue
            if not (cfg["min_odds"] <= pick["odds"] <= cfg["max_odds"]):
                continue
            score = pick["drop"] * cfg["drop_weight"] + pick["odds"] * cfg["odds_weight"]
            candidates.append({**pick, "score": score})
        if candidates:
            candidates.sort(key=lambda x: (x["score"], x["drop"]), reverse=True)
            pick = candidates[0]
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
    side_options = {
        "1x2": ["all", "1", "X", "2"],
        "asian": ["all", "home", "away"],
        "total": ["all", "over", "under"],
    }
    rows = []
    for market in ["total", "asian", "1x2"]:
        for side, min_drop, max_drop, min_odds, max_odds, drop_weight, odds_weight in product(
            side_options[market],
            [-0.2, -0.05, 0, 0.015, 0.03, 0.05, 0.08, 0.12],
            [0.04, 0.08, 0.15, 0.35, 1.0],
            [1.45, 1.6, 1.75, 1.85, 2.0, 2.2],
            [2.05, 2.25, 2.5, 2.8, 3.5, 6.0],
            [0, 50, 100, 150],
            [-1, 0, 1],
        ):
            if min_drop > max_drop or min_odds >= max_odds:
                continue
            cfg = {
                "side": side,
                "min_drop": min_drop,
                "max_drop": max_drop,
                "min_odds": min_odds,
                "max_odds": max_odds,
                "drop_weight": drop_weight,
                "odds_weight": odds_weight,
            }
            row = run_rule(features, results, market, cfg)
            if row and 6 <= row["bets"] <= 15 and row["profit"] > 0:
                rows.append(row)
    rows.sort(key=lambda r: (r["roi"], r["profit"], r["bets"]), reverse=True)
    lines = [
        "# Ultra Selective Edge Search",
        "",
        "This deliberately allows fewer bets. Higher ROI here means more selectivity and more overfit risk.",
        "",
        "| Rank | Market | Side | Bets | W-P-L | Profit | ROI | Drop Range | Odds Range |",
        "|---:|---|---|---:|---|---:|---:|---|---|",
    ]
    for i, row in enumerate(rows[:40], 1):
        cfg = row["config"]
        lines.append(
            f"| {i} | {row['market']} | {cfg['side']} | {row['bets']} | {row['wins']}-{row['pushes']}-{row['losses']} | "
            f"{row['profit']:.2f} | {row['roi']:.2%} | {cfg['min_drop']:.1%}..{cfg['max_drop']:.1%} | "
            f"{cfg['min_odds']}..{cfg['max_odds']} |"
        )
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
