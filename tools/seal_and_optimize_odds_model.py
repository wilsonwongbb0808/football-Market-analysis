import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGED_PATH = ROOT / "data" / "oddsportal_worldcup2022_opening_merged.json"
FEATURES_PATH = ROOT / "data" / "worldcup2022_odds_features_sealed.json"
RESULTS_PATH = ROOT / "data" / "worldcup2022_results_sealed.json"
CONFIG_PATH = ROOT / "data" / "football_analyzer_model_calibration.json"
REPORT_PATH = ROOT / "data" / "football_analyzer_model_calibration.md"


def drop_pct(open_odds, close_odds):
    if not open_odds or not close_odds:
        return 0
    return (open_odds - close_odds) / open_odds


def settle_1x2(result, side, odds):
    outcome = "1" if result["home_score"] > result["away_score"] else "2" if result["away_score"] > result["home_score"] else "X"
    return odds - 1 if outcome == side else -1


def settle_asian(result, line, side, odds):
    diff = result["home_score"] - result["away_score"]
    adjusted = diff + line if side == "home" else -diff - line
    if adjusted > 0:
        return odds - 1
    if adjusted == 0:
        return 0
    return -1


def settle_total(result, line, side, odds):
    goals = result["home_score"] + result["away_score"]
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


def seal_files(rows):
    features = []
    results = []
    for idx, row in enumerate(rows, 1):
        match_id = f"wc2022-{idx:02d}"
        features.append({
            "match_id": match_id,
            "match": row["match"],
            "home": row["home"],
            "away": row["away"],
            "h2h_home_open": row["h2h_home_open"],
            "h2h_draw_open": row["h2h_draw_open"],
            "h2h_away_open": row["h2h_away_open"],
            "h2h_home_close": row["h2h_home_close"],
            "h2h_draw_close": row["h2h_draw_close"],
            "h2h_away_close": row["h2h_away_close"],
            "ah_line": row["ah_line"],
            "ah_home_open": row["ah_home_open"],
            "ah_away_open": row["ah_away_open"],
            "ah_home_close": row["ah_home_close"],
            "ah_away_close": row["ah_away_close"],
            "total_line": row["total_line"],
            "over_open": row["over_open"],
            "under_open": row["under_open"],
            "over_close": row["over_close"],
            "under_close": row["under_close"],
        })
        results.append({
            "match_id": match_id,
            "match": row["match"],
            "home_score": row["home_score"],
            "away_score": row["away_score"],
        })
    FEATURES_PATH.write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return features, {row["match_id"]: row for row in results}


def return_shape_decimal(odds):
    if odds < 1.6:
        return -4
    if odds < 1.8:
        return -2
    if odds <= 2.35:
        return 1.2
    if odds <= 3.5:
        return 0.4
    if odds <= 5:
        return -0.4
    return -1.2


def candidates(row, cfg):
    picks = []
    for side, key in [("1", "h2h_home"), ("X", "h2h_draw"), ("2", "h2h_away")]:
        op, cl = row[f"{key}_open"], row[f"{key}_close"]
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["euro_bonus"] + return_shape_decimal(cl)
        if cl < cfg["min_euro_odds"]:
            score -= cfg["low_euro_penalty"]
        picks.append({"market": "1x2", "side": side, "odds": cl, "drop": d, "score": score})
    for side, key in [("home", "ah_home"), ("away", "ah_away")]:
        op, cl = row[f"{key}_open"], row[f"{key}_close"]
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["asian_bonus"] + return_shape_decimal(cl)
        picks.append({"market": "asian", "side": side, "odds": cl, "drop": d, "score": score})
    for side, key in [("over", "over"), ("under", "under")]:
        op, cl = row[f"{key}_open"], row[f"{key}_close"]
        if op is None or cl is None:
            continue
        d = drop_pct(op, cl)
        score = d * cfg["drop_weight"] + cfg["total_bonus"] + return_shape_decimal(cl)
        picks.append({"market": "total", "side": side, "odds": cl, "drop": d, "score": score})
    return [p for p in picks if p["drop"] >= cfg["min_drop"] and p["score"] >= cfg["min_score"]]


def pnl_for_pick(row, result, pick):
    if pick["market"] == "1x2":
        return settle_1x2(result, pick["side"], pick["odds"])
    if pick["market"] == "asian":
        return settle_asian(result, row["ah_line"], pick["side"], pick["odds"])
    return settle_total(result, row["total_line"], pick["side"], pick["odds"])


def evaluate(features, results, cfg):
    bets = []
    for row in features:
        picks = candidates(row, cfg)
        picks.sort(key=lambda p: (
            p["score"],
            {"total": 2, "asian": 1, "1x2": 0}[p["market"]],
            p["odds"],
        ), reverse=True)
        for pick in picks[:cfg["max_picks_per_match"]]:
            result = results[row["match_id"]]
            bets.append({
                **pick,
                "match_id": row["match_id"],
                "match": row["match"],
                "pnl": pnl_for_pick(row, result, pick),
            })
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
        "sample_bets": bets[:10],
    }


def market_summary(bets):
    out = {}
    for market in ["total", "asian", "1x2"]:
        rows = [b for b in bets if b["market"] == market]
        if not rows:
            continue
        profit = sum(b["pnl"] for b in rows)
        out[market] = {
            "bets": len(rows),
            "wins": sum(1 for b in rows if b["pnl"] > 0),
            "pushes": sum(1 for b in rows if b["pnl"] == 0),
            "losses": sum(1 for b in rows if b["pnl"] < 0),
            "profit_units": round(profit, 3),
            "roi": round(profit / len(rows), 4),
        }
    return out


def optimize(features, results):
    configs = []
    for drop_weight, min_drop, min_score, total_bonus, asian_bonus, euro_bonus, max_picks in product(
        [60, 75, 90, 110],
        [0, 0.015, 0.025, 0.04],
        [1.5, 2.5, 3.5, 4.5, 5.5],
        [0.8, 1.4, 2.0, 2.6],
        [0.4, 0.9, 1.4, 1.9],
        [-1.2, -0.8, -0.4, 0],
        [1, 2],
    ):
        configs.append({
            "drop_weight": drop_weight,
            "min_drop": min_drop,
            "min_score": min_score,
            "total_bonus": total_bonus,
            "asian_bonus": asian_bonus,
            "euro_bonus": euro_bonus,
            "min_euro_odds": 1.8,
            "low_euro_penalty": 4,
            "max_picks_per_match": max_picks,
        })
    results_rows = [r for r in (evaluate(features, results, cfg) for cfg in configs) if r and r["bets"] >= 16]
    # Prefer profit and enough coverage, not tiny high-ROI samples.
    results_rows.sort(key=lambda r: (r["profit_units"], r["roi"], -abs(r["bets"] - 42)), reverse=True)
    return results_rows


def main():
    rows = json.loads(MERGED_PATH.read_text(encoding="utf-8"))
    features, results = seal_files(rows)
    ranked = optimize(features, results)
    best = ranked[0]
    CONFIG_PATH.write_text(json.dumps({
        "sealed_features": str(FEATURES_PATH.relative_to(ROOT)),
        "sealed_results": str(RESULTS_PATH.relative_to(ROOT)),
        "best_model": best,
        "top_models": ranked[:20],
        "notes": [
            "Results were stored separately from odds features before optimization.",
            "Recommendation is optimized for expected return and market tolerance: total goals first, Asian handicap second, 1X2 last when scores are close.",
            "1X2 odds below 1.80 are penalized heavily and should not be a main recommendation.",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Football Analyzer Model Calibration",
        "",
        "Data: 2022 World Cup bet365 opening-to-closing odds from OddsPortal.",
        "",
        f"Sealed odds features: `{FEATURES_PATH.relative_to(ROOT)}`",
        f"Sealed results: `{RESULTS_PATH.relative_to(ROOT)}`",
        "",
        "## Best Model",
        "",
        f"- Bets: {best['bets']}",
        f"- W-P-L: {best['wins']}-{best['pushes']}-{best['losses']}",
        f"- Profit: {best['profit_units']} units",
        f"- ROI: {best['roi']:.2%}",
        f"- Config: `{json.dumps(best['config'], ensure_ascii=False)}`",
        "",
        "## Market Split",
        "",
        "| Market | Bets | W-P-L | Profit | ROI |",
        "|---|---:|---|---:|---:|",
    ]
    for market, summary in best["by_market"].items():
        lines.append(
            f"| {market} | {summary['bets']} | {summary['wins']}-{summary['pushes']}-{summary['losses']} | "
            f"{summary['profit_units']:.2f} | {summary['roi']:.2%} |"
        )
    lines.extend([
        "",
        "## Top 10 Models",
        "",
        "| Rank | Bets | W-P-L | Profit | ROI | Total Bonus | Asian Bonus | 1X2 Bonus | Min Score | Min Drop |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for i, row in enumerate(ranked[:10], 1):
        cfg = row["config"]
        lines.append(
            f"| {i} | {row['bets']} | {row['wins']}-{row['pushes']}-{row['losses']} | "
            f"{row['profit_units']:.2f} | {row['roi']:.2%} | {cfg['total_bonus']} | {cfg['asian_bonus']} | "
            f"{cfg['euro_bonus']} | {cfg['min_score']} | {cfg['min_drop']:.1%} |"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
