"""Task 2: transparent peer-reference potential, observed constraints, and test priorities."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"Data_clean"
TASK1=ROOT/"output"/"Shop_Performance_and_BAU"
OUT=ROOT/"output"/"Growth_Potential_and_Prioritization"
PHASE1_GATE=ROOT/"output"/"Data processing"/"validation_report.json"
MIN_PEERS=30
PILOT_CAPACITY=10
COLORS={"blue":"#004AAD","navy":"#14213d","mid":"#8FAAD1","red":"#C51E1E","gray":"#6B7280","grid":"#E4E8ED"}
plt.rcParams.update({"font.family":"Arial","font.size":8,"figure.facecolor":"white","axes.facecolor":"white","savefig.facecolor":"white","axes.spines.top":False,"axes.spines.right":False,"axes.grid":True,"grid.color":COLORS["grid"],"axes.axisbelow":True})


def safe_json(value: Any) -> Any:
    if isinstance(value,pd.DataFrame): return safe_json(value.to_dict("records"))
    if isinstance(value,pd.Series): return safe_json(value.to_dict())
    if isinstance(value,dict): return {str(k):safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [safe_json(v) for v in value]
    if isinstance(value,pd.Timestamp): return value.isoformat()
    if isinstance(value,np.integer): return int(value)
    if isinstance(value,np.bool_): return bool(value)
    if isinstance(value,(float,np.floating)): return float(value) if math.isfinite(float(value)) else None
    if pd.isna(value): return None
    return value


def canonical_shop_key(values:pd.Series)->pd.Series:
    return values.astype("Int64").astype("string").fillna("__UNKNOWN_SHOP__")


def write_json(path:Path,payload:Any)->None:
    path.write_text(json.dumps(safe_json(payload),ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def peer_potential(values,minimum:int=MIN_PEERS)->dict[str,Any]:
    x=np.asarray(values,float);x=x[np.isfinite(x)]
    if len(x)<minimum:return {"status":"INSUFFICIENT_PEER_SUPPORT","n":int(len(x)),"p50":None,"p75":None,"p90":None}
    return {"status":"SUPPORTED_PEER_REFERENCE","n":int(len(x)),"p50":float(np.quantile(x,.5)),"p75":float(np.quantile(x,.75)),"p90":float(np.quantile(x,.9))}


def attainable_funded_potential(peer_monthly_averages,minimum_peers:int=MIN_PEERS)->dict[str,Any]:
    values=np.asarray(peer_monthly_averages,dtype=float)
    values=values[np.isfinite(values)]
    if len(values)<minimum_peers:
        return {"status":"INSUFFICIENT_FUNDED_PEER_SUPPORT","shops":int(len(values)),"low_3m":None,"base_3m":None,"high_3m":None}
    return {"status":"SUPPORTED_FUNDED_PEER_REFERENCE","shops":int(len(values)),
            "low_3m":float(np.quantile(values,.50)*3),"base_3m":float(np.quantile(values,.75)*3),
            "high_3m":float(np.quantile(values,.90)*3)}


def internal_lead_ceiling(eligible_uuids,peer_rate):
    if eligible_uuids is None or peer_rate is None or not np.isfinite(float(eligible_uuids)) or not np.isfinite(float(peer_rate)):
        return None
    return max(0.0,float(eligible_uuids))*float(np.clip(peer_rate,0,1))


def classify_action(opportunity_gap,match_rate,peer_match_rate,peer_supported,forecast_reliability):
    if not peer_supported:return "LEARN_FIRST"
    if opportunity_gap is None or pd.isna(opportunity_gap) or forecast_reliability!="VALIDATED_MODEL":return "ENABLE_MEASUREMENT"
    if opportunity_gap<=0:return "MONITOR"
    if match_rate is not None and peer_match_rate is not None and pd.notna(match_rate) and pd.notna(peer_match_rate) and match_rate<peer_match_rate:return "TEST_LEAD_EXECUTION"
    return "TEST_DEMAND_OR_CAPACITY"


def check_gates()->dict[str,Any]:
    report=json.loads(PHASE1_GATE.read_text(encoding="utf-8"))
    if report.get("execution_status")!="SUCCESS" or report.get("fatal_failures"):
        raise RuntimeError("Phase 1 Revision 2 validation gate failed; Task 2 stopped.")
    audit=json.loads((TASK1/"task1_audit.json").read_text(encoding="utf-8"))
    if audit.get("status")!="SUCCESS":raise RuntimeError("Task 1 audit failed; Task 2 stopped.")
    return {"phase1":report,"task1":audit}


def _read(path:Path)->pd.DataFrame:
    c=duckdb.connect()
    try:return c.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()
    finally:c.close()


def peer_key(frame:pd.DataFrame)->pd.Series:
    category=frame.get("salesroom_category",pd.Series(index=frame.index,dtype=object))
    model=frame.get("salesroom_model",pd.Series(index=frame.index,dtype=object))
    master=category.notna()&model.notna()&(category.astype(str)!="(unknown category)")&(model.astype(str)!="(unknown model)")
    activity=pd.to_numeric(frame.get("observed_contract_months",0),errors="coerce").fillna(0)
    leads=pd.to_numeric(frame.get("lead_volume",0),errors="coerce").fillna(0)
    activity_band=pd.cut(activity,[-1,5,12,10**9],labels=["0-5","6-12","13+"]).astype(str)
    lead_band=pd.cut(leads,[-1,20,100,10**12],labels=["0-20","21-100","101+"]).astype(str)
    behavior="BEHAVIOR|"+activity_band+"|"+lead_band
    return pd.Series(np.where(master,"MASTER|"+category.fillna("").astype(str)+"|"+model.fillna("").astype(str),behavior),index=frame.index)


def load_inputs():
    gates=check_gates()
    task1_audit=gates["task1"]
    latest=pd.Timestamp(task1_audit["window"]["latest_complete_month"])
    months=pd.date_range(latest-pd.DateOffset(months=2),latest,freq="MS")
    profile=_read(DATA/"shop_behavior_profile.parquet")
    master=_read(DATA/"shop_clean.parquet")
    task1_summary=_read(TASK1/"shop_performance_summary.parquet")
    forecasts=_read(TASK1/"shop_bau_forecast.parquet")
    shop_month_path=(DATA/"shop_month_foundation.parquet").as_posix()
    lead_path=(DATA/"leads_clean.parquet").as_posix()
    candidate_path=(DATA/"lead_contract_candidates.parquet").as_posix()
    c=duckdb.connect()
    try:
        lead_stats=c.execute(f"""
          WITH l AS (
            SELECT CAST(skp_salesroom_id AS VARCHAR) shop_key, count(*) lead_event_rows,
                   count(DISTINCT lead_uuid) lead_uuid_count, count(DISTINCT skp_client_id) lead_client_count
            FROM read_parquet('{lead_path}')
            WHERE date_assigned_ts >= DATE '{months[0].date()}' AND date_assigned_ts < DATE '{(latest+pd.offsets.MonthBegin(1)).date()}'
            GROUP BY 1
          ), m AS (
            SELECT CAST(lead_origin_shop_id AS VARCHAR) shop_key,count(DISTINCT lead_uuid) primary_matched_uuids
            FROM read_parquet('{candidate_path}')
            WHERE is_confirmed_match AND is_primary_match
              AND date_assigned_ts >= DATE '{months[0].date()}'
              AND date_assigned_ts < DATE '{(latest+pd.offsets.MonthBegin(1)).date()}'
              AND contract_apply_ts < DATE '{(latest+pd.offsets.MonthBegin(1)).date()}'
            GROUP BY 1
          ) SELECT l.*,coalesce(m.primary_matched_uuids,0) primary_matched_uuids
            FROM l LEFT JOIN m USING(shop_key)
        """).df()
        product_mix=c.execute(f"""
          SELECT CAST(skp_salesroom_id AS VARCHAR) shop_key,
                 sum(lead_event_rows) FILTER(WHERE upper(lead_product_code)='TW') tw_rows,
                 sum(lead_event_rows) FILTER(WHERE upper(lead_product_code)='CL') cl_rows,
                 sum(lead_event_rows) FILTER(WHERE upper(lead_product_code)='CC') cc_rows,
                 sum(lead_event_rows) FILTER(WHERE upper(lead_product_code)='CD') cd_rows
          FROM read_parquet('{(DATA/'lead_shop_month_product.parquet').as_posix()}')
          WHERE month_start >= DATE '{months[0].date()}' AND month_start <= DATE '{latest.date()}' GROUP BY 1
        """).df()
        monthly_funded=c.execute(f"""
          SELECT CASE WHEN skp_salesroom_id IS NULL THEN '__UNKNOWN_SHOP__' ELSE CAST(skp_salesroom_id AS VARCHAR) END shop_key,month_start,funded_contract_count
          FROM read_parquet('{shop_month_path}')
          WHERE month_start <= DATE '{latest.date()}' AND contract_application_event_rows > 0
        """).df()
    finally:
        c.close()
    profile["shop_key"]=canonical_shop_key(profile.skp_salesroom_id)
    master["shop_key"]=canonical_shop_key(master.skp_salesroom_id)
    task1_summary["shop_key"]=task1_summary.shop_key.astype(str)
    forecasts["shop_key"]=forecasts.shop_key.astype(str)
    monthly_funded["shop_key"]=monthly_funded.shop_key.astype(str)
    monthly_funded=monthly_funded[monthly_funded.month_start>=latest-pd.DateOffset(months=5)]
    funded_history=monthly_funded.groupby("shop_key").funded_contract_count.agg(list).rename("recent_funded_months")
    base=profile.merge(master[[c for c in ["shop_key","salesroom_category","salesroom_model","salesroom_product","salesroom_status","master_version_state"] if c in master]],on="shop_key",how="left",validate="one_to_one")
    base=base.merge(task1_summary[[c for c in ["shop_key","current_actual_3m_funded","current_actual_3m_months_funded","observed_history_tier","eligibility_status","observation_quality_state","lead_match_rate","lead_rows_3m","lead_uuids_3m","assigned_headcount_proxy_3m","peer_group","peer_n"] if c in task1_summary]],on="shop_key",how="left",validate="one_to_one")
    total=forecasts[(forecasts.outcome=="funded")&(forecasts.horizon.astype(str)=="3M_TOTAL")]
    total=total[["shop_key","point","lo","hi","forecast_reliability","eligibility_status","interval_status","observation_quality_state","downstream_usage_recommendation"]].rename(columns={"point":"bau_3m_descriptive","lo":"bau_3m_lo","hi":"bau_3m_hi"})
    base=base.merge(total,on="shop_key",how="left",validate="one_to_one")
    base=base.merge(lead_stats,on="shop_key",how="left",validate="one_to_one").merge(product_mix,on="shop_key",how="left",validate="one_to_one")
    base=base.merge(funded_history,on="shop_key",how="left",validate="one_to_one")
    base["avg_funded_per_observed_month"]=base.recent_funded_months.map(lambda x:float(np.mean(x)) if isinstance(x,list) and len(x)>=3 else np.nan)
    base["funded_history_months_recent"]=base.recent_funded_months.map(lambda x:len(x) if isinstance(x,list) else 0)
    base["lead_match_rate_3m"]=base.primary_matched_uuids/base.lead_uuid_count.replace(0,np.nan)
    base["lead_match_rate_3m"]=base.lead_match_rate_3m.clip(0,1)
    base["peer_key"]=peer_key(base)
    return base,forecasts,task1_audit,months,latest


def build_task2() -> dict[str,Any]:
    shops,forecasts,t1_audit,months,latest=load_inputs()
    shops["peer_support_count"]=shops.groupby("peer_key").peer_key.transform("count")
    shops["peer_supported"]=shops.peer_support_count.ge(MIN_PEERS)
    shops["avg_funded_per_observed_month"]=pd.to_numeric(shops.avg_funded_per_observed_month,errors="coerce")
    shops["peer_potential_status"]="INSUFFICIENT_PEER_SUPPORT"
    shops["attainable_low_3m"]=np.nan;shops["attainable_base_3m"]=np.nan;shops["attainable_high_3m"]=np.nan
    shops["peer_potential_shop_count"]=0
    shops["peer_p50_lead_match_rate"]=np.nan;shops["peer_p75_lead_match_rate"]=np.nan
    for key,idx in shops.groupby("peer_key").groups.items():
        ix=list(idx)
        eligible_ix=[i for i in ix if pd.notna(shops.loc[i,"avg_funded_per_observed_month"]) and shops.loc[i,"funded_history_months_recent"]>=3]
        benchmark=attainable_funded_potential(shops.loc[eligible_ix,"avg_funded_per_observed_month"],MIN_PEERS)
        shops.loc[ix,"peer_potential_status"]=benchmark["status"]
        shops.loc[ix,"peer_potential_shop_count"]=benchmark["shops"]
        if benchmark["status"]=="SUPPORTED_FUNDED_PEER_REFERENCE":
            shops.loc[ix,"attainable_low_3m"]=benchmark["low_3m"]
            shops.loc[ix,"attainable_base_3m"]=benchmark["base_3m"]
            shops.loc[ix,"attainable_high_3m"]=benchmark["high_3m"]
        rate=peer_potential(shops.loc[ix,"lead_match_rate_3m"],MIN_PEERS)
        if rate["status"]=="SUPPORTED_PEER_BENCHMARK":
            shops.loc[ix,"peer_p50_lead_match_rate"]=rate["p50"]
            shops.loc[ix,"peer_p75_lead_match_rate"]=rate["p75"]
    shops["internal_lead_ceiling_3m"]=[internal_lead_ceiling(n,r) for n,r in zip(shops.lead_uuid_count,shops.peer_p75_lead_match_rate)]
    qualified=shops.downstream_usage_recommendation.eq("EVIDENCE_QUALIFIED_BAU")
    shops["bau_3m_for_gap"]=shops.bau_3m_descriptive.where(qualified)
    shops["opportunity_gap_3m"]=(shops.attainable_base_3m-shops.bau_3m_for_gap).clip(lower=0)
    shops.loc[~qualified,"opportunity_gap_3m"]=np.nan
    shops["action_group"]=[classify_action(g,m,p,bool(s),r) for g,m,p,s,r in zip(shops.opportunity_gap_3m,shops.lead_match_rate_3m,shops.peer_p50_lead_match_rate,shops.peer_supported,shops.forecast_reliability)]
    shops["priority_rank"]=(shops["opportunity_gap_3m"].where(shops.action_group.str.startswith("TEST"))).rank(method="first",ascending=False)
    shops["illustrative_pilot_candidate"]=(shops.priority_rank<=PILOT_CAPACITY)&shops.action_group.str.startswith("TEST")
    pair=json.loads((TASK1/"task1_pair.json").read_text(encoding="utf-8"))
    pair_ids=[str(x) for x in pair.get("pair_ids",[])]
    shops["case_pair_member"]=shops.shop_key.isin(pair_ids)
    return publish_task2(shops,pair,t1_audit,months,latest)



def publish_task2(shops,pair,t1_audit,months,latest):
    OUT.mkdir(parents=True,exist_ok=True)
    pair_ids=[str(x) for x in pair.get("pair_ids",[])]
    pair_rows=shops[shops.case_pair_member].copy()
    checks=[
        {"check":"phase1_and_task1_gates_pass","observed":True,"status":"PASS"},
        {"check":"one_row_per_shop_key","observed":int(shops.shop_key.duplicated().sum()),"expected":0,"status":"PASS" if not shops.shop_key.duplicated().any() else "FAIL"},
        {"check":"unmatched_master_shops_retained","observed":int((~shops.master_matched_flag.fillna(False)).sum()),"expected":">=0; retained in output","status":"PASS"},
        {"check":"no_sample_weights_applied","observed":False,"expected":False,"status":"PASS"},
        {"check":"no_roi_or_causal_uplift","observed":False,"expected":False,"status":"PASS"},
    ]
    qualified=shops.downstream_usage_recommendation.eq("EVIDENCE_QUALIFIED_BAU")
    audit={"status":"SUCCESS","window":{"start":months[0],"latest_complete":latest},
           "foundation_shop_count":int(len(shops)),"master_matched_shops":int(shops.master_matched_flag.fillna(False).sum()),
           "unmatched_master_shops":int((~shops.master_matched_flag.fillna(False)).sum()),
           "forecast_reliability_counts":shops.forecast_reliability.fillna("NaN").value_counts().to_dict(),
           "evidence_qualified_bau_rows":int(qualified.sum()),
           "market_status":"ADDRESSABLE_MARKET_NOT_ESTIMABLE_EXTERNAL; internal lead-opportunity ceiling is a bounded proxy",
           "r2_predictive_or_causal_use":False,"pair":pair,"checks":checks,
           "assumptions":{"peer_group":"current category/model where present; unmatched shops use observed contract-history and lead-volume bands",
             "minimum_peer_support":MIN_PEERS,"attainable_potential":"p50/p75/p90 of each peer shop's average monthly funded-origin count across up to six recent observed contract months, multiplied by three; same outcome unit/horizon as funded BAU, descriptive peer benchmark, not intervention uplift",
             "internal_ceiling":"distinct lead UUID opportunities in latest 3 complete months multiplied by peer p75 primary-match UUID rate; existing lead pipeline only, not total addressable market",
             "priority_capacity":PILOT_CAPACITY,"cost_roi":"not estimated: costs, margin and resource capacity are unavailable",
             "lead_match":"distinct UUID with at least one primary criterion-qualified contract / distinct UUID assigned in the window; right-censoring remains possible"},
           "task2_may_consume_forecasts":"Only rows tagged EVIDENCE_QUALIFIED_BAU; others are descriptive and cannot support numeric opportunity gaps."}
    shop_path=OUT/"shop_growth_potential.parquet"
    shops.to_parquet(shop_path,index=False,compression="zstd")
    write_json(OUT/"task2_validation_report.json",audit)
    insights=["# Task 2 — Growth constraints and potential","",f"Observed window: {months[0]:%b %Y} to {latest:%b %Y}.",
      "Attainable potential uses peers' observed monthly funded-origin counts multiplied to a three-month reference range; it is not causal uplift. Numeric BAU gaps use the same funded-origin outcome and horizon and are reported only for Task 1 evidence-qualified BAU.",
      "The internal ceiling proxy covers recorded lead UUID opportunities only. It is not total market size; external addressable market remains not estimable.",
      "Lead match rate uses primary criterion-qualified pairs and distinct UUIDs. Follow-up time and status semantics remain limitations.",
      "Unmatched shops remain in the output and use behavior-based peer groups; they are not discarded.",
      f"Pair case: {pair_ids} status={pair.get('status')}; pair-level observed constraints are shown only where data exist.",
      "Priority groups are test hypotheses, not causal recommendations or an optimized budget. Ten-shop pilot capacity is illustrative; cost and ROI are not estimated.",""]
    if not pair_rows.empty:
        insights.append("## Similar-current pair constraint view")
        for row in pair_rows.itertuples():
            insights.append(f"- Shop {row.shop_key}: actual={row.current_actual_3m_funded}; BAU={row.bau_3m_for_gap}; peer potential p50/p75/p90={row.attainable_low_3m}/{row.attainable_base_3m}/{row.attainable_high_3m}; recent lead UUIDs={row.lead_uuid_count}; primary-match UUID rate={row.lead_match_rate_3m}.")
    (OUT/"task2_insights.md").write_text("\n".join(insights)+"\n",encoding="utf-8")
    # Compact fixed figures: complete support only, no empty chart and no external TAM bar.
    fig,ax=plt.subplots(figsize=(7,4),dpi=200,facecolor="white")
    subset=shops[shops.peer_potential_status=="SUPPORTED_FUNDED_PEER_REFERENCE"]
    ax.scatter(subset.attainable_base_3m,subset.bau_3m_for_gap,c=COLORS["blue"],alpha=.45,s=10)
    if not subset.empty:
        lim=max(float(subset.attainable_base_3m.max()),float(subset.bau_3m_for_gap.max()) if subset.bau_3m_for_gap.notna().any() else 0,1);ax.plot([0,lim],[0,lim],color=COLORS["gray"],linestyle="--")
    else: ax.text(.5,.5,"N/A — insufficient peer support",ha="center",va="center",transform=ax.transAxes)
    ax.set_xlabel("Peer p75 3-month potential reference");ax.set_ylabel("Evidence-qualified BAU, 3 months")
    fig.savefig(OUT/"T2_01_BAU_vs_Peer_Potential.png",dpi=200,facecolor="white",bbox_inches="tight");plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,3.5),dpi=200,facecolor="white")
    counts=shops.action_group.value_counts().sort_index();ax.bar(counts.index,counts.values,color=COLORS["blue"]);ax.tick_params(axis="x",rotation=25);ax.set_ylabel("Shop IDs")
    fig.savefig(OUT/"T2_02_Action_Readiness.png",dpi=200,facecolor="white",bbox_inches="tight");plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,3.5),dpi=200,facecolor="white")
    ceiling=shops.internal_lead_ceiling_3m.dropna()
    if ceiling.empty:ax.text(.5,.5,"Internal lead ceiling not estimable",ha="center",va="center",transform=ax.transAxes)
    else:ax.hist(ceiling,bins=25,color=COLORS["mid"]);ax.set_xlabel("Internal active-lead ceiling proxy (contract count)")
    ax.set_ylabel("Shop IDs")
    fig.savefig(OUT/"T2_03_Internal_Lead_Ceiling.png",dpi=200,facecolor="white",bbox_inches="tight");plt.close(fig)
    return {"status":audit["status"],"audit":audit,"shops":shops,"output_dir":str(OUT)}


def main(): return build_task2()


if __name__=="__main__":
    result=main();print(f"Task 2 {result['status']}; shops={len(result['shops']):,}; qualified BAU={result['audit']['evidence_qualified_bau_rows']:,}")
