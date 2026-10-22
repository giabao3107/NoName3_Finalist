"""Task 2-3 completion: credit leakage (lead origin vs booking shop), R2 customer mix per shop, four growth concepts,
constraint diagnosis, the similar-sales pair, and robust pilot prioritization."""
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
OUT=ROOT/"output"/"Customer_to_Shop_Growth"
WINDOW=(pd.Timestamp("2026-07-01"),pd.Timestamp("2026-10-01"))     # latest three complete months, same as Task 1
MIN_PEERS=30
MIN_LINKED=30                 # R2 customer-mix gate per shop (blueprint G6)
MIN_CURRENT=15                # shops below this have too few contracts for a stable conversion or mix
PILOT_SIZES=(10,20,50)
COLORS={"blue":"#004AAD","navy":"#14213d","mid":"#8FAAD1","light":"#C9D6EA","red":"#C51E1E","gray":"#6B7280","grid":"#E4E8ED","green":"#2E7D5B","amber":"#C98A1B"}
GROUP_COLORS={"GROW":COLORS["blue"],"RE-TIME":COLORS["amber"],"NURTURE":COLORS["mid"],"PROTECT":COLORS["red"]}
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
    if value is not None and not isinstance(value,(str,bool,int)) and pd.isna(value): return None
    return value


def write_json(path:Path,payload:Any)->None:
    path.write_text(json.dumps(safe_json(payload),ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def save(fig,name:str)->None:
    fig.savefig(OUT/name,dpi=200,facecolor="white",bbox_inches="tight");plt.close(fig)


def p(path:Path)->str:return path.as_posix()


# %% Shop facts -------------------------------------------------------------------------------------
def shop_facts(c)->pd.DataFrame:
    w0,w1=(d.date() for d in WINDOW)
    shops=c.execute(f"""
      WITH m AS (
        SELECT skp_salesroom_id shop, any_value(salesroom_category) category, any_value(salesroom_model) model,
               any_value(salesroom_province) province, any_value(salesroom_area) area,
               sum(funded_contract_count) FILTER (WHERE month_start>=DATE '{w0}' AND month_start<DATE '{w1}') current_3m,
               sum(funded_contract_count) FILTER (WHERE month_start>=DATE '2026-04-01' AND month_start<DATE '{w0}') prior_3m,
               sum(distinct_lead_uuids) FILTER (WHERE month_start>=DATE '{w0}' AND month_start<DATE '{w1}') lead_uuids_3m,
               count(*) FILTER (WHERE funded_contract_count>0) active_months
        FROM read_parquet('{p(DATA/'shop_month_foundation.parquet')}') GROUP BY 1),
      x AS (
        -- Lead-driven funded contracts by ORIGIN shop, split by where they were booked.
        SELECT lead_origin_shop_id shop,
               count(*) FILTER (WHERE is_funded AND booking_shop_id=lead_origin_shop_id) lead_funded_here,
               count(*) FILTER (WHERE is_funded AND booking_shop_id<>lead_origin_shop_id) exported_3m,
               count(DISTINCT lead_uuid) FILTER (WHERE is_funded) converted_uuids
        FROM read_parquet('{p(DATA/'lead_contract_candidates.parquet')}')
        WHERE is_primary_match AND date_assigned_ts>=TIMESTAMP '{w0}' AND date_assigned_ts<TIMESTAMP '{w1}' GROUP BY 1),
      i AS (
        SELECT booking_shop_id shop, count(*) FILTER (WHERE is_funded AND booking_shop_id<>lead_origin_shop_id) imported_3m
        FROM read_parquet('{p(DATA/'lead_contract_candidates.parquet')}')
        WHERE is_primary_match AND contract_apply_ts>=TIMESTAMP '{w0}' AND contract_apply_ts<TIMESTAMP '{w1}' GROUP BY 1)
      SELECT m.*, coalesce(x.lead_funded_here,0) lead_funded_here, coalesce(x.exported_3m,0) exported_3m,
             coalesce(x.converted_uuids,0) converted_uuids, coalesce(i.imported_3m,0) imported_3m
      FROM m LEFT JOIN x USING(shop) LEFT JOIN i USING(shop)""").df()
    shops["master"]=shops.category.notna()
    shops["peer"]=np.where(shops.master,shops.category.fillna("")+" | "+shops.model.fillna(""),"Not in shop master")
    for col in ["current_3m","prior_3m","lead_uuids_3m"]:shops[col]=shops[col].fillna(0)
    shops["origin_credited_3m"]=shops.current_3m+shops.exported_3m
    shops["exported_share"]=shops.exported_3m/shops.origin_credited_3m.replace(0,np.nan)
    shops["lead_conversion"]=(shops.converted_uuids/shops.lead_uuids_3m.replace(0,np.nan)).clip(0,1)
    shops["leads_per_contract"]=shops.lead_uuids_3m/shops.current_3m.replace(0,np.nan)
    return shops


def product_pipeline(c)->pd.DataFrame:
    """Lead UUIDs and lead-driven funded contracts by origin shop and product: CL campaign leads convert ~2%, CD point-of-sale leads ~40%,
    so conversion must be benchmarked within product."""
    w0,w1=(d.date() for d in WINDOW)
    return c.execute(f"""
      SELECT lead_origin_shop_id shop, upper(lead_product_code) product, sum(distinct_lead_uuids) leads, sum(funded_primary_matched_contracts) lead_funded
      FROM read_parquet('{p(DATA/'lead_shop_month_product.parquet')}')
      WHERE month_start>=DATE '{w0}' AND month_start<DATE '{w1}' AND lead_origin_shop_id IS NOT NULL GROUP BY 1,2""").df()


def agent_capacity(c)->pd.DataFrame:
    """Sales agents rotate across many shops, so headcount is split: each agent counts 1/(shops served) at each shop."""
    w0,w1=(d.date() for d in WINDOW)
    return c.execute(f"""
      WITH a AS (SELECT DISTINCT skp_employee_id, skp_salesroom_id shop FROM read_parquet('{p(DATA/'employee_shop_clean.parquet')}')
                 WHERE valid_from_ts<TIMESTAMP '{w1}' AND (valid_to_ts IS NULL OR valid_to_ts>=TIMESTAMP '{w0}')),
           n AS (SELECT skp_employee_id, count(*) shops_served FROM a GROUP BY 1)
      SELECT shop, count(*) assigned_agents, sum(1.0/shops_served) agent_fte, avg(shops_served) avg_shops_per_agent
      FROM a JOIN n USING(skp_employee_id) GROUP BY 1""").df()


def customer_mix(c)->pd.DataFrame:
    """R2 group mix of the customers each shop touched in Round 3 (bookings or lead origin, Jun-2025 onward); a customer counts at every shop touched."""
    groups=DATA/"R2"/"r2_customer_groups.parquet"
    return c.execute(f"""
      WITH g AS (SELECT skp_client_id, action_group FROM read_parquet('{p(groups)}')),
      t AS (SELECT DISTINCT skp_salesroom_id shop, skp_client_id FROM read_parquet('{p(DATA/'contract_clean.parquet')}') WHERE after_common_r2_cutoff
            UNION SELECT DISTINCT skp_salesroom_id, skp_client_id FROM read_parquet('{p(DATA/'leads_clean.parquet')}') WHERE after_common_r2_cutoff)
      SELECT shop, count(*) linked_customers,
             avg((action_group='GROW')::INT) grow_share, avg((action_group='PROTECT')::INT) protect_share,
             avg((action_group='RE-TIME')::INT) retime_share, avg((action_group='NURTURE')::INT) nurture_share
      FROM t JOIN g USING(skp_client_id) GROUP BY 1""").df()


def leakage_by_product(c)->pd.DataFrame:
    w0,w1=(d.date() for d in WINDOW)
    return c.execute(f"""
      SELECT CASE WHEN s.skp_salesroom_id IS NULL THEN 'Origin not in shop master' ELSE 'Physical shop (in master)' END origin_type,
             lead_product_code product, count(*) FILTER (WHERE is_funded) funded,
             avg((booking_shop_id<>lead_origin_shop_id)::INT) FILTER (WHERE is_funded) booked_elsewhere_share
      FROM read_parquet('{p(DATA/'lead_contract_candidates.parquet')}') l
      LEFT JOIN read_parquet('{p(DATA/'shop_clean.parquet')}') s ON l.lead_origin_shop_id=s.skp_salesroom_id
      WHERE is_primary_match AND date_assigned_ts>=TIMESTAMP '{w0}' AND date_assigned_ts<TIMESTAMP '{w1}' GROUP BY 1,2 ORDER BY 1,3 DESC""").df()


def cross_booking_evidence(c)->pd.DataFrame:
    """Why physical-shop CC/CL leads are recorded elsewhere: was the contract processed by the origin shop's own staff, and how fast?"""
    w0,w1=(d.date() for d in WINDOW)
    return c.execute(f"""
      WITH x AS (
        SELECT l.contract_fact_id, l.lead_origin_shop_id, l.lead_product_code product, l.booking_shop_id,
               date_diff('hour',l.date_assigned_ts,l.contract_apply_ts) AS lag_hours
        FROM read_parquet('{p(DATA/'lead_contract_candidates.parquet')}') l
        JOIN read_parquet('{p(DATA/'shop_clean.parquet')}') s ON l.lead_origin_shop_id=s.skp_salesroom_id
        WHERE l.is_primary_match AND l.is_funded AND l.lead_product_code IN ('CC','CL') AND l.booking_shop_id<>l.lead_origin_shop_id
          AND l.date_assigned_ts>=TIMESTAMP '{w0}' AND l.date_assigned_ts<TIMESTAMP '{w1}'),
      e AS (SELECT DISTINCT skp_employee_id, skp_salesroom_id FROM read_parquet('{p(DATA/'employee_shop_clean.parquet')}'))
      SELECT x.product, x.booking_shop_id IN (42902170,6282) AS central_id, count(*) contracts,
             avg((e.skp_salesroom_id IS NOT NULL)::INT) processed_by_origin_staff, avg((x.lag_hours<=24)::INT) within_24h,
             quantile_cont(x.lag_hours,.5) median_hours
      FROM x JOIN read_parquet('{p(DATA/'contract_clean.parquet')}') k USING(contract_fact_id)
      LEFT JOIN e ON e.skp_employee_id=k.skp_emp_pre_process_id AND e.skp_salesroom_id=x.lead_origin_shop_id
      GROUP BY 1,2 ORDER BY 1,2""").df()


def booking_concentration(c)->pd.DataFrame:
    w0,w1=(d.date() for d in WINDOW)
    return c.execute(f"""
      SELECT skp_salesroom_id shop, sum(funded_contract_count) funded, sum(lead_event_rows) lead_rows, any_value(salesroom_category) category
      FROM read_parquet('{p(DATA/'shop_month_foundation.parquet')}') WHERE month_start>=DATE '{w0}' AND month_start<DATE '{w1}'
      GROUP BY 1 ORDER BY funded DESC""").df()


# %% Four concepts, constraints, priorities -----------------------------------------------------------
def add_bau(shops:pd.DataFrame)->pd.DataFrame:
    f=pd.read_parquet(TASK1/"shop_bau_forecast.parquet")
    f=f[(f.outcome=="funded")&(f.horizon.astype(str)=="3M_TOTAL")][["shop_key","point","lo","hi","forecast_reliability"]]
    f["shop"]=pd.to_numeric(f.shop_key,errors="coerce").astype("Int64")
    shops=shops.merge(f.drop(columns="shop_key").rename(columns={"point":"bau_3m","lo":"bau_lo","hi":"bau_hi"}),on="shop",how="left")
    # Task 1 BAU is a trailing baseline; where it is missing, the trailing three-month actual is the same rule.
    shops["bau_3m"]=shops.bau_3m.fillna(shops.current_3m)
    return shops


MIN_PRODUCT_LEADS=20


def four_concepts(shops:pd.DataFrame,pipeline:pd.DataFrame)->pd.DataFrame:
    """Same unit everywhere: funded contracts over three months.
    Attainable = BAU + two evidenced levers at peer p50/p75/p90 (low/base/high):
      (1) lead lever: convert each product's lead pipeline at the same-peer, same-product conversion rate;
      (2) GROW lever: re-activate the shop's GROW customers at the peer rate of lead-driven funding per GROW customer.
    Internal ceiling = BAU + every lead at the peer p90 product rate + every linked GROW customer at the peer p90 activation rate."""
    s=shops.copy()
    s["grow_customers"]=(s.grow_share*s.linked_customers).fillna(0)
    s["grow_activation"]=s.lead_funded_here/s.grow_customers.replace(0,np.nan)    # observed proxy: lead-driven funded per GROW customer
    eligible=s.master&(s.current_3m>=MIN_CURRENT)
    s["peer_n"]=s[eligible].groupby("peer").shop.transform("count").reindex(s.index)
    pl=pipeline.merge(s[["shop","peer"]].assign(eligible=eligible.to_numpy()),on="shop",how="inner")
    pl["conv"]=(pl.lead_funded/pl.leads).clip(0,1)
    bench=pl[pl.eligible&pl.leads.ge(MIN_PRODUCT_LEADS)].groupby(["peer","product"]).conv.quantile([.5,.75,.9]).unstack()
    bench.columns=["q50","q75","q90"];pl=pl.merge(bench.reset_index(),on=["peer","product"],how="left")
    measurable=pl.leads.ge(MIN_PRODUCT_LEADS)
    pl["expected_p50"]=pl.leads*pl.q50
    for name,q in (("low","q50"),("base","q75"),("high","q90")):
        pl[f"lever_{name}"]=np.where(measurable,((pl[q]-pl.conv).clip(lower=0)*pl.leads).fillna(0),0)
    pl["ceiling_leads"]=(pl.leads*pl.q90).fillna(0)
    agg=pl.groupby("shop").agg(lever_leads_low=("lever_low","sum"),lever_leads_base=("lever_base","sum"),lever_leads_high=("lever_high","sum"),
                               ceiling_leads=("ceiling_leads","sum"),expected_lead_funded=("expected_p50","sum"),measured_lead_funded=("lead_funded","sum"))
    s=s.merge(agg,on="shop",how="left")
    for col in agg.columns:s[col]=s[col].fillna(0)
    # Keep every concept in "booked at this shop" units: extra lead conversions only count at the share this shop books itself
    # (cards and cash loans are often booked under a central ID). The rest is reported separately as booked elsewhere.
    own=s.lead_funded_here/(s.lead_funded_here+s.exported_3m).replace(0,np.nan)
    peer_own=own[eligible].groupby(s.peer[eligible]).median()
    s["lead_own_booking_share"]=own.fillna(s.peer.map(peer_own)).fillna(1.0)
    for name in ("low","base","high"):
        s[f"lever_leads_elsewhere_{name}"]=s[f"lever_leads_{name}"]*(1-s.lead_own_booking_share)
        s[f"lever_leads_{name}"]=s[f"lever_leads_{name}"]*s.lead_own_booking_share
    s["ceiling_leads"]=s.ceiling_leads*s.lead_own_booking_share
    s["conversion_vs_peer"]=s.measured_lead_funded/s.expected_lead_funded.replace(0,np.nan)   # 1.0 = peer median, product-mix adjusted
    for q,name in ((.5,"low"),(.75,"base"),(.9,"high")):
        act=s[eligible&s.linked_customers.ge(MIN_LINKED)].groupby("peer").grow_activation.quantile(q)
        s[f"peer_act_{name}"]=s.peer.map(act)
        grow_lever=(s[f"peer_act_{name}"]-s.grow_activation.fillna(0)).clip(lower=0)*s.grow_customers*(s.linked_customers>=MIN_LINKED)
        s[f"lever_grow_{name}"]=grow_lever.fillna(0)
        s[f"attainable_{name}"]=s.bau_3m+s[f"lever_leads_{name}"]+s[f"lever_grow_{name}"]
    s["ceiling_internal"]=s.bau_3m+s.ceiling_leads+s.grow_customers*s.peer_act_high.fillna(0)*(s.linked_customers>=MIN_LINKED)
    s["gap_base"]=s.attainable_base-s.bau_3m
    s["gap_low"]=s.attainable_low-s.bau_3m
    s["gap_high"]=s.attainable_high-s.bau_3m
    s.loc[~eligible|s.peer_n.lt(MIN_PEERS),["attainable_low","attainable_base","attainable_high","ceiling_internal","gap_low","gap_base","gap_high"]]=np.nan
    return s


def diagnose(s:pd.DataFrame)->pd.DataFrame:
    """Primary constraint vs peer median; observed signals, not causes."""
    d=s.copy();e=d.attainable_base.notna()
    med=lambda col:d[e].groupby("peer")[col].transform("median").reindex(d.index)
    network_protect=float(d.loc[e&d.linked_customers.ge(MIN_LINKED),"protect_share"].median())
    conditions=[
        e&d.linked_customers.ge(MIN_LINKED)&(d.protect_share>=2*network_protect),
        e&(d.lead_uuids_3m>=med("lead_uuids_3m"))&(d.conversion_vs_peer<0.8),
        e&(d.lead_uuids_3m<med("lead_uuids_3m"))&(d.grow_share>=med("grow_share")),
        e&(d.lead_uuids_3m<med("lead_uuids_3m")),
    ]
    labels=["QUALITY: high PROTECT share","EXECUTION: leads convert below peers",
            "UNTAPPED BASE: warm customers, thin pipeline","DEMAND: thin pipeline"]
    d["primary_constraint"]=np.select(conditions,labels,"NO CLEAR GAP")
    d.loc[~e,"primary_constraint"]="NOT ASSESSED (small or no peer)"
    d["network_protect_median"]=network_protect
    # Credit leakage is an attribution problem, not a growth constraint: flag it separately (handled network-wide by recommendation 2).
    d["credit_leakage_flag"]=e&(d.exported_share>=0.2)&(d.exported_3m>=5)
    return d


def prioritize(d:pd.DataFrame)->pd.DataFrame:
    """Rank on base opportunity; quality-flagged shops are held out of growth pilots. Robustness = rank under low/high."""
    r=d.copy();e=r.gap_base.notna()&~r.primary_constraint.str.startswith("QUALITY")
    for name in ("low","base","high"):r[f"rank_{name}"]=r[f"gap_{name}"].where(e).rank(ascending=False,method="first")
    r["confidence"]=np.select([r.current_3m.ge(60)&r.linked_customers.ge(100),r.current_3m.ge(30)],["High","Medium"],"Low")
    r["action"]=np.select(
        [r.primary_constraint.str.startswith("QUALITY"),r.primary_constraint.str.startswith("EXECUTION"),
         r.primary_constraint.str.startswith("UNTAPPED"),r.primary_constraint.str.startswith("DEMAND")],
        ["PROTECT FIRST: no volume push","TEST: lead follow-up SLA","TEST: warm-base reactivation","LEARN: demand test"],"MONITOR")
    r.loc[r.gap_base.isna(),"action"]="NOT ASSESSED"
    return r


def choose_pair(r:pd.DataFrame)->tuple[pd.Series,pd.Series,dict]:
    """Two same-peer shops with near-identical current funded contracts and the largest difference in base opportunity."""
    c=r[r.gap_base.notna()&r.current_3m.ge(30)&r.linked_customers.ge(MIN_LINKED)].sort_values("current_3m")
    best=None
    for peer,g in c.groupby("peer"):
        g=g.reset_index(drop=True)
        for i in range(len(g)):
            j=g[(g.current_3m-g.loc[i,"current_3m"]).abs()<=0.05*g.loc[i,"current_3m"]]
            if len(j)<2:continue
            # Shop A must carry the diagnosed execution gap; shop B is a same-size shop without one.
            a=j[j.primary_constraint.str.startswith("EXECUTION")];b=j[~j.primary_constraint.str.startswith(("EXECUTION","QUALITY"))]
            if a.empty or b.empty:continue
            hi,lo=a.loc[a.gap_base.idxmax()],b.loc[b.gap_base.idxmin()]
            spread=hi.gap_base-lo.gap_base
            if best is None or spread>best[2]:best=(hi,lo,spread,peer)
    if best is None:raise RuntimeError("No similar-sales pair found")
    hi,lo,spread,peer=best
    return hi,lo,{"peer":peer,"rule":"same category|model, current funded 3M within 5%, current>=30, linked R2 customers>=30; A has the EXECUTION constraint, B has none; largest base-gap difference","gap_spread":spread}


# %% Figures -----------------------------------------------------------------------------------------
def fig_leakage(conc:pd.DataFrame,prod:pd.DataFrame)->None:
    fig,(a,b)=plt.subplots(1,2,figsize=(10.5,3.6),dpi=200,gridspec_kw={"width_ratios":[1,1.2]})
    total=conc.funded.sum();top=conc.head(3)
    labels=[f"Shop {int(s)}" for s in top.shop]+["Other 32.5K shop IDs"]
    values=list(top.funded)+[total-top.funded.sum()]
    a.barh(labels[::-1],values[::-1],color=[COLORS["light"]]+[COLORS["navy"]]*3)
    for y,v in enumerate(values[::-1]):a.text(v,y,f" {v/total:.0%}",va="center",fontsize=7)
    a.set_xlabel("Funded contracts, Jul-Sep 2026");a.xaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v/1e3:,.0f}K"))
    phys=prod[prod.origin_type.str.startswith("Physical")].set_index("product")
    b.bar(phys.index,phys.booked_elsewhere_share,color=[COLORS["red"] if v>.5 else COLORS["blue"] for v in phys.booked_elsewhere_share])
    for i,(v,n) in enumerate(zip(phys.booked_elsewhere_share,phys.funded)):b.text(i,v,f"{v:.0%}\n(n={n:,})",ha="center",va="bottom",fontsize=7)
    b.set_ylim(0,1.15);b.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));b.set_xlabel("Lead product generated by a physical shop: share funded at another shop")
    save(fig,"R3_01_Credit_Leakage.png")


def fig_mix(r:pd.DataFrame)->None:
    m=r[r.master&r.linked_customers.ge(MIN_LINKED)&r.current_3m.ge(MIN_CURRENT)].copy()
    m["size_band"]=pd.qcut(m.current_3m,4,labels=["Q1 smallest","Q2","Q3","Q4 largest"])
    fig,(a,b)=plt.subplots(1,2,figsize=(10.5,3.6),dpi=200)
    for band,g in m.groupby("size_band",observed=True):
        a.scatter(np.full(len(g),list(m.size_band.cat.categories).index(band))+np.random.default_rng(1).uniform(-.25,.25,len(g)),g.grow_share,s=3,alpha=.35,color=COLORS["blue"])
    q=m.groupby("size_band",observed=True).grow_share.quantile([.1,.5,.9]).unstack()
    a.plot(range(4),q[.5],color=COLORS["navy"],marker="o",label="Median");a.fill_between(range(4),q[.1],q[.9],color=COLORS["light"],alpha=.5,label="P10-P90")
    a.set_xticks(range(4),m.size_band.cat.categories);a.set_ylabel("GROW share of linked R2 customers");a.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));a.legend(frameon=False,fontsize=7)
    a.set_xlabel("Shop size: current funded contracts (quartile)")
    m["grow_q"]=pd.qcut(m.grow_share,5,labels=False,duplicates="drop")
    growth=m.groupby("grow_q").apply(lambda g:(g.current_3m.sum()-g.prior_3m.sum())/max(g.prior_3m.sum(),1),include_groups=False)
    b.bar(range(len(growth)),growth.values,color=[COLORS["blue"] if v>=0 else COLORS["red"] for v in growth.values])
    for i,v in enumerate(growth.values):b.text(i,v,f"{v:+.1%}",ha="center",va="bottom" if v>=0 else "top",fontsize=7)
    b.set_xticks(range(len(growth)),[f"Q{i+1}" for i in range(len(growth))]);b.set_xlabel("GROW-share quintile (Q5 = most GROW customers)")
    b.set_ylabel("Funded growth, Jul-Sep vs Apr-Jun 2026");b.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));b.axhline(0,color=COLORS["gray"],linewidth=.6)
    save(fig,"R3_02_Customer_Mix_Same_Size.png")


def fig_pair(hi:pd.Series,lo:pd.Series,monthly:pd.DataFrame)->None:
    fig,(a,b)=plt.subplots(1,2,figsize=(11,3.8),dpi=200,gridspec_kw={"width_ratios":[1.25,1]})
    for row,color,tag in ((hi,COLORS["blue"],"A"),(lo,COLORS["gray"],"B")):
        t=monthly[monthly.shop==row.shop].sort_values("month_start")
        a.plot(t.month_start,t.funded_contract_count,color=color,marker="o",markersize=2.5,label=f"Shop {tag} ({int(row.shop)})")
    a.set_ylabel("Funded contracts per month");a.legend(frameon=False,fontsize=7);a.tick_params(axis="x",rotation=30)
    concepts=["current_3m","bau_3m","attainable_base","ceiling_internal"];names=["Current\nactual","BAU","Attainable\n(peer p75)","Internal\nceiling"]
    x=np.arange(4);w=.38
    for k,(row,color,tag) in enumerate(((hi,COLORS["blue"],"A"),(lo,COLORS["gray"],"B"))):
        vals=[row[c] for c in concepts];b.bar(x+(k-.5)*w,vals,w,color=color,label=f"Shop {tag}")
        b.errorbar(x[2]+(k-.5)*w,row.attainable_base,yerr=[[row.attainable_base-row.attainable_low],[row.attainable_high-row.attainable_base]],color=COLORS["navy"],capsize=3,linewidth=.8)
        for xi,v in zip(x+(k-.5)*w,vals):b.text(xi,v,f"{v:.0f}",ha="center",va="bottom",fontsize=7)
    b.set_xticks(x,names);b.set_ylabel("Funded contracts, 3 months");b.legend(frameon=False,fontsize=7)
    save(fig,"R3_03_Pair_Four_Concepts.png")


def fig_constraints(r:pd.DataFrame)->None:
    t=r[r.gap_base.notna()].groupby("primary_constraint").agg(shops=("shop","size"),gap=("gap_base","sum"),gap_low=("gap_low","sum"),gap_high=("gap_high","sum")).sort_values("gap")
    fig,(a,b)=plt.subplots(1,2,figsize=(10.5,3.4),dpi=200,sharey=True)
    a.barh(t.index,t.shops,color=COLORS["mid"]);a.set_xlabel("Shops")
    for y,v in enumerate(t.shops):a.text(v,y,f" {v:,}",va="center",fontsize=7)
    b.barh(t.index,t.gap,color=COLORS["blue"],xerr=[t.gap-t.gap_low,t.gap_high-t.gap],error_kw={"ecolor":COLORS["navy"],"capsize":2,"linewidth":.7})
    b.set_xlabel("Opportunity above BAU, funded contracts / 3 months (bar p75, whisker p50-p90)")
    save(fig,"R3_04_Constraint_Map.png")


def fig_priority(r:pd.DataFrame,robust:pd.DataFrame)->None:
    fig,(a,b)=plt.subplots(1,2,figsize=(10.5,3.6),dpi=200)
    e=r[r.gap_base.notna()]
    for action,g in e.groupby("action"):
        a.scatter(g.current_3m,g.gap_base,s=6,alpha=.5,label=action)
    a.set_xscale("log");a.set_xlabel("Current funded contracts, 3 months (log)");a.set_ylabel("Base opportunity above BAU");a.legend(frameon=False,fontsize=6,markerscale=2)
    b.plot(robust.pilot_size,robust.overlap_low,marker="o",color=COLORS["gray"],label="Same shops under p50 benchmark")
    b.plot(robust.pilot_size,robust.overlap_high,marker="o",color=COLORS["blue"],label="Same shops under p90 benchmark")
    for _,row in robust.iterrows():b.text(row.pilot_size,row.overlap_high,f" {row.overlap_high:.0%}",fontsize=7,va="bottom")
    b.set_ylim(0,1.05);b.set_xlabel("Pilot size (shops)");b.set_ylabel("Share of base-case shortlist kept");b.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));b.legend(frameon=False,fontsize=7)
    save(fig,"R3_05_Priority_and_Robustness.png")


def fig_capacity(r:pd.DataFrame)->None:
    m=r[r.master&r.current_3m.ge(MIN_CURRENT)&r.agent_fte.notna()].copy()
    m["per_fte"]=m.current_3m/m.agent_fte.replace(0,np.nan)
    fig,(a,b)=plt.subplots(1,2,figsize=(10.5,3.4),dpi=200)
    g=m.groupby("model").agg(agents=("assigned_agents","median"),fte=("agent_fte","median"),shops_per_agent=("avg_shops_per_agent","median"))
    x=np.arange(len(g));a.bar(x-.2,g.agents,.4,color=COLORS["mid"],label="Assigned agents (headcount)");a.bar(x+.2,g.fte,.4,color=COLORS["blue"],label="Agent FTE (1 / shops served)")
    for i,(n,f,s) in enumerate(zip(g.agents,g.fte,g.shops_per_agent)):a.text(i,max(n,f),f"each agent serves {s:.0f} shops",ha="center",va="bottom",fontsize=7)
    a.set_xticks(x,g.index);a.set_ylabel("Median per shop");a.legend(frameon=False,fontsize=7)
    for model,color in zip(g.index,[COLORS["amber"],COLORS["blue"]]):
        t=m[m.model==model];b.scatter(t.agent_fte,t.current_3m,s=4,alpha=.35,color=color,label=model)
    b.set_xscale("log");b.set_yscale("log");b.set_xlabel("Agent FTE at shop (log)");b.set_ylabel("Funded contracts, 3 months (log)");b.legend(frameon=False,fontsize=7)
    save(fig,"R3_06_Agent_Time_Share.png")


def fig_network_concepts(r:pd.DataFrame)->None:
    e=r[r.gap_base.notna()]
    vals=[e.current_3m.sum(),e.bau_3m.sum(),e.attainable_base.sum(),e.ceiling_internal.sum()]
    names=["Current actual","BAU","Attainable (peer p75)","Internal ceiling"]
    fig,ax=plt.subplots(figsize=(7,3.2),dpi=200)
    ax.bar(names,vals,color=[COLORS["gray"],COLORS["mid"],COLORS["blue"],COLORS["navy"]])
    ax.errorbar(2,vals[2],yerr=[[vals[2]-e.attainable_low.sum()],[e.attainable_high.sum()-vals[2]]],color=COLORS["red"],capsize=4,linewidth=1)
    for i,v in enumerate(vals):ax.text(i,v,f"{v/1e3:,.1f}K",ha="center",va="bottom",fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v/1e3:,.0f}K"));ax.set_ylabel("Funded contracts recorded at shop, 3 months")
    save(fig,"R3_07_Network_Four_Concepts.png")


# %% Pipeline ----------------------------------------------------------------------------------------
def build()->dict[str,Any]:
    OUT.mkdir(parents=True,exist_ok=True)
    c=duckdb.connect()
    try:
        shops=shop_facts(c);pipeline=product_pipeline(c);cap=agent_capacity(c);mix=customer_mix(c);prod=leakage_by_product(c);cross=cross_booking_evidence(c);conc=booking_concentration(c)
        monthly=c.execute(f"SELECT skp_salesroom_id shop, month_start, funded_contract_count FROM read_parquet('{p(DATA/'shop_month_foundation.parquet')}') WHERE month_start<DATE '{WINDOW[1].date()}'").df()
    finally:c.close()
    shops=shops.merge(cap,on="shop",how="left").merge(mix,on="shop",how="left")
    shops["linked_customers"]=shops.linked_customers.fillna(0)
    shops=add_bau(shops);shops=four_concepts(shops,pipeline);shops=diagnose(shops);ranked=prioritize(shops)
    robust=[]
    for n in PILOT_SIZES:
        base=set(ranked.loc[ranked.rank_base<=n,"shop"])
        robust.append({"pilot_size":n,"overlap_low":len(base&set(ranked.loc[ranked.rank_low<=n,"shop"]))/n,"overlap_high":len(base&set(ranked.loc[ranked.rank_high<=n,"shop"]))/n})
    robust=pd.DataFrame(robust)
    hi,lo,pair_meta=choose_pair(ranked)
    fig_leakage(conc,prod);fig_mix(ranked);fig_pair(hi,lo,monthly);fig_constraints(ranked);fig_priority(ranked,robust);fig_capacity(ranked);fig_network_concepts(ranked)
    ranked.to_parquet(OUT/"shop_growth_priority.parquet",index=False,compression="zstd")
    shortlist=ranked[ranked.rank_base<=max(PILOT_SIZES)].sort_values("rank_base")[["rank_base","shop","peer","province","current_3m","bau_3m","attainable_low","attainable_base","attainable_high",
        "ceiling_internal","gap_base","primary_constraint","action","confidence","lead_conversion","conversion_vs_peer","exported_share","credit_leakage_flag","grow_share","protect_share","linked_customers","rank_low","rank_high"]]
    shortlist.to_csv(OUT/"pilot_shortlist_top50.csv",index=False)
    e=ranked.gap_base.notna()
    phys_cl=prod[prod.origin_type.str.startswith("Physical")&prod["product"].eq("CL")]
    report={"status":"SUCCESS","window":WINDOW,
        "network":{"shop_ids":int(len(ranked)),"funded_3m":float(ranked.current_3m.sum()),"top3_booking_share":float(conc.head(3).funded.sum()/conc.funded.sum()),
                   "master_shops":int(ranked.master.sum()),"assessed_shops":int(e.sum())},
        "leakage":{"by_product":prod,"cross_booking_evidence":cross,"physical_cl_booked_elsewhere":float(phys_cl.booked_elsewhere_share.iloc[0]) if len(phys_cl) else None,
                   "exported_3m_master":float(ranked.loc[ranked.master,"exported_3m"].sum()),"current_3m_master":float(ranked.loc[ranked.master,"current_3m"].sum())},
        "four_concepts_assessed":{k:float(ranked.loc[e,k].sum()) for k in ["current_3m","bau_3m","attainable_low","attainable_base","attainable_high","ceiling_internal"]},
        "levers_base":{"leads_booked_here":float(ranked.loc[e,"lever_leads_base"].sum()),"leads_booked_elsewhere":float(ranked.loc[e,"lever_leads_elsewhere_base"].sum()),"grow":float(ranked.loc[e,"lever_grow_base"].sum())},
        "assessed_share_of_network_funded":float(ranked.loc[e,"current_3m"].sum()/ranked.current_3m.sum()),
        "credit_leakage_flag_shops":int(ranked.credit_leakage_flag.sum()),
        "top20_execution":ranked[ranked.action.eq("TEST: lead follow-up SLA")].nlargest(20,"gap_base")[["gap_low","gap_base","gap_high","current_3m"]].sum(),
        "top_n_all":{n:ranked[ranked.rank_base<=n][["gap_low","gap_base","gap_high"]].sum() for n in PILOT_SIZES},
        "constraints":ranked[e].groupby("primary_constraint").agg(shops=("shop","size"),gap_base=("gap_base","sum")).reset_index(),
        "actions":ranked[e].action.value_counts(),"robustness":robust,
        "pair":{"meta":pair_meta,"A":hi[["shop","peer","province","current_3m","bau_3m","attainable_low","attainable_base","attainable_high","ceiling_internal","lead_uuids_3m","lead_conversion","conversion_vs_peer","exported_share","grow_share","protect_share","linked_customers","agent_fte","primary_constraint","action"]],
                "B":lo[["shop","peer","province","current_3m","bau_3m","attainable_low","attainable_base","attainable_high","ceiling_internal","lead_uuids_3m","lead_conversion","conversion_vs_peer","exported_share","grow_share","protect_share","linked_customers","agent_fte","primary_constraint","action"]]},
        "capacity":ranked[ranked.master&ranked.current_3m.ge(MIN_CURRENT)].groupby("model").agg(agents=("assigned_agents","median"),fte=("agent_fte","median"),shops_per_agent=("avg_shops_per_agent","median"),current=("current_3m","median")).reset_index(),
        "assumptions":{"unit":"funded contracts, three months","bau":"Task 1 trailing baseline (descriptive)","attainable":"BAU + lead lever + GROW lever at peer p50/p75/p90 (low/base/high)",
                       "ceiling":"internal serviceable proxy, not external market size","peer":"category|model in shop master, >=30 shops with >=15 funded contracts",
                       "customer_mix":f"R2 groups of customers touching the shop after 2025-06-05; shown only with >={MIN_LINKED} linked customers",
                       "causality":"levers are peer-benchmark scenarios to be tested, not causal uplift"}}
    write_json(OUT/"customer_to_shop_report.json",report)
    return {"report":report,"ranked":ranked}


if __name__=="__main__":
    r=build()["report"]
    print(json.dumps(safe_json({k:r[k] for k in ["network","four_concepts_assessed","levers_base","pair"]}),indent=1)[:5000])
    print(r["leakage"]["by_product"].to_string());print(r["constraints"].to_string());print(r["robustness"].to_string());print(r["capacity"].to_string())
