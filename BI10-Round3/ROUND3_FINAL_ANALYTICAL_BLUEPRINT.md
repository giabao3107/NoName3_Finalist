# BI10 Round 3 — Final Analytical Blueprint

**Status:** Planning blueprint; no models, slides, figures, or dashboard have been built.  
**Scope:** Preserve the bounded hybrid architecture and the exact five-stage order:

> **Foundation → Task 1 — Shop Performance & BAU → Task 2 — Growth Constraints & Potential → Task 3 — Prioritization & Allocation → Business Recommendations**

## 1. Executive Design

### Analytical storyline

> **Customer Understanding (Round 2) → Current Shop Performance → BAU Forecasting → Growth Constraints → Attainable Potential → Resource Prioritization → Business Actions.**

Round 2 supplies a customer-level starting point, not shop attribution or evidence that its recommended actions worked. Round 3 supplies shop-attributed events and operating records, but there are material gaps in shop-master coverage, product mapping, historical status and customer overlap. Round 2 segments are therefore a historical customer baseline for linked records. Shop-level segment reporting is conditional on demonstrated coverage, valid event/shop attribution and decision-relevant precision.

### Four growth quantities

| Quantity                       | Definition                                                                                                                                                              | Evidence type                                                                                                                         |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Current Actual**             | Observed shop outcome over the latest three complete months. Primary metric: raw application-event count; raw `credit_amount` is secondary, never called funded volume. | Observed extract measure, with shop/date coverage flags.                                                                              |
| **Business-as-Usual (BAU)**    | Next-three-month forecast if observed conditions continue without intervention.                                                                                         | Rolling-origin-validated forecast where feasible; otherwise trailing baseline with wide uncertainty.                                  |
| **Attainable Potential**       | Internal scenario-based attainable range on the same metric/horizon, anchored to comparable shops and explicit assumptions.                                             | Peer benchmark/scenario; not causal uplift.                                                                                           |
| **Addressable Market Ceiling** | Internal in-scope ceiling: eligible existing customers × transparent peer conversion benchmark, limited to supported products and observed customer/shop scope.         | Internal proxy, not total Vietnamese market size; coverage and uncertainty explicit. External TAM remains separately “Not estimated.” |

`T2_07_Four_Concept_Growth_Overview` shows all four concepts on a consistent three-month application-event scale. Label the fourth bar **Internal serviceable ceiling (proxy)** and decompose it into eligible-customer denominator × peer-rate assumption. It is not external TAM. If either component is unsupported, show “Not estimable”—never fabricate.

## 2. Evidence Base and Round 2 → Round 3 Integration

### Local evidence inspected

- Round 3 brief: `BI10-Round3/BI10_ROUND03.md`
- Round 3 data: `BI10-Round3/Round3_BI10_dataset/`
- Round 2 deck: `BI10-Round2/Slide.pdf`
- Round 2 analysis/output: `BI10-Round2/ANALYSIS.md`, `BI10-Round2/output/Task1/`, `Task2/`, `Task3/`

The Round 2 deck is a 15-page, 16:9 report-style deck. It uses SCQA for its opening, then a data-quality section, evidence-to-implication analysis, segment/action matrices, decision tables and an assumptions strip. Its white canvas, blue/navy palette, red risk accents, KPI cards, tables and “Insight → Implication → Action” pattern guide the proposed slides. Round 2 numerical findings are **not** Round 3 findings.

### Valid linkage and preliminary key-only coverage

Round 2 score outputs contain `SKP_CLIENT`, FHS/CES fields and customer-segment fields. The FHS and CES Parquet files each have 1,000,528 unique customer keys, and Round 2’s analysis documents their one-to-one join by `SKP_CLIENT`. Round 3 `contract.csv` and `leads.csv` both contain `skp_client`.

A read-only key-only membership check found:

| Join scope |                                           Distinct linked customers | R2-linked raw event rows / all fact rows | All fact rows mapped to current shop master | R2-linked rows within master-mapped subset                                                                                      |
| ---------- | ------------------------------------------------------------------: | ---------------------------------------: | ------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------------- |
| Contracts  | 349,399 (34.92% of R2 cohort; 13.90% of 2,513,153 contract clients) |             633,398 / 3,775,371 (16.78%) |                                     621,387 | 39,384 / 621,387 (6.34%); also 39,384 / 633,398 (6.22% of R2-linked rows), across 31,329 customers (8.97% of linked customers). |
| Leads      |      228,427 (22.83% of R2 cohort; 6.29% of 3,631,389 lead clients) |              477,921 / 6,130,637 (7.80%) |                                     385,273 | 27,309 / 385,273 (7.09%); also 27,309 / 477,921 (5.71% of R2-linked rows), across 19,192 customers (8.40% of linked customers). |

R3 distinct-client denominators are per fact file (contracts versus leads), not a combined network-client universe; R2 contains 1,000,528 unique customers. Master-mapped counts are not the R2-linked subset. R2-linked rows are 39,384/633,398 = 6.22% of linked contract rows and 27,309/477,921 = 5.71% of linked lead rows. Lead counts are raw/unweighted. `sample_weight` is undocumented: 4,130,637 rows have weight 1.0 and 2,000,000 have 19.662104 (sum 43,454,845), concentrated in `INSTANT_TWO_RTDM` × `CL`. Mechanical weighting shifts CL share 71.93%→96.04% and source share 55.20%→93.68%; these are unvalidated sensitivities, not population estimates. Do not treat weights as lead totals or apply them to conversions/customers/sales.
These are **linkage feasibility counts, not growth findings**. They do not yet apply the full post-score time cutoff, validate product compatibility, resolve repeated lead UUIDs, establish lead-to-contract uniqueness or evaluate selection bias.

### Join and aggregation contract

1. **Customer score join:** Round 2 `SKP_CLIENT` → Round 3 `skp_client`. Start from FHS/CES Parquet outputs, validate one-to-one key alignment and use the documented tier fields to derive segments; R2 linkage is supporting context, not a prerequisite for the core shop pair. Avoid the approximately 1.31 GB CSV unless a required field exists only there.
2. **Temporal alignment:** use Round 2 declared score snapshots for historical labels and apply the later common cutoff to score-linked outcome analyses. If feature-level provenance is uncertain, disclose and omit affected R2 claims; do not block shop analyses. Never use current/final status, later DPD or later actions as baseline predictors.
3. **Product alignment:** crosswalk Round 3 lead product codes to contract categories before product-level conversion analysis. Only four lead product codes overlap contract `product` values exactly; string equality is not a valid complete crosswalk.
4. **Shop attribution:** use lead `skp_salesroom` as the lead-side/origin shop where semantics are confirmed; use contract `skp_salesroom` as the booking shop. Report the two separately. A customer may appear in multiple shops; do not assign a single “home shop” without evidence.
5. **Lead–contract matching:** require same client, compatible product and `date_assigned <= date_apply`. A direct `skp_credit_case` key is a validation signal, not an unconditional substitute. Ambiguous candidates remain flagged; do not credit a contract amount multiple times.
6. **Aggregation:** preserve event counts and distinct-customer counts separately. For segment figures, aggregate linked post-cutoff events by segment, product, month, shop and event role; state whether each denominator is customers, leads, applications or eligible contracts.
7. **Generalization gate:** report linkage coverage by shop, segment, product and time; compare linked versus unlinked populations. Show shop-level segment composition only if coverage and precision support the decision. Otherwise use a matched-cohort/peer-group view or state that shop-level segment composition is not estimable.

Round 2’s customer population is heavily concentrated in the Dec-2024/Jan-2025 Tết application wave, as documented in its analysis and slides. It is not a complete current shop customer book. Do not generalize that cohort to the full Round 3 network without evidence.

## 3. Foundation — Data Engineering, Quality & Business EDA

The Foundation remains a complete engineering and EDA phase, but uses **two main-deck slides**. Detailed audit evidence moves to the appendix and supporting files.

### Main-deck Foundation slide 1 — Data trust at a glance

Composite of source/entity coverage, time coverage and attribution-quality summary. Add a compact “issue → treatment” table only for limitations that alter interpretation. Keep visible:

- Shop-master match coverage and the rule that unmatched attributes are not silently discarded.
- Usable event-date windows and the common cutoff.
- Whether lead–contract links meet the specified predicates.
- The requirement to confirm status and amount semantics before calling a measure funded volume.
- Full fact population versus the narrower mapped/eligible population; show the undocumented lead `sample_weight` as a high-impact G7 exception and distinguish raw extracted rows from mechanical sensitivity.

### Main-deck Foundation slide 2 — Customer-to-shop growth bridge

Composite of **R2 segment → R3 product event → lead-origin/contract-booking shop → shop performance → constraint**. Show linkage coverage and matched/unmatched denominators. Show segment composition at individual-shop level only after the gates below pass.

### Technical audit and EDA retained

The full code-level audit and appendix must cover:

- Entity keys, nulls, primary grains, seller/shop/customer integrity, unmatched reasons and schema-to-file column parity.
- Preprocessing, date parsing, sentinel handling, category normalization, weight-field provenance and documented exclusions.
- Repeated lead UUIDs versus exact duplicate rows; no UUID deduplication until event/version meaning is resolved.
- Lead–contract candidate generation, match predicates, ambiguity and contradictory direct keys.
- Product crosswalk coverage and unmapped codes.
- Employee/shop assignment intervals and duplicate assignments; headcount proxy versus FTE distinction.
- Current shop attributes versus historical validity; old/new geographic boundaries.
- One-to-many joins and reconciliation of contract counts/amounts before and after integration.
- Temporal-leakage checks for every feature at each forecast origin.
- Business EDA on shop heterogeneity, cohorts, lead/product mix, staffing proxy and repayment-quality maturity.
- Round 2 join coverage, event-time filters, linked-versus-unlinked selection checks, and raw-versus-weighted lead sensitivity for `sample_weight`.

### Decision and assumption register (competition-run defaults)

No business/source owner is available in this competition. Replace approval gates with a versioned assumption register: publish ID, provisional definition, evidence, confidence, sensitivity range, affected outputs and reversal trigger. These are contest defaults, not company policy. Run low/base/high sensitivity for material assumptions; never relabel assumptions as observed facts.

| ID                   | Provisional default                                                                                                                  | Sensitivity / treatment                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| A01 outcome          | Raw application-event count by `date_apply`; raw `credit_amount` secondary only. No “funded” label.                                  | Compare unique cases and non-null amount.                                                |
| A02 period           | Latest three complete observed months; next three months for BAU/potential.                                                          | One- and six-month windows if possible.                                                  |
| A03 cutoff           | Round 2 declared production snapshot/common later cutoff; post-cutoff only for score-linked claims.                                  | If provenance uncertain, omit R2 shop claims; core shop analysis proceeds.               |
| A04 eligibility      | Non-null shop ID and recorded events in ≥2/3 complete months; do not infer active/closed from current status.                        | Re-run 1/3 and 3/3; retain sparse/unmatched shops in coverage appendix.                  |
| A05 peer match       | Current actual within ±10%, same available category/model and region where supported; relax dimensions in stated order if <10 peers. | ±5%/±20%, exact/relaxed dimensions, minimum peer n=5/10.                                 |
| A06 lead/product     | Raw event rows only; exact product equality is a candidate, not approved compatibility; weights never population weights.            | Mechanical-weight sensitivity appendix only, clearly unvalidated.                        |
| A07 potential        | Peer median base; 25th/75th percentile low/high for same metric/horizon.                                                             | 10th/90th percentiles and leave-one-peer-out.                                            |
| A08 internal ceiling | Distinct eligible existing customers with supported product opportunity × best-supported peer conversion rate.                       | Median/base and 25th/75th percentile peer rates; label internal proxy, not total market. |
| A09 action readiness | TEST / ENABLE / LEARN / MONITOR evidence-led groups, no hidden weighted score or ROI absent costs.                                   | Test pair/group membership across A04-A08.                                               |

| Gate                         | Acceptance condition                                                                                              |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **G0 — Metric/cutoff**       | Apply A01-A03; status semantics are unnecessary for application counts; make no funded-volume claim.              |
| **G1 — Grain/key integrity** | Document grains, retain repeated UUID versions, validate score uniqueness and report unmatched keys.              |
| **G2 — Attribution/product** | Apply lead-contract predicates; retain ambiguity; use raw measures where product map is unapproved.               |
| **G3 — Time/leakage**        | Flag invalid/sentinel dates; use only origin-available forecast features.                                         |
| **G4 — Join reconciliation** | One-to-one joins preserve rows/amounts; aggregate one-to-many details first.                                      |
| **G5 — Eligibility**         | Publish A04 population, coverage and exclusions; retain unknown shops.                                            |
| **G6 — R2 bridge**           | Apply A03 and report linkage/representativeness; R2 does not gate core pair, BAU or prioritization.               |
| **G7 — Weight semantics**    | No approval assumed; raw rows are extract counts; weight sensitivity is appendix-only, not a population estimate. |

### Eligible shop populations

- **Task 1:** usable historical outcomes and complete periods; separate mature incumbents, new/short-history shops, known closed shops and unknown-status shops. Forecast active shops at origin only when active status is supportable. Pre-opening/post-closure periods are not zero-sales months.
- **Task 2:** eligibility is constraint-specific. Lead execution requires a valid lead denominator; product analysis requires a validated product map; staffing requires valid employee intervals; risk analysis requires matured DPD follow-up. Missing one diagnostic does not automatically exclude a shop from all others.
- **Task 3:** active, action-eligible shops with traceable estimates, feasible actions and sufficient confidence. High-opportunity/low-confidence shops are learning-pilot candidates, not automatically high-investment candidates.

## 4. Task 1 — Shop Performance & Business-as-Usual

**Question:** Where does each shop stand today, and where is it heading without additional intervention?

### Methods and outputs

- Apply A01-A04: latest three complete months for Current Actual; raw application-event count primary, raw amount secondary, never funded volume. No owner confirmation blocks this explicitly labeled proxy analysis.
- BAU horizon is next three months on the same outcome/scale as Attainable Potential.
- Build shop-month panels with explicit event coverage; no records mean unknown, not zero, unless source coverage supports zero.
- Model ladder: trailing mean/last-period baseline; seasonal naïve only if supported; pooled model challenger.
- Use rolling-origin backtests, never random splits. Short history means limited evidence; report WAPE/MASE, bias and interval coverage; avoid MAPE with zeros.
- Choose the **pair spine** before forecasting: select the closest eligible pair with similar current actual, common-support context and a material contrast in a directly observed constraint. Freeze selection using only current/pre-period data. Show trajectories and BAU intervals. This is explanatory, not causal.
- If complexity does not consistently beat simple baselines, retain trailing baseline as a planning reference with wide uncertainty.

**Output contract — `shop_bau_forecast`:** one row per shop × outcome × origin × horizon, containing current window, BAU estimate/range (calibrated quantiles only where supported), eligibility, pair ID, quality flags and model version.

**Fallback:** deliver observed pair and trailing baseline where possible. If no strict pair/forecast exists, use closest pair under relaxed A05 criteria and label BAU unavailable; the pair remains the narrative anchor.

## 5. Task 2 — Growth Constraints & Attainable Potential

**Question:** Given two shops with similar current applications, what observed difference could explain distinct room to grow—and what is the transparent internal ceiling within stated scope?

### Methods

1. **Pair first:** carry Task 1 pair into every diagnostic. Contrast raw leads, supported product mix, assigned-staff proxy, customer linkage and data quality. Separate measured differences from hypotheses; no causal claim.
2. **Demand:** raw recorded lead-event counts/product mix by shop-period. `sample_weight` is undocumented: no population total or weighted conversion claim. Existing-customer leads are not total market demand.
3. **Execution:** matched-sample diagnostics only; no conversion rate unless lead grain, status, product compatibility and numerator/denominator are supportable. Label rates as observed sample associations.
4. **Staffing/quality:** assignment count is proxy, not FTE/capacity; compare only matured DPD cohorts. Missing diagnostics do not block other evidence.
5. **Comparable frontier:** construct common-support peers per A05; show support count and distribution.
6. **Attainable Potential:** A07 peer-percentile range for next-three-month application count, conditional on comparable-shop scenario; not causal uplift.
7. **Internal serviceable ceiling:** A08 eligible existing-customer opportunity set × peer benchmark conversion rate. Require distinct linked customers and supported product/event evidence; disclose denominator coverage and low/base/high rates. This is internal planning proxy, not TAM. If denominator or rate is unsupported, say what is missing and retain other analyses.

**Output contract — `shop_constraint_potential`:** shop/pair, observed diagnostics, peer support, BAU, potential low/base/high, internal ceiling low/base/high where supportable, gap vs BAU, assumption IDs, eligible denominator, coverage and confidence.

**Fallback:** no validated conversion means no conversion claim, but observed pair contrast and peer-based application range still publish. Staffing stays a proxy; unsupported ceiling does not block the analysis.

## 6. Task 3 — Prioritization & Allocation

**Question:** Which shops should receive the next test or enablement resource, how much opportunity is in scope, and why?

### Methods

Use auditable decision groups, not unavailable owner-approved weights:

1. Apply A04 eligibility; show confidence/coverage separately.
2. Base opportunity = max(0, Attainable Potential base − BAU P50); retain low/high bounds and do not convert to money.
3. Assign readiness from observed evidence: **TEST** (clear gap + testable constraint), **ENABLE** (data/process prerequisite), **LEARN** (high potential, weak evidence), **MONITOR** (no supported gap/low confidence).
4. Apply matured-quality flags as descriptive guardrails; insufficient maturity means “quality unknown,” not pass. High-confidence administrative or service pilots may proceed as learning tests, but no scale recommendation implies quality clearance.
5. Compare illustrative pilot capacities (e.g., 5/10/20 shops); select high-confidence TEST/ENABLE candidates and reserve a learning slot for high-opportunity/low-confidence cases. These are exercise scenarios, not company budgets or optima.
6. Re-run pair/groups/selections across A04-A08; report stable vs assumption-sensitive membership.

Use opportunity × feasibility with confidence separate. Without costs, margins and capacity, provide named eligible examples and bounded pilot roster; no ROI, budget optimization or causal uplift.

**Output contract — `shop_priority`:** shop, group/action, evidence IDs, BAU/potential range, constraint evidence/hypothesis, quality, confidence/coverage, assumption IDs and scenario slot.

**Fallback:** unstable estimates become LEARN/ENABLE rather than disappearing; if all evidence is weak, recommend named measurement/data-remediation pilot, not an empty ranking.

## 7. Refined 37-Figure Manifest

**Priority:** `Main` = candidate for the 14 substantive main slides; `Supporting` = secondary evidence/small inset or appendix; `Appendix` = technical detail.  
**Readiness:** `Ready` = computable after mechanical processing; `Conditional` = requires stated validation or a declared assumption/sensitivity; `Blocked` is reserved for outputs that cannot be computed at all. Readiness applies to result-bearing figures; conditional outputs must show caveats rather than substitute fabricated values.

### Foundation (9)

| ID / working title                         | Business question; inputs                                                                                                                               | Method and chart                                                                                                                                                                                                                                                                                    | Expected insight and business implication                                                                                                  | Upstream dependencies                                                                                                                                   | Priority / readiness   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **FND_01_Data_Coverage**                   | What share of facts link to shops/sellers/customers, and are the CSV schemas documented? All source keys, fact counts, shop master and schema files.    | Row/key match rates by source/period plus schema parity; coverage funnel and reconciliation table.                                                                                                                                                                                                  | Shows where results generalize, where attributes are unknown, and which fields lack definitions.                                           | Raw source inventory, entity keys and data dictionaries.                                                                                                | Main / Ready           |
| **FND_02_Time_and_Outcome_Maturity**       | Which dates/outcomes are usable? `date_apply`, `date_sign`, `date_assigned`, status, DPD, extract date.                                                 | Parse/sentinel/maturity audit; monthly coverage calendar.                                                                                                                                                                                                                                           | Defines valid cutoffs and outcome windows.                                                                                                 | Raw event-date fields; extract-date confirmation.                                                                                                       | Main / Conditional     |
| **FND_03_Lead_Integrity_and_Weight_Audit** | Are repeated UUID rows versions, and what does `sample_weight` mean? UUID, timestamps, status, product/source and weights.                              | Compare fields within UUID; profile the weight distribution and cell concentration; calculate raw and mechanical weighted sensitivity separately with an “unvalidated” label.                                                                                                                       | Prevents double counting and exposes a potentially material sample/weight effect without asserting a population interpretation.            | Raw lead events; weight definition from source owner is required before weighted interpretation.                                                        | Appendix / Conditional |
| **FND_04_Lead_Contract_Match_Quality**     | Which links satisfy the brief’s rules? Client, product, assignment/application dates, case IDs.                                                         | Candidate bridge; validated, unique, ambiguous, contradictory and unmatched funnel; lag distribution.                                                                                                                                                                                               | Establishes which execution measures are defensible.                                                                                       | FND_02 dates, FND_03 audited lead grain, approved FND_05 crosswalk.                                                                                     | Main / Conditional     |
| **FND_05_Product_Crosswalk**               | Which lead codes map to contract categories? Lead variants, contract `product`, product detail.                                                         | Approved mapping table and code/category heatmap; unmatched values visible.                                                                                                                                                                                                                         | Prevents false non-conversions and invalid product comparisons.                                                                            | Raw lead/contract product codes and business-approved product definitions.                                                                              | Appendix / Conditional |
| **FND_06_Shop_Heterogeneity**              | How do outcomes vary by recorded shop characteristics? Monthly actuals, raw shop ID, master attributes and mapping flags.                               | Distributions by supported category/model/product/tenure; small multiples.                                                                                                                                                                                                                          | Motivates peer comparison, not by itself a headroom claim.                                                                                 | FND_01 coverage, raw shop attributes and preliminary shop-month outcome aggregate.                                                                      | Main / Conditional     |
| **FND_07_R2_Customer_to_Shop_Bridge**      | Can R2 segments link to later product events and attributed shops? R2 FHS/CES keys/tiers; R3 client, product, dates, shop IDs and sample-weight status. | Key-only and post-cutoff coverage funnel; segment × product × event-role aggregate. Raw events and distinct customers are primary; keep any pre-G7 weighted sensitivity separate in the appendix, and use weighted event estimates only after approval. Shop panel only if precision/coverage pass. | Connects customer understanding to shop growth without forcing one shop per customer or treating unvalidated weights as population counts. | R2 score outputs and cutoff; Round 3 keys; FND_05 for product grouping; G7 before weighted estimates; FND_04 only for contract-linked lead attribution. | Main / Conditional     |
| **FND_08_Employee_Shop_Validity**          | Can staffing be counted at shop-period level? Employee/shop IDs, valid-from/to and status.                                                              | Interval dedupe and as-of counts; assignment coverage by shop type.                                                                                                                                                                                                                                 | Establishes whether headcount is a usable proxy.                                                                                           | Raw employee/shop intervals; FND_01 shop-key validation.                                                                                                | Appendix / Conditional |
| **FND_09_Repayment_Maturity**              | Which DPD cohorts have comparable follow-up? Application vintage, DPD checkpoints, status/product.                                                      | Maturity-window cohort rates; vintage × checkpoint plot.                                                                                                                                                                                                                                            | Prevents unequal follow-up masquerading as quality differences.                                                                            | FND_02 dates and approved DPD maturity definitions.                                                                                                     | Appendix / Conditional |

### Task 1 — Shop Performance & BAU (8)

| ID / working title                      | Business question; inputs                                                                                                  | Method and chart                                                                                                | Expected insight and business implication                               | Upstream dependencies                                                                               | Priority / readiness                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **T1_01_Current_Actual_Baseline**       | What does each eligible shop achieve now? Monthly count/amount, status definition, active periods.                         | Agreed recent window; shop distribution with KPI cards and denominators.                                        | Establishes actual baseline and dispersion.                             | G0 outcome/window definition, FND_01 coverage and FND_02 usable dates.                              | Main / Conditional                  |
| **T1_02_Monthly_Shop_Trends**           | Is performance changing? Monthly outcomes, shop activity/product.                                                          | Monthly trend with active-shop-normalized series.                                                               | Separates underlying change from network expansion/closure.             | T1_01 outcome panel and FND_02 dates.                                                               | Main / Conditional                  |
| **T1_03_Shop_Lifecycle_Cohorts**        | Do new/mature/closed shops follow different paths? Start/end dates, status, monthly outcomes.                              | Cohort trajectories with active months; small multiples.                                                        | Supports separate forecast populations.                                 | Confirmed shop lifecycle dates and T1_01 monthly outcomes.                                          | Supporting / Conditional            |
| **T1_04_Comparable_Shop_Benchmark**     | How does a shop compare with similar shops? Outcomes, model/category/product, tenure, area, staffing proxy.                | Common-support peer groups; peer distribution/interval plot.                                                    | Identifies unusual relative performance without causal headroom claims. | T1_01 outcomes, FND_06 attributes and common-support criteria.                                      | Main / Conditional                  |
| **T1_05_Forecast_Model_Ladder**         | Does complexity improve on baselines? Monthly outcomes and cutoff-available predictors.                                    | Compare naïve/trailing, regularized, pooled/hierarchical; boosting as challenger; error dot plot.               | Selects simplest defensible BAU method.                                 | T1_01/T1_02 panel and leakage-safe predictors; any lagged lead feature requires G7 weight decision. | Main / Conditional                  |
| **T1_06_Rolling_Origin_Backtest**       | How do forecasts compare with later held-out outcomes? Origins, horizon, actual/predicted values.                          | Expanding-window rolling origins; actual-vs-forecast and error-by-horizon plots.                                | Demonstrates true out-of-sample performance.                            | T1_05 candidate models, T1_02 time panel and valid cutoffs.                                         | Main / Conditional                  |
| **T1_07_Forecast_Interval_Calibration** | Are shop forecast ranges calibrated? Backtest residuals by horizon/segment.                                                | Interval coverage/width and error-by-segment.                                                                   | Shows where forecast-based priority should be cautious.                 | T1_06 out-of-sample residuals.                                                                      | Supporting / Conditional            |
| **T1_08_Two_Shop_Actual_vs_BAU**        | Can two shops with similar current actual have different trajectories? Eligible shops, current actual and matched context. | Required pair-spine figure: select closest pair per A05; show actuals and BAU ranges; no causal interpretation. | Directly answers the case question and anchors the narrative.           | A01-A05, T1_01/T1_04; trailing baseline if calibration is weak.                                     | Main / Conditional (required spine) |

### Task 2 — Growth Constraints & Potential (10)

| ID / working title                          | Business question; inputs                                                                                                             | Method and chart                                                                                                                                                                                                                                                   | Expected insight and business implication                                                         | Upstream dependencies                                                                             | Priority / readiness                |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **T2_01_Lead_Opportunity_by_Shop**          | Where are observed leads concentrated? Audited leads, product, assignment date, shop, active periods and `sample_weight`.             | Primary chart: raw recorded event counts by shop-period/product. Before G7, mechanical weighted sensitivity is an appendix/QA diagnostic only, explicitly unvalidated; after G7, show the approved weighted estimate alongside raw counts.                         | Separates extracted-row volume from a validated population estimate and from total market demand. | FND_01/02 shop/date coverage, FND_03 lead/weight audit and eligibility.                           | Main / Conditional                  |
| **T2_02_Validated_Lead_Execution_Funnel**   | Which links meet observed predicates? Valid bridge, reason map, product crosswalk, dates and weight provenance.                       | Conditional matched-sample diagnostic with explicit denominator; omit conversion rate if semantics/grain unsupported.                                                                                                                                              | May motivate process tests but does not gate pair/potential.                                      | FND_02/03/04/05 and source limitations.                                                           | Main / Conditional                  |
| **T2_03_Staffing_Productivity_Proxy**       | Do assigned staff and throughput co-vary? As-of employee count, outcomes/shop type.                                                   | Within-peer outcome per assigned employee; scatter with uncertainty.                                                                                                                                                                                               | Staffing hypothesis, not capacity or causal effect.                                               | FND_08 valid-time assignments and T1_01 outcomes.                                                 | Supporting / Conditional            |
| **T2_04_Product_Mix_Opportunity**           | Does observed raw mix vary by product/shop type?                                                                                      | Raw event mix primary; unvalidated mechanical weight sensitivity appendix-only.                                                                                                                                                                                    | Identifies diagnostic areas without claiming demand.                                              | FND_05 mapping coverage, FND_06, T1_01; raw-code description does not require approved crosswalk. | Main / Conditional                  |
| **T2_05_R2_Segment_Product_Quality_Bridge** | Do linked R2 segments differ in later products/outcomes? FHS/CES tiers, thin file, post-cutoff events, weight status and matured DPD. | Use raw matched-event and distinct-customer denominators. Before G7, place any mechanical weighted event sensitivity only in the appendix; after approval, publish weighted event estimates only if the estimator is valid. Never weight distinct-customer counts. | Adds customer context for shop constraints while showing sampling/coverage sensitivity.           | FND_07 cutoff bridge, FND_05 map, FND_09 mature outcomes and G7 for weighted estimates.           | Main / Conditional                  |
| **T2_06_Comparable_Shop_Frontier**          | What range do comparable shops achieve? T1 peers, active months, quality-controlled outcomes.                                         | Peer median/upper range or conditional frontier only within common support.                                                                                                                                                                                        | Reference range, not a guarantee of attainment.                                                   | T1_01 actuals, T1_04 peers and common-support criteria.                                           | Main / Conditional                  |
| **T2_07_Four_Concept_Growth_Overview**      | How do Actual, BAU, Potential and scoped ceiling differ?                                                                              | Pair-centered, same metric/horizon; internal serviceable proxy per A08 with denominator/rate shown; external TAM remains not estimated.                                                                                                                            | Distinguishes observed, forecast, scenario and bounded ceiling.                                   | T1_01/T1_08, T2_06/08; T2_09 denominator audit.                                                   | Main / Conditional                  |
| **T2_08_Attainable_Scenario_Sensitivity**   | Which assumptions drive feasible range?                                                                                               | Pair/network low-base-high and sensitivity using A04-A08.                                                                                                                                                                                                          | Makes assumption dependence visible, not gated on owner approval.                                 | Pair, diagnostics/frontier and assumption register.                                               | Main / Conditional                  |
| **T2_09_Addressable_Market_Evidence**       | What is the defensible in-scope denominator?                                                                                          | Internal eligible-customer denominator/exclusion waterfall; external TAM separately unavailable.                                                                                                                                                                   | Estimates bounded proxy or identifies missing component.                                          | R3 client/lead data, A03/A08 and coverage.                                                        | Appendix / Conditional              |
| **T2_10_Two_Shop_Constraint_Contrast**      | Why might the pair have different opportunity?                                                                                        | Required contrast of observed leads, mapped product where possible, staffing proxy, R2 coverage and quality maturity; observed vs hypothesized.                                                                                                                    | Connects trajectory gap to a testable action.                                                     | T1_08 and available diagnostics; gaps are caveats, not blockers.                                  | Main / Conditional (required spine) |

### Task 3 — Prioritization & Allocation (6)

| ID / working title                           | Business question; inputs                                                     | Method and chart                                                     | Expected insight and business implication                            | Upstream dependencies                          | Priority / readiness     |
| -------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------- | ------------------------ |
| **T3_01_Opportunity_Gap_Distribution**       | How large/uncertain are eligible shops’ gaps?                                 | A07 potential minus BAU with low/base/high and eligible denominator. | Quantifies opportunity without false precision.                      | T1_01/T1_06/07 or trailing baseline; T2_07/08. | Main / Conditional       |
| **T3_02_Opportunity_Feasibility_Confidence** | Which shops combine opportunity, actionable constraint and credible evidence? | Opportunity × feasibility; confidence separate.                      | Produces TEST/ENABLE/LEARN/MONITOR, no hidden score.                 | T3_01, T2 evidence and A09.                    | Main / Conditional       |
| **T3_03_Quality_Guardrail_Tradeoff**         | Does opportunity conflict with matured quality?                               | Quality vs opportunity; unknown maturity shown.                      | Guards against volume-only decisions without unverified thresholds.  | FND_09 maturity and T2 evidence.               | Supporting / Conditional |
| **T3_04_Priority_Groups_by_Action**          | What shops/examples qualify?                                                  | Named eligible groups/counts, evidence/assumptions; count once.      | Usable pilot shortlist.                                              | T3_02/A09.                                     | Main / Conditional       |
| **T3_05_Resource_Allocation_Scenarios**      | What trade-offs follow from pilot capacities?                                 | Compare 5/10/20-shop scenarios; no costs/ROI.                        | Shows capacity vs reach/learning.                                    | T3_02/T3_04; capacities illustrative.          | Supporting / Conditional |
| **T3_06_Rank_Robustness**                    | Do groups/pair persist?                                                       | Membership, pair identity and opportunity stability across A04-A08.  | Separates robust targets from sensitivity-dependent learning pilots. | T3_01/T3_02/scenario register.                 | Main / Conditional       |

### Business Recommendations (4)

| ID / working title                        | Business question; inputs                         | Method and chart                                                                                                                    | Expected insight and business implication                                          | Upstream dependencies                   | Priority / readiness |
| ----------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------- | -------------------- |
| **REC_01_Constraint_to_Action_Map**       | Does each action address an evidenced constraint? | Pair-led: target → observed evidence → constraint/hypothesis → low-risk test → KPI.                                                 | Actionable recommendations without pretending owner approval.                      | Pair diagnostics and T3 groups.         | Main / Conditional   |
| **REC_02_Opportunity_and_Resource_Cards** | What opportunity/resources accompany each test?   | Bounded event-count range, assumption IDs, confidence, illustrative resources; costs unavailable.                                   | Trade-offs without fabricated financial value.                                     | REC_01, T2_07/08, T3_05.                | Main / Conditional   |
| **REC_03_Pilot_to_Scale_Roadmap**         | How should actions be tested?                     | Prepare → pilot → evaluate → scale/stop; accountable function is proposed, not confirmed.                                           | Reversible next steps.                                                             | REC_01/02 and delivery assumptions.     | Main / Conditional   |
| **REC_04_KPI_and_Scale_Stop_Gates**       | What evidence justifies continuing?               | Pre-register application-event KPI, quality/customer guardrails, comparator/cadence; thresholds provisional and sensitivity-tested. | Usable measurement plan without claiming powered effects or authorized thresholds. | REC_03, A01-A02 and design assumptions. | Main / Conditional   |

### Figure distribution

| Priority   |  Count | Use                                                           |
| ---------- | -----: | ------------------------------------------------------------- |
| Main       |     27 | Candidate components for the 14 substantive main slides.      |
| Supporting |      5 | Secondary evidence/small inset or appendix.                   |
| Appendix   |      5 | Technical detail, not required for main narrative.            |
| **Total**  | **37** | Candidate library, not a requirement to publish every figure. |

### Figure dependency map (arrows point upstream → downstream)

```text
Raw Round 2/3 files -> FND_01, FND_02, FND_03, FND_05, FND_08, FND_09
FND_02 + FND_03 + FND_05 -> FND_04 lead-contract matching
FND_01 + shop attributes + preliminary shop-month aggregates -> FND_06
R2 scores + verified score cutoff + R3 SKP_CLIENT -> FND_07
FND_05 -> T2_04; FND_05 -> FND_07/T2_05 product analyses
FND_04 -> FND_07 only for lead-contract-linked attribution
FND_03/G7 -> T2_01, T2_02, T2_04, T2_05; G7 -> T1_05 only if lagged lead features are used
FND_01/02 + A01-A04 -> T1_01; T1_01 -> T1_02/03/04/05
FND_06 + A05 -> T1_04; T1_02 + T1_05 -> T1_06 -> T1_07
T1_01 + A05 -> required pair T1_08; T1_08 + T2 diagnostics -> T2_10
FND_01/02/03 -> T2_01; FND_02/03/04/05 -> conditional T2_02
FND_08 + T1_01 -> T2_03; FND_05/FND_06/T1_01 -> T2_04
FND_07/FND_05/FND_09 + post-cutoff alignment -> T2_05
T1_01 + T1_04 + A05 -> T2_06; T1_08 + T2_10 -> pair-centered T2_07/T2_08
A08 eligible-customer denominator + supported peer rate -> internal ceiling in T2_07; external source -> optional external TAM only
T2_07/08 + diagnostics -> T3_01/T3_02 -> T3_04/T3_06 -> REC_01 -> REC_02 -> REC_03/REC_04
```

Manifest upstream-dependency cells list prerequisites; this map is build order. Conditional diagnostics (R2 coverage, lead conversion, external TAM) do not block the pair, application-based potential or provisional prioritization. If A08 denominator/rate cannot be supported, only the internal ceiling is “Not estimable”; other concepts remain.

## 8. Slide Composition and 10-Minute Story

The deck contains **14 substantive slides plus a cover**. Foundation occupies exactly two main slides. Figure IDs are reused components; executive KPI cards are derived from verified figures, not extra findings.

| Slide | Section                    | Composition                                                                                                                                  |
| ----: | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
|     1 | Cover                      | Team/title plus the exact required first-slide line **“Visual supported by Canva”**; competition cover treatment only here.                  |
|     2 | Executive summary          | SCQA; after analysis, up to three KPI cards and decision headline.                                                                           |
|     3 | Foundation                 | FND_01 coverage, FND_02 time, FND_04 match summary and a compact G7 sample-weight caveat; detailed weight sensitivity stays in the appendix. |
|     4 | Foundation                 | FND_06 shop context + FND_07 customer-to-shop bridge; matched/unmatched denominators.                                                        |
|     5 | Task 1                     | T1_01 Current Actual + T1_02 trend.                                                                                                          |
|     6 | Task 1                     | **Pair spine T1_08:** matched-current shops, observed trajectories and BAU/trailing ranges; state selection rule.                            |
|     7 | Task 1                     | T1_04 peer support + T1_05/T1_06 forecast check; pair is not causal.                                                                         |
|     8 | Task 2                     | T2_01 raw lead diagnostics + T2_02 only if valid; never block pair analysis.                                                                 |
|     9 | Task 2                     | **T2_10 pair constraint contrast** + supporting evidence/coverage caveats.                                                                   |
|    10 | Task 2                     | **T2_07 hero:** pair Actual, BAU, Potential, internal ceiling; show denominator and peer rate.                                               |
|    11 | Task 2                     | T2_06 frontier + T2_08 sensitivity; assumption register visible.                                                                             |
|    12 | Task 3                     | T3_01/T3_02 opportunity groups and confidence; no “no shops ranked” fallback.                                                                |
|    13 | Task 3                     | T3_04/T3_06 named pilot shortlist and stability; T3_05 illustrative capacities.                                                              |
|    14 | Business Recommendations   | REC_01/02 pair-led action cards with bounded opportunity and unknown costs explicit.                                                         |
|    15 | Business Recommendations   | REC_03/04 pilot protocol, provisional KPI and scale/stop gates.                                                                              |
|   16+ | Appendix (not substantive) | Audit evidence, forecast/scenario validation, external-source citations and supporting assumptions.                                          |

### 10-minute pacing

- **0:00–0:35:** Round 2 → Round 3 question and answer-first summary.
- **0:35–1:35:** two Foundation slides; only reliability and linkage limits that affect interpretation.
- **1:35–3:20:** Task 1 — current position, peers and validated BAU.
- **3:20–6:25:** Task 2 — observed constraints, potential range and four-concept hero visual.
- **6:25–7:45:** Task 3 — eligible priority groups and robustness.
- **7:45–9:35:** actions, resources, pilot and scale gates.
- **9:35–10:00:** bottom-line decision and Q&A transition.

Detailed audit, forecast validation, assumption register and internal-ceiling denominator audit belong in appendix. Do not claim external TAM absent sources; this does not prevent a clearly labeled internal serviceable-ceiling proxy. Limit main slides to complementary visuals, compact table, verified KPIs and an **Insight → Implication → Action** statement.

## 9. Visualization Style Guide

- White 16:9 analytical canvas; primary blue `#004aad`, deep navy such as `#14213d`, light-blue tints and neutral gray.
- Reserve red for risk, negative outcomes or critical exceptions.
- Follow Round 2 hierarchy: section eyebrow, strong working headline, compact chart/table body, direct annotations and consistent footer.
- Use Anton display, Be Vietnam body and Noto Sans labels where available; do not shrink text to fit excess panels.
- Every chart states metric, unit, period, denominator, source and assumptions. Use ranges and uncertainty where meaningful.
- Use descriptive working titles during analysis; replace with evidence-based takeaways only after validation.
- When authorized, export static reusable SVG/PNG and PDF vector graphics. No dashboard or repeated decorative cover art.

## 10. Business Recommendation Framework

Every action must provide:

| Field                | Required content                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| Target shops         | Task 3 priority group, eligibility and mapping status.                                                |
| Supporting evidence  | Exact Task 1–3 figure/table and validation reference.                                                 |
| Diagnosed constraint | Observed evidence separated from hypothesis.                                                          |
| Intervention         | Specific operational action; no causal uplift claim without a test.                                   |
| Opportunity          | Attainable range versus BAU on the same metric/horizon; monetary conversion only if validated.        |
| Resources and owner  | Capacity, cost, responsible function and assumptions; mark missing values.                            |
| KPIs/guardrails      | Primary business outcome, quality/risk metric, contact/customer guardrails and cadence.               |
| Uncertainty          | Forecast, scenario, mapping and sampling uncertainty remain distinct.                                 |
| Pilot validation     | Assignment unit, comparator, power/sample-size plan, intention-to-treat estimate and scale/stop gate. |

**Conditional examples, not current recommendations:**

- High verified lead opportunity with low validated conversion → test lead routing/follow-up.
- Low peer-relative outcomes with a reliable staffing proxy → test a capacity intervention; do not infer FTE from assignment counts.
- Product/customer mix differences with an approved crosswalk → test a suitable product/service pathway with risk safeguards.
- Missing external market denominator → do not recommend expansion using a fabricated ceiling.

For shop-level intervention, randomize eligible shops or seller clusters, block on pre-period BAU/product/region where feasible, and account for spillovers. For genuinely customer-level interventions, randomize customers within shops only if interference is controlled. Set sample size and guardrails before launch; report intention-to-treat effects with uncertainty.

## 11. Implementation Specifications

### Required analytical tables and grains

| Table                                 | Grain and key                                    | Required content                                                                                                                                                                                              |
| ------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `contract_fact`                       | One row per `skp_credit_case`                    | Shop/client/product, application date, validated status/amount, quality fields and flags.                                                                                                                     |
| `lead_event_version`                  | Lead UUID × source version/event when applicable | Lead date, customer, origin shop, offered product, status, `sample_weight`, weight provenance/approval state and duplicate/version flags.                                                                     |
| `lead_contract_bridge`                | Lead × candidate contract × match rule           | Direct-key evidence, predicates, match state, ambiguity and lag.                                                                                                                                              |
| `product_crosswalk`                   | Source system × source code                      | Normalized product, evidence, mapping status, effective period and owner approval.                                                                                                                            |
| `shop_validity`                       | Salesroom × valid-time interval                  | Attributes and whether historical validity is known or current-snapshot only.                                                                                                                                 |
| `employee_shop_interval`              | Employee × shop × validity interval              | Status, role, dedup flag and headcount-proxy eligibility.                                                                                                                                                     |
| `r2_customer_segment`                 | One row per `SKP_CLIENT` and score cutoff        | FHS/CES tiers, segment, thin-file flag, cutoff, provenance and join eligibility.                                                                                                                              |
| `contract_shop_month`                 | Shop × month × outcome                           | Actual count/amount with active, coverage and outcome-definition flags.                                                                                                                                       |
| `lead_shop_month_product`             | Origin shop × month × product                    | Raw event rows, distinct customers, match states and `weight_status`; separate mechanical sensitivity from any approved weighted estimate.                                                                    |
| `customer_segment_shop_product_month` | Shop × month × product × R2 segment × event role | Raw matched events and distinct customers; separate pre-G7 mechanical weighted sensitivity from approved weighted-event estimates; never weight distinct-customer counts. Origin vs booking remains separate. |
| `shop_bau_forecast`                   | Shop × outcome × origin × horizon                | Actual window, BAU prediction/interval, model and eligibility flags.                                                                                                                                          |
| `shop_constraint_potential`           | Shop/peer group × outcome × scenario             | Constraints, peer support, Attainable Potential, BAU gap, assumption IDs, coverage/confidence, market-ceiling status and lead-weight basis where applicable.                                                  |
| `shop_priority`                       | One row per eligible shop and priority run       | Group, confidence, guardrail, evidence, lead-weight basis where relevant, and optional validated cost/value.                                                                                                  |
| `recommendation_pilot_plan`           | Action × target group × pilot version            | Owner function, resources, KPI, assignment/control plan and gates.                                                                                                                                            |

### Validation and regression checks

- Primary-key uniqueness and declared grain; repeated UUIDs remain visible until semantics are resolved.
- `sample_weight` value distribution, provenance, permitted scope and reconciliation to source documentation; compare raw/weighted sensitivity without assuming a population interpretation.
- Product/status crosswalk completeness; unmapped values retained.
- Lead–contract predicates, ambiguous candidates, direct-key validation and consistent numerator/denominator treatment if weights are approved.
- Temporal leakage: every feature timestamp at/before forecast origin; post-cutoff status/DPD/contact excluded as predictors.
- Join inflation: reconcile fact rows/amounts before and after joins; aggregate one-to-many details before fact-level reporting.
- Shop/employee as-of validity; unknown historical attributes remain unknown.
- R2 score uniqueness/cutoff, post-score outcome filtering and linked/unlinked comparison.
- Forecast baseline comparison, rolling origins, bias, horizon error and interval calibration.
- Scenario sensitivity, rank stability and separation of forecast/scenario/causal evidence.
- Privacy: aggregate customer segments only and suppress low-count cells under company policy.

## 12. Model, Scenario and Fallback Rules

| Risk or missing input                  | Primary handling                                                                                                                            | Fallback                                                                                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sample_weight` semantics undocumented | Before approval, raw rows are counts of the extract; put mechanical weight sensitivity in a separate, explicitly unvalidated appendix view. | If the source owner cannot define it, use raw recorded-event counts only, make no population-weighted lead/product/conversion claim, and do not use the weight sum as a volume total. |
| Shop master incomplete                 | Retain raw shop IDs and unmatched attributes.                                                                                               | Compare only supportable groups; no network inference from mapped subset.                                                                                                             |
| Repeated UUID semantics unresolved     | Preserve versions and report row/unique-ID counts separately.                                                                               | No lead conversion claim.                                                                                                                                                             |
| Product map incomplete                 | Show mapped coverage and unmatched categories.                                                                                              | Omit product-level conversion/constraint conclusions.                                                                                                                                 |
| R2 join or cutoff fails                | Keep R2 as customer-context narrative only.                                                                                                 | No shop-level segments.                                                                                                                                                               |
| R2 join is selective                   | Show matched coverage and linked/unlinked comparison.                                                                                       | Broader aggregates only if representative and precise.                                                                                                                                |
| Forecast history insufficient/unstable | Use transparent trailing/last-period BAU with wide intervals.                                                                               | No boosting or seasonal claim.                                                                                                                                                        |
| Peer support weak                      | Descriptive distributions without frontier extrapolation.                                                                                   | No Attainable Potential for unsupported shops.                                                                                                                                        |
| Intervention assumptions absent        | Label scenarios as hypothetical.                                                                                                            | No uplift claim; define pilot hypotheses only.                                                                                                                                        |
| Market denominator absent              | External TAM stays “Not estimated”; construct A08 internal ceiling if denominator/rate are supportable.                                     | If either is unavailable, state the missing component and proceed with pair/potential analysis.                                                                                       |
| Costs/margins/capacity absent          | Use opportunity ranges and priority groups.                                                                                                 | No ROI or budget optimizer.                                                                                                                                                           |

## 13. Must Have / Should Have / Optional

### Must Have

- Use A01-A09 defaults and sensitivity ranges instead of unavailable owner approvals; distinguish assumptions from observations.
- Make the similar-current two-shop pair the recurring narrative spine from Task 1 through recommendations.
- Estimate and label an internal serviceable-ceiling proxy; keep external TAM distinct and not estimated absent sources.
- Produce evidence-led action groups and illustrative pilot-capacity scenarios; no empty ranking, ROI or optimal-allocation claim.
- Use rolling-origin validation where feasible and uncertainty-aware trailing baseline otherwise.
- Separate lead-origin from contract-booking shop; keep R2 historical, aligned and coverage-qualified, not a gate on core answer.
- Separate associations, peer benchmarks, scenarios and pilot effects; trace recommendations to evidence and measurement.

### Should Have

- Approved product crosswalk with effective dates.
- Historic shop mapping or explicit unknown population.
- Linked/unlinked Round 2 comparison and segment-stability checks.
- Peer groups with documented common support.
- Matured repayment guardrail and rank sensitivity.
- Round 2 customer insight integration where valid.

### Optional

- Gradient boosting if it beats transparent models in rolling tests.
- External market-ceiling estimate if denominator and geography are defensible.
- Budget optimization if values, costs, capacities and constraints are validated.
- Geographic expansion analysis if boundaries are harmonized.

## 14. Implementation Roadmap

1. **Foundation:** inventory/grains/cutoff and regression checks; lock A01-A09 in a visible register, run sensitivities and produce coverage evidence. No owner-approval dependency for explicitly labeled contest defaults.
2. **Task 1:** build shop-month panels/peers; select and freeze pair; validate forecast or use trailing baseline with uncertainty.
3. **Task 2:** build pair diagnostics, peer potential and internal-ceiling denominator/rate audit; quantify sensitivity; external TAM remains not estimated unless sourced.
4. **Task 3/recommendations:** form TEST/ENABLE/LEARN/MONITOR groups, test stability, prepare illustrative capacity scenarios and pair-led pilot/KPI plan without ROI or authorization claims.

## 15. Submission Readiness and Handoff

### Presentation PDF

- English, 16:9 PDF; slide 1 includes the exact line **“Visual supported by Canva”**.
- Filename pattern: `TeamName_LeaderName_R03_BI10_Slide.pdf`. Bracketed names in the brief are placeholders; replace them and do not type literal brackets.
- Distinguish the internal serviceable-ceiling proxy from external TAM; cite any external denominator and never imply the proxy is total market.

### Supporting ZIP

- Include all SQL and Python analysis files used to produce the solution.
- Include a README for every external dataset with: (1) source and reporting period; (2) geographic coverage and granularity; (3) mapping/integration method; (4) business relevance/additional insight; (5) assumptions, limitations and potential biases.
- Attachments ZIP pattern: `TeamName_LeaderName_R03_BI10_Attachments.zip` (replace the team/leader placeholders; do not type literal brackets).

### Appendix plan (slides after the main 15 pages)

- **A1 — Entity and coverage audit:** key coverage, unmatched shops, source-schema parity and row-count reconciliation.
- **A2 — Lead integrity, weight and matching:** repeated UUIDs, exact duplicates, `sample_weight` distribution/provenance, raw-vs-weighted sensitivity, match predicates, ambiguity and conversion eligibility.
- **A3 — Product/staffing/time audit:** product crosswalk, one-to-many inflation, employee validity intervals, sentinel dates and maturity.
- **A4 — R2 bridge validation:** score cutoff, matched/unmatched cohort comparison, post-cutoff customer/product/shop coverage and segment suppression rules.
- **A5 — Forecast evidence:** model ladder, rolling-origin windows, error/bias and interval calibration.
- **A6 — Scenario and market evidence:** sensitivity assumptions, external denominator method if supported, and source citations.

## 16. Critical Methodological Review and Change Log

### Critical review

- Lead `sample_weight` is present in `leads.csv` but undocumented in `StructureTable.xlsx`; `code_product_type_original` is also omitted from the documented Leads schema. A read-only check found 4,130,637 rows at weight 1.0 and 2,000,000 at 19.662104; mechanical weighting changes total row weight from 6,130,637 to 43,454,845 and shifts CL from 71.93% to 96.04% and `INSTANT_TWO_RTDM` from 55.20% to 93.68%. All rows above 1.0 are in `id_lead_source=INSTANT_TWO_RTDM` × normalized `code_product_type=CL`, split across `code_product_type_original` values SCC/SCC PR2/SCC PR3. The weighted mix shift is therefore concentrated in one normalized source/product cell; it is not independent evidence of population product demand.
- Round 2 can link by customer key, but overlap with Round 3 is partial; the shop-master-constrained subset is smaller still. Combined with the Tết-heavy Round 2 cohort, the bridge is valuable but conditional, not a universal shop segmentation.
- Round 3 contract status is current/final in a single extract; historical as-of status may be unavailable. This limits funded outcomes and leakage-safe backtesting.
- Contract application history is about 21 months; lead-assignment history is shorter. Seasonal and long-horizon claims should remain cautious.
- Current salesroom metadata covers only a subset of historical fact-shop IDs. Keep unmapped shops visible.
- Lead status and product mapping do not support conversion until validated.
- Staffing records are assignments, not FTE hours or causal capacity.
- No supplied external market denominator supports an external TAM claim; no cost/margin/capacity inputs support ROI or budget optimization.
- Round 2 overlap is partial and shop-constrained coverage smaller/Tết-heavy; R2 is supporting conditional context, not universal segmentation.
- Contract status is current/final in one extract; application count is safer primary outcome than funded volume.
- Short history means BAU is a planning baseline with limited validation, not a strong seasonal model.
- Current shop attributes are incomplete snapshots; unmatched IDs remain visible and status does not infer historic activity.
- Lead status/product/weight limitations constrain conversion claims but do not block pair, raw diagnostics, peer potential or application-based prioritization.
- No external data are required for a bounded internal serviceable ceiling; it is not TAM and must disclose denominator coverage and rate assumptions.
- Two-shop comparison is the required narrative spine; if strict matching fails, relax A05 transparently and label limitation.

### Change log

1. Replaced unavailable approvals with contest assumptions A01-A09 and sensitivity ranges.
2. Made similar-current two-shop comparison the required recurring spine.
3. Added bounded internal serviceable-ceiling proxy, distinct from external TAM.
4. Replaced conditional Task 3/recommendation fallbacks with provisional groups and illustrative capacity scenarios.
5. Preserved data limitations, non-causal language, raw lead counts and validation safeguards.
