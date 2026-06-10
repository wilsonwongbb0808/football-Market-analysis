import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seal_and_optimize_odds_model import (
    ROOT,
    FEATURES_PATH,
    RESULTS_PATH,
    candidates as broad_candidates,
    pnl_for_pick,
)
from search_market_specific_edges import picks_for

HIGH_ROI_PATH = ROOT / "data" / "football_analyzer_high_roi_model.json"
OUT_JSON = ROOT / "data" / "football_analyzer_monte_carlo_2022.json"
OUT_MD = ROOT / "data" / "football_analyzer_monte_carlo_2022.md"


def percentile(values, p):
    values = sorted(values)
    if not values:
        return 0
    idx = (len(values) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def max_drawdown(sequence):
    equity = 0
    peak = 0
    dd = 0
    for pnl in sequence:
        equity += pnl
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return dd


def losing_streak(sequence):
    cur = 0
    best = 0
    for pnl in sequence:
        if pnl < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def broad_model_bets(features, results):
    cfg = {
        "drop_weight": 75,
        "min_drop": 0.015,
        "min_score": 1.5,
        "total_bonus": 2.0,
        "asian_bonus": 1.4,
        "euro_bonus": -1.2,
        "min_euro_odds": 1.8,
        "low_euro_penalty": 4,
        "max_picks_per_match": 2,
    }
    bets = []
    for row in features:
        picks = broad_candidates(row, cfg)
        picks.sort(key=lambda p: (
            p["score"],
            {"total": 2, "asian": 1, "1x2": 0}[p["market"]],
            p["odds"],
        ), reverse=True)
        for pick in picks[: cfg["max_picks_per_match"]]:
            bets.append({**pick, "match": row["match"], "pnl": pnl_for_pick(row, results[row["match_id"]], pick)})
    return bets


def high_roi_bets():
    data = json.loads(HIGH_ROI_PATH.read_text(encoding="utf-8"))
    return data["best_model"]["bets_detail"]


def draw_strong_bets(features, results):
    bets = []
    for row in features:
        for pick in picks_for(row, "1x2"):
            if pick["side"] == "X" and 0.03 <= pick["drop"] <= 0.15 and 1.8 <= pick["odds"] <= 3.5:
                bets.append({**pick, "match": row["match"], "pnl": pnl_for_pick(row, results[row["match_id"]], pick)})
    return bets


def under_ultra_bets(features, results):
    bets = []
    for row in features:
        for pick in picks_for(row, "total"):
            if pick["side"] == "under" and -0.05 <= pick["drop"] <= 0.04 and 1.75 <= pick["odds"] <= 2.25:
                bets.append({**pick, "match": row["match"], "pnl": pnl_for_pick(row, results[row["match_id"]], pick)})
    return bets


def combined_trigger_bets(features, results):
    by_match = {}
    for pick in under_ultra_bets(features, results):
        by_match.setdefault(pick["match"], []).append({**pick, "priority": 2})
    for pick in draw_strong_bets(features, results):
        by_match.setdefault(pick["match"], []).append({**pick, "priority": 1})
    bets = []
    for rows in by_match.values():
        rows.sort(key=lambda p: (p["priority"], p["odds"]), reverse=True)
        bets.append(rows[0])
    return bets


def simulate(name, bets, runs=50000, seed=20220609):
    rng = random.Random(seed + sum(ord(c) for c in name))
    pnls = [float(b["pnl"]) for b in bets]
    n = len(pnls)
    profits = []
    rois = []
    drawdowns = []
    streaks = []
    for _ in range(runs):
        sample = [rng.choice(pnls) for _ in range(n)]
        profit = sum(sample)
        profits.append(profit)
        rois.append(profit / n if n else 0)
        drawdowns.append(max_drawdown(sample))
        streaks.append(losing_streak(sample))
    actual_profit = sum(pnls)
    return {
        "name": name,
        "bets": n,
        "actual_profit": round(actual_profit, 3),
        "actual_roi": round(actual_profit / n, 4) if n else 0,
        "wins": sum(1 for x in pnls if x > 0),
        "pushes": sum(1 for x in pnls if x == 0),
        "losses": sum(1 for x in pnls if x < 0),
        "profit_probability": round(sum(1 for x in profits if x > 0) / runs, 4),
        "roi_p05": round(percentile(rois, 0.05), 4),
        "roi_p25": round(percentile(rois, 0.25), 4),
        "roi_p50": round(percentile(rois, 0.50), 4),
        "roi_p75": round(percentile(rois, 0.75), 4),
        "roi_p95": round(percentile(rois, 0.95), 4),
        "profit_p05": round(percentile(profits, 0.05), 3),
        "profit_p50": round(percentile(profits, 0.50), 3),
        "profit_p95": round(percentile(profits, 0.95), 3),
        "max_drawdown_p50": round(percentile(drawdowns, 0.50), 3),
        "max_drawdown_p05": round(percentile(drawdowns, 0.05), 3),
        "losing_streak_p95": round(percentile(streaks, 0.95), 1),
    }


def main():
    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    results = {r["match_id"]: r for r in json.loads(RESULTS_PATH.read_text(encoding="utf-8"))}
    strategy_bets = {
        "broad_calibrated": broad_model_bets(features, results),
        "high_roi_search": high_roi_bets(),
        "draw_strong_trigger": draw_strong_bets(features, results),
        "under_ultra_trigger": under_ultra_bets(features, results),
        "combined_latest_triggers": combined_trigger_bets(features, results),
    }
    summaries = [simulate(name, bets) for name, bets in strategy_bets.items()]
    OUT_JSON.write_text(json.dumps({"runs": 50000, "strategies": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Monte Carlo 2022 World Cup",
        "",
        "50,000 bootstrap simulations per strategy. Each run samples from the strategy's observed 2022 World Cup bet returns.",
        "",
        "| Strategy | Bets | W-P-L | Actual ROI | Profit Prob | ROI p05 | ROI p50 | ROI p95 | DD p50 | DD bad p05 | Lose Streak p95 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['name']} | {row['bets']} | {row['wins']}-{row['pushes']}-{row['losses']} | "
            f"{row['actual_roi']:.2%} | {row['profit_probability']:.2%} | {row['roi_p05']:.2%} | "
            f"{row['roi_p50']:.2%} | {row['roi_p95']:.2%} | {row['max_drawdown_p50']:.2f} | "
            f"{row['max_drawdown_p05']:.2f} | {row['losing_streak_p95']:.0f} |"
        )
    lines.extend([
        "",
        "Notes:",
        "- `DD bad p05` is the worse 5th percentile max drawdown, expressed in flat units.",
        "- Higher ROI with very few bets is more fragile and more likely to be overfit.",
        "- Use this to compare risk shape, not as proof of future ROI.",
    ])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
