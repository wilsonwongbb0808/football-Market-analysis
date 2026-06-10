# Football Analyzer Model Calibration

Data: 2022 World Cup bet365 opening-to-closing odds from OddsPortal.

Sealed odds features: `data\worldcup2022_odds_features_sealed.json`
Sealed results: `data\worldcup2022_results_sealed.json`

## Best Model

- Bets: 111
- W-P-L: 59-3-49
- Profit: 14.5 units
- ROI: 13.06%
- Config: `{"drop_weight": 75, "min_drop": 0.015, "min_score": 1.5, "total_bonus": 2.0, "asian_bonus": 1.4, "euro_bonus": -1.2, "min_euro_odds": 1.8, "low_euro_penalty": 4, "max_picks_per_match": 2}`

## Market Split

| Market | Bets | W-P-L | Profit | ROI |
|---|---:|---|---:|---:|
| total | 34 | 24-0-10 | 6.88 | 20.24% |
| asian | 50 | 24-3-23 | -0.34 | -0.68% |
| 1x2 | 27 | 11-0-16 | 7.96 | 29.48% |

## Top 10 Models

| Rank | Bets | W-P-L | Profit | ROI | Total Bonus | Asian Bonus | 1X2 Bonus | Min Score | Min Drop |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 111 | 59-3-49 | 14.50 | 13.06% | 2.0 | 1.4 | -1.2 | 1.5 | 1.5% |
| 2 | 111 | 59-3-49 | 14.50 | 13.06% | 2.0 | 1.9 | -1.2 | 1.5 | 1.5% |
| 3 | 111 | 59-3-49 | 14.18 | 12.77% | 2.0 | 1.9 | -1.2 | 2.5 | 1.5% |
| 4 | 111 | 59-3-49 | 14.18 | 12.77% | 2.0 | 1.9 | -0.8 | 2.5 | 1.5% |
| 5 | 111 | 59-3-49 | 14.18 | 12.77% | 2.6 | 1.9 | -1.2 | 2.5 | 1.5% |
| 6 | 111 | 59-3-49 | 14.18 | 12.77% | 2.6 | 1.9 | -0.8 | 2.5 | 1.5% |
| 7 | 110 | 58-3-49 | 13.93 | 12.66% | 1.4 | 1.4 | -1.2 | 1.5 | 1.5% |
| 8 | 110 | 58-3-49 | 13.93 | 12.66% | 1.4 | 1.9 | -1.2 | 1.5 | 1.5% |
| 9 | 110 | 58-3-49 | 13.82 | 12.56% | 2.6 | 1.9 | -0.8 | 2.5 | 1.5% |
| 10 | 110 | 58-3-49 | 13.82 | 12.56% | 2.6 | 1.9 | -0.4 | 2.5 | 1.5% |