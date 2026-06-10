# Monte Carlo 2022 World Cup

50,000 bootstrap simulations per strategy. Each run samples from the strategy's observed 2022 World Cup bet returns.

| Strategy | Bets | W-P-L | Actual ROI | Profit Prob | ROI p05 | ROI p50 | ROI p95 | DD p50 | DD bad p05 | Lose Streak p95 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| broad_calibrated | 111 | 59-3-49 | 13.06% | 87.26% | -5.59% | 12.93% | 32.59% | -8.61 | -17.02 | 8 |
| high_roi_search | 20 | 9-0-11 | 17.15% | 70.77% | -32.00% | 16.65% | 68.15% | -4.24 | -9.27 | 8 |
| draw_strong_trigger | 12 | 7-0-5 | 86.25% | 97.88% | 6.25% | 86.25% | 164.58% | -2.00 | -5.00 | 5 |
| under_ultra_trigger | 6 | 6-0-0 | 92.83% | 100.00% | 84.00% | 92.33% | 102.83% | 0.00 | 0.00 | 0 |
| combined_latest_triggers | 17 | 12-0-5 | 79.53% | 99.43% | 28.29% | 80.00% | 129.30% | -2.00 | -4.00 | 4 |

Notes:
- `DD bad p05` is the worse 5th percentile max drawdown, expressed in flat units.
- Higher ROI with very few bets is more fragile and more likely to be overfit.
- Use this to compare risk shape, not as proof of future ROI.