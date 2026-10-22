"""Numbers used in the PARALLAX deck that are not printed by scripts 0-5.
Run after script 5. Reads only its outputs plus the shop-month foundation; writes output/Deck/deck_numbers.json.

1. Three views of a shop (recorded / credited to the shop that created the lead / possible).
2. Theoretical ceiling without double counting: BAU + every assigned lead that has not converted yet
   (at the share this shop books itself) + the GROW lever at the top-10% peer rate.
   Script 5's ceiling adds leads x p90 on top of BAU, which already contains the leads converted so far.
3. Pilot pool: top-40 EXECUTION shops (quality-flagged shops excluded), randomised 20 test / 20 control.
4. Smallest effect a 20-vs-20 test can detect, from how much these shops' quarter-on-quarter change varies.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = pd.read_parquet(ROOT/"output"/"Customer_to_Shop_Growth"/"shop_growth_priority.parquet")
M = pd.read_parquet(ROOT/"Data_clean"/"shop_month_foundation.parquet", columns=["skp_salesroom_id", "month_start", "funded_contract_count"])
OUT = ROOT/"output"/"Deck"; OUT.mkdir(parents=True, exist_ok=True)

a = R[R.attainable_base.notna()].copy()

# 1. Three views -------------------------------------------------------------------------------------
a["credited_3m"] = a.current_3m + a.exported_3m            # contracts this shop's leads produced, wherever booked
views = {"recorded": a.current_3m.sum(), "credited": a.credited_3m.sum(), "booked_elsewhere": a.exported_3m.sum(),
         "booked_elsewhere_share_of_credited": a.exported_3m.sum()/a.credited_3m.sum(),
         "lead_driven_share_of_recorded": a.lead_funded_here.sum()/a.current_3m.sum(),
         "lead_driven_share_median_shop": float((a.lead_funded_here/a.current_3m).median()),
         "shops_undercounted_20pct": int(a.credit_leakage_flag.sum())}

# 2. Theoretical ceiling ----------------------------------------------------------------------------
unconverted = (a.lead_uuids_3m - a.converted_uuids).clip(lower=0)
a["ceiling_theoretical"] = a.bau_3m + unconverted*a.lead_own_booking_share + a.lever_grow_high
a["ceiling_theoretical"] = np.maximum(a.ceiling_theoretical, a.attainable_high)   # never below the high attainable case
concepts = {k: float(a[k].sum()) for k in ["current_3m", "bau_3m", "attainable_low", "attainable_base", "attainable_high", "ceiling_theoretical"]}
concepts["ceiling_script5_double_counted"] = float(a.ceiling_internal.sum())
concepts["shops_floored_at_attainable_high"] = int((a.bau_3m + unconverted*a.lead_own_booking_share + a.lever_grow_high < a.attainable_high - 1e-9).sum())

def shop(s):
    x = a[a.shop == s].iloc[0]
    return {k: (float(x[k]) if isinstance(x[k], (int, float, np.floating, np.integer)) else x[k]) for k in
            ["shop", "province", "peer", "current_3m", "exported_3m", "credited_3m", "bau_3m", "attainable_low", "attainable_base",
             "attainable_high", "ceiling_theoretical", "ceiling_internal", "lead_uuids_3m", "converted_uuids", "lead_conversion",
             "conversion_vs_peer", "lever_leads_base", "lever_leads_elsewhere_base", "lever_grow_base", "agent_fte", "assigned_agents"]}
pair = {"A": shop(101125364), "B": shop(104947973)}

# 3. Pilot pool --------------------------------------------------------------------------------------
a["lead_peer_median"] = a.groupby("peer").lead_uuids_3m.transform("median")
ex = a[a.primary_constraint.str.startswith("EXECUTION")].sort_values("gap_base", ascending=False)
pool = ex.head(40).copy(); pool["pool_rank"] = range(1, len(pool)+1)
pilot = {"pool_size": len(pool), "current_3m": float(pool.current_3m.sum()),
         "gap_low": float(pool.gap_low.sum()), "gap_base": float(pool.gap_base.sum()), "gap_high": float(pool.gap_high.sum()),
         "leads_min": float(pool.lead_uuids_3m.min()), "leads_max": float(pool.lead_uuids_3m.max()),
         "peer_median_leads": sorted(pool.lead_peer_median.unique().tolist()),
         "lead_multiple_min": float((pool.lead_uuids_3m/pool.lead_peer_median).min()),
         "lead_multiple_max": float((pool.lead_uuids_3m/pool.lead_peer_median).max()),
         "conv_vs_peer_min": float(pool.conversion_vs_peer.min()), "conv_vs_peer_max": float(pool.conversion_vs_peer.max()),
         "agent_fte_median": float(pool.agent_fte.median()), "nonaldi_fte_median_network": float(a[a.model == "Non-Aldi"].agent_fte.median()),
         "shop_A_pool_rank": int(pool.loc[pool.shop == 101125364, "pool_rank"].iloc[0]),
         "execution_shops": int(len(ex)), "execution_gap_base": float(ex.gap_base.sum())}

# 4. Detectable effect -------------------------------------------------------------------------------
m = M[M.skp_salesroom_id.isin(pool.shop)].copy()
m["q"] = pd.PeriodIndex(m.month_start, freq="Q")
q = m.groupby(["skp_salesroom_id", "q"]).funded_contract_count.sum().unstack()
q = q.loc[:, [c for c in q.columns if pd.Period("2025Q2") <= c <= pd.Period("2026Q3")]]
chg = np.log(q.where(q > 0)).diff(axis=1).iloc[:, 1:]          # quarter-on-quarter log change per shop
sd = float(np.nanstd(chg.to_numpy(), ddof=1))
n = 20
mde_log = 2.8*sd*np.sqrt(2/n)                                    # 80% power, 5% two-sided, two equal arms
pilot.update({"qoq_log_sd": sd, "mde_log": float(mde_log), "mde_pct": float(np.expm1(mde_log)), "quarters_used": [str(c) for c in q.columns]})
pilot["gap_low_pct_of_test_arm"] = pilot["gap_low"]/pilot["current_3m"]
pilot["gap_base_pct_of_test_arm"] = pilot["gap_base"]/pilot["current_3m"]

# 5. Context numbers quoted on the slides --------------------------------------------------------------
import duckdb
con = duckdb.connect()
CC = (ROOT/"Data_clean"/"contract_clean.parquet").as_posix()
W = "date_apply_ts>=TIMESTAMP '2026-07-01' AND date_apply_ts<TIMESTAMP '2026-10-01'"
central = con.execute(f"""SELECT count(*) funded, count(*) FILTER (WHERE skp_salesroom_id=42902170) central,
    count(*) FILTER (WHERE upper(product_raw)='CC') cards, count(*) FILTER (WHERE upper(product_raw)='CC' AND skp_salesroom_id=42902170) central_cards,
    count(DISTINCT skp_emp_pre_process_id) FILTER (WHERE skp_salesroom_id=42902170) central_employees,
    string_agg(DISTINCT upper(product_raw), ',') FILTER (WHERE skp_salesroom_id=42902170) central_products
    FROM read_parquet('{CC}') WHERE is_funded AND {W}""").df().iloc[0].to_dict()
central["central_share"] = central["central"]/central["funded"]; central["central_card_share"] = central["central_cards"]/central["cards"]
funnel = {"ids_funded_in_window": int((R.current_3m > 0).sum()), "master_ids_funded_in_window": int((R.master & (R.current_3m > 0)).sum()),
          "assessed": int(len(a)), "execution": int(len(ex)), "pool": int(len(pool)),
          "share_booked_outside_master": float(R.loc[~R.master, "current_3m"].sum()/R.current_3m.sum()),
          "share_master_not_assessed": float((R.loc[R.master, "current_3m"].sum() - a.current_3m.sum())/R.current_3m.sum()),
          "share_assessed": float(a.current_3m.sum()/R.current_3m.sum())}
bt = pd.read_parquet(ROOT/"output"/"Shop_Performance_and_BAU"/"task1_backtest.parquet")
h = bt[(bt.outcome == "funded") & (bt.split == "holdout")].copy()
h["err"] = h.mae*h.n; h["act"] = h.err/h.wape
pooled = h.groupby(["tier", "horizon", "model"])[["err", "act"]].sum()
pooled = (pooled.err/pooled.act).round(3).unstack().reset_index().to_dict("records")
context = {"central_id": central, "funnel": funnel, "holdout_wape_pooled": pooled,
           "bau_reliability": a.forecast_reliability.fillna("NO_FORECAST").value_counts().to_dict()}

pool[["pool_rank", "shop", "province", "peer", "current_3m", "attainable_low", "attainable_base", "attainable_high", "lead_uuids_3m",
      "lead_peer_median", "conversion_vs_peer", "agent_fte"]].to_csv(OUT/"pilot_pool_top40.csv", index=False)
report = {"views": views, "four_concepts_assessed": concepts, "pair": pair, "pilot": pilot, "context": context}
(OUT/"deck_numbers.json").write_text(json.dumps(report, indent=1, default=float, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=1, default=float, ensure_ascii=False))
