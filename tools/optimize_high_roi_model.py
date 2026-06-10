import json
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seal_and_optimize_odds_model import (
    ROOT,
    FEATURES_PATH,
    RESULTS_PATH,
    drop_pct,
    pnl_for_pick,
    market_summary,
)

OUT_PATH = ROOT / "data" / "football_analyzer_high_roi_model.json"
REPORT_PATH = ROOT / "data" / "football_analyzer_high_roi_model.md"


def shape_score(odds, cfg):
    if odds < cfg["hard_min_odds"]:
        return -99
    if odds < 1.75:
        return -cfg["low_odds_penalty"]
    if odds <= 2.25:
        return cfg["sweet_spot_bonus"]
    if odds <= 2.8:
        return cfg["medium_odds_bonus"]
    if odds <= 3.8:
        return 0
    return -cfg["high_odds_penalty"]


def candidate_rows(row, cfg):
    out = []
    for side, key in [("1", "h2h_home"), ("X", "h2h_draw"), ("2", "h2h_away")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["euro_bonus"] + shape_score(cl, cfg)
        if cl < cfg["min_euro_odds"]:
            score -= cfg["euro_low_penalty"]
        out.append({"market": "1x2", "side": side, "odds": cl, "drop": d, "score": score})
    for side, key in [("home", "ah_home"), ("away", "ah_away")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["asian_bonus"] + shape_score(cl, cfg)
        out.append({"market": "asian", "side": side, "odds": cl, "drop": d, "score": score})
    for side, key in [("over", "over"), ("under", "under")]:
        op, cl = row.get(f"{key}_open"), row.get(f"{key}_close")
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["total_bonus"] + shape_score(cl, cfg)
        out.append({"market": "total", "side": side, "odds": cl, "drop": d, "score": score})
    return [
        pick for pick in out
        if pick["drop"] >= cfg["min_drop"]
        and pick["score"] >= cfg["min_score"]
        and cfg["min_pick_odds"] <= pick["odds"] <= cfg["max_pick_odds"]
    ]


def evaluate(features, results, cfg):
    bets = []
    for row in features:
        picks = [p for p in candidate_rows(row, cfg) if p["market"] in cfg["markets"]]
        picks.sort(key=lambda p: (
            p["score"],
            {"total": 2, "asian": 1, "1x2": 0}[p["market"]],
            p["drop"],
        ), reverse=True)
        for pick in picks[:cfg["max_picks_per_match"]]:
            result = results[row["match_id"]]
            bets.append({**pick, "match": row["match"], "match_id": row["match_id"], "pnl": pnl_for_pick(row, result, pick)})
    if not bets:
        return None
    profit = sum(b["pnl"] for b in bets)
    return {
        "config": cfg,
        "bets": len(bets),
        "wins": sum(1 for b in bets if b["pnl"] > 0),
        "pushes": sum(1 for b in bets if b["pnl"] == 0),
        "losses": sum(1 for b in bets if b["pnl"] < 0),
        "profit_units": round(profit, 3),
        "roi": round(profit / len(bets), 4),
        "by_market": market_summary(bets),
        "bets_detail": bets,
    }


def main():
    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    results = {r["match_id"]: r for r in json.loads(RESULTS_PATH.read_text(encoding="utf-8"))}
    configs = []
    for drop_weight, min_drop, min_score, total_bonus, asian_bonus, euro_bonus, max_picks, min_odds, max_odds, markets in product(
        [75, 110, 150],
        [0, 0.015, 0.025, 0.04, 0.06],
        [2.5, 4.0, 5.5, 7.0, 9.0],
        [1.5, 2.2, 3.0, 3.8],
        [-0.5, 0.5, 1.4],
        [-2.0, -1.2, -0.5, 0.0],
        [1],
        [1.75, 1.8],
        [2.4, 3.4, 5.5],
        [["total"], ["1x2"], ["asian"], ["total", "1x2"], ["total", "asian", "1x2"]],
    ):
        configs.append({
            "drop_weight": drop_weight,
            "min_drop": min_drop,
            "min_score": min_score,
            "total_bonus": total_bonus,
            "asian_bonus": asian_bonus,
            "euro_bonus": euro_bonus,
            "max_picks_per_match": max_picks,
            "hard_min_odds": 1.55,
            "min_pick_odds": min_odds,
            "max_pick_odds": max_odds,
            "min_euro_odds": 1.8,
            "euro_low_penalty": 6,
            "low_odds_penalty": 5,
            "sweet_spot_bonus": 2,
            "medium_odds_bonus": 0.8,
            "high_odds_penalty": 1.5,
            "markets": markets,
        })
    rows = [r for r in (evaluate(features, results, cfg) for cfg in configs) if r and 12 <= r["bets"] <= 55 and r["profit_units"] > 0]
    rows.sort(key=lambda r: (r["roi"], r["profit_units"], r["bets"]), reverse=True)
    best = rows[0]
    OUT_PATH.write_text(json.dumps({"best_model": best, "top_models": rows[:50]}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# High ROI Model Search",
        "",
        "Goal: fewer but cleaner recommendations. Results are still from one sealed tournament, so this is an aggressive mode.",
        "",
        f"Best ROI: {best['roi']:.2%}",
        f"Bets: {best['bets']}",
        f"W-P-L: {best['wins']}-{best['pushes']}-{best['losses']}",
        f"Profit: {best['profit_units']} units",
        f"Config: `{json.dumps(best['config'], ensure_ascii=False)}`",
        "",
        "## Market Split",
        "",
        "| Market | Bets | W-P-L | Profit | ROI |",
        "|---|---:|---|---:|---:|",
    ]
    for market, summary in best["by_market"].items():
        lines.append(f"| {market} | {summary['bets']} | {summary['wins']}-{summary['pushes']}-{summary['losses']} | {summary['profit_units']:.2f} | {summary['roi']:.2%} |")
    lines.extend([
        "",
        "## Top 15",
        "",
        "| Rank | Bets | W-P-L | Profit | ROI | Min Drop | Min Score | Odds Range | Total Bonus | Asian Bonus |",
        "|---:|---:|---|---:|---:|---:|---:|---|---:|---:|",
    ])
    for i, row in enumerate(rows[:15], 1):
        cfg = row["config"]
        lines.append(
            f"| {i} | {row['bets']} | {row['wins']}-{row['pushes']}-{row['losses']} | {row['profit_units']:.2f} | "
            f"{row['roi']:.2%} | {cfg['min_drop']:.1%} | {cfg['min_score']} | {cfg['min_pick_odds']}-{cfg['max_pick_odds']} | "
            f"{cfg['total_bonus']} | {cfg['asian_bonus']} |"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
