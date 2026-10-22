# Task 1 — Shop performance and BAU

Observed contract history: Jan 2025 to Sep 2026.
Observed facts use contract-positive months; missing shop-months remain missing. Current actual is null unless all three months are observed.
BAU compares trailing three-observation mean with a simple linear trend. Selection and validation choose; holdout only evaluates.
Tier A has insufficient validation because validation origins do not contain 18 prior months; the 18-month threshold was retained.
Intervals are empirical residual ranges, not guaranteed 80% intervals.
Comparable pair ['99180387', '99363629'] status=ILLUSTRATIVE_ONLY; flags=['99180387:DESCRIPTIVE_ONLY_BAU', '99363629:DESCRIPTIVE_ONLY_BAU'].
Task 2 may use only EVIDENCE_QUALIFIED_BAU rows quantitatively; DESCRIPTIVE_ONLY rows cannot support gap claims.

## T1_01_Current_Actual_Baseline
![T1_01_Current_Actual_Baseline](T1_01_Current_Actual_Baseline.png)
Current actual varies by prior observed history.
Only complete three-month windows are reported through Sep 2026.
Incomplete windows remain missing; funded-origin is a configured proxy.

## T1_02_Monthly_Shop_Trends
![T1_02_Monthly_Shop_Trends](T1_02_Monthly_Shop_Trends.png)
The two outcome measures move on different scales.
Window Jan 2025 to Sep 2026.
Only observed contract months are plotted.

## T1_03_Shop_Lifecycle_Cohorts
![T1_03_Shop_Lifecycle_Cohorts](T1_03_Shop_Lifecycle_Cohorts.png)
First recorded activity dates show unequal history lengths.
21 recorded-activity cohorts.
Extract activity is not a verified shop opening date.

## T1_04_Comparable_Shop_Benchmark
![T1_04_Comparable_Shop_Benchmark](T1_04_Comparable_Shop_Benchmark.png)
Comparable shops provide a descriptive range.
8 peer groups with n≥30.
Peer performance is not guaranteed attainable potential.

## T1_05_Forecast_Model_Ladder
![T1_05_Forecast_Model_Ladder](T1_05_Forecast_Model_Ladder.png)
A simple linear trend is tested against trailing average.
12 model-tier-horizon validation cells available.
Tier A has no valid validation origins; holdout is not used to choose models.

## T1_06_Rolling_Origin_Backtest
![T1_06_Rolling_Origin_Backtest](T1_06_Rolling_Origin_Backtest.png)
Validation-selected model and holdout results are separate.
WAPE shown separately; N/A where no support.
Few time origins and overlapping shop observations limit inference.

## T1_07_Forecast_Interval_Calibration
![T1_07_Forecast_Interval_Calibration](T1_07_Forecast_Interval_Calibration.png)
Intervals are empirical descriptive ranges, not guaranteed 80% intervals.
0 undercoverage flags across funded cells.
Tier A intervals unavailable; holdout sample is not independent by shop.

## T1_08A_Shop_Actual_vs_BAU
![T1_08A_Shop_Actual_vs_BAU](T1_08A_Shop_Actual_vs_BAU.png)
Similar-current shops are compared under the declared A05 rule.
Complete 3-month actual observed: 3/3; BAU reliability: TRAILING_BASELINE_FALLBACK.
Pair comparison is descriptive, not causal; BAU is not attainable uplift.

## T1_08B_Shop_Actual_vs_BAU
![T1_08B_Shop_Actual_vs_BAU](T1_08B_Shop_Actual_vs_BAU.png)
Similar-current shops are compared under the declared A05 rule.
Complete 3-month actual observed: 3/3; BAU reliability: TRAILING_BASELINE_FALLBACK.
Pair comparison is descriptive, not causal; BAU is not attainable uplift.
