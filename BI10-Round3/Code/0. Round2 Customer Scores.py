"""Round 2 revision: evidence-based FHS/CES weights and thresholds, four action groups, and out-of-time validation on Round 3 contracts."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"Data_clean"
R2_DATA=DATA/"R2"
OUT=ROOT/"output"/"R2_Customer_Foundation"
# Round 2 score exports are read once and frozen in Data_clean/R2 so NoName3 runs without the NoName2 folder.
R2_SOURCE=Path(os.environ.get("R2_SOURCE",ROOT.parents[2]/"ROUND 02"/"NoName2"/"output"))
INPUTS=R2_DATA/"r2_score_inputs.parquet"
SNAPSHOT=pd.Timestamp("2025-06-05")          # Round 2 production score snapshot (validation_report.json)
EXTRACT_END=pd.Timestamp("2026-10-01")       # first month with no Round 3 applications
TET_WINDOW=(pd.Timestamp("2026-01-01"),pd.Timestamp("2026-02-17"))   # Tet 2026 falls on 17 Feb; pre-Tet borrowing runs through January
FORWARD_6M=SNAPSHOT+pd.DateOffset(months=6)
MATURE_SIGN_BY=pd.Timestamp("2026-05-01")    # four monthly instalments due before the extract ends
SEED=42
PILLARS=["pillar_Repayment History","pillar_Credit Standing","pillar_Debt Burden (DTI)","pillar_Down-payment Buffer","pillar_Pre-approved Capacity"]
R2_PILLAR_WEIGHTS=[0.35,0.26,0.13,0.13,0.13]
COMPONENTS=["E1_digital","E2_recency","E3_frequency","E4_responsiveness","E5_breadth"]
R2_CES_WEIGHTS=[0.20,0.20,0.25,0.20,0.15]       # NoName2 Code/config/config.py:74 (slide 10 swapped recency/frequency)
COLORS={"blue":"#004AAD","navy":"#14213d","mid":"#8FAAD1","light":"#C9D6EA","red":"#C51E1E","gray":"#6B7280","grid":"#E4E8ED","green":"#2E7D5B","amber":"#C98A1B"}
GROUP_ORDER=["GROW","RE-TIME","NURTURE","PROTECT"]
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


# %% Inputs ---------------------------------------------------------------------------------------
def freeze_round2_inputs()->pd.DataFrame:
    """Copy the Round 2 columns this stage needs into NoName3 once; later runs read the frozen file."""
    if INPUTS.exists() and INPUTS.stat().st_size>1000: return pd.read_parquet(INPUTS)
    fh=pd.read_parquet(R2_SOURCE/"Task1"/"scores"/"fh_scores.parquet",
                       columns=["SKP_CLIENT","Financial_Health_Score","fh_thin_file","fh_thin_type","n_signed","n_delinquent","n_open_delinquent",*PILLARS])
    en=pd.read_parquet(R2_SOURCE/"Task2"/"scores"/"eng_scores.parquet",
                       columns=["SKP_CLIENT","Engagement_Score",*COMPONENTS,"e4_available","days_since_last_activity","active_months_12m",
                                "out_attempts","out_connected","collection_calls","opted_out"])
    frame=fh.merge(en,on="SKP_CLIENT",how="inner",validate="one_to_one")
    if len(frame)!=len(fh) or len(frame)!=len(en): raise RuntimeError("Round 2 FHS and CES keys do not match one-to-one")
    frame=frame.rename(columns={"SKP_CLIENT":"skp_client_id","Financial_Health_Score":"fhs_r2","Engagement_Score":"ces_r2"})
    R2_DATA.mkdir(parents=True,exist_ok=True);frame.to_parquet(INPUTS,index=False,compression="zstd")
    return frame


def round3_outcomes(clients:pd.Series)->pd.DataFrame:
    """Customer-level outcomes observed only after the Round 2 snapshot, from Round 3 contracts."""
    path=(DATA/"contract_clean.parquet").as_posix()
    c=duckdb.connect()
    try:
        c.register("r2",pd.DataFrame({"skp_client_id":clients.astype("int64")}))
        out=c.execute(f"""
          WITH k AS (
            SELECT skp_client_id, date_apply_ts, is_funded, skp_salesroom_id,
                   greatest(coalesce(dpd_1pd_raw,0),coalesce(dpd_2pd_raw,0),coalesce(dpd_3pd_raw,0),coalesce(dpd_4pd_raw,0)) AS max_dpd
            FROM read_parquet('{path}')
            WHERE date_apply_ts > TIMESTAMP '{SNAPSHOT.date()}' AND date_apply_ts < TIMESTAMP '{EXTRACT_END.date()}')
          SELECT r2.skp_client_id,
                 count(k.date_apply_ts) AS r3_applications,
                 count(k.date_apply_ts) FILTER (WHERE k.date_apply_ts < TIMESTAMP '{FORWARD_6M.date()}') AS r3_applications_6m,
                 count(k.date_apply_ts) FILTER (WHERE k.is_funded) AS r3_funded,
                 count(k.date_apply_ts) FILTER (WHERE k.date_apply_ts >= TIMESTAMP '{TET_WINDOW[0].date()}' AND k.date_apply_ts < TIMESTAMP '{TET_WINDOW[1].date()}') AS r3_tet26_applications,
                 count(k.date_apply_ts) FILTER (WHERE k.is_funded AND k.date_apply_ts < TIMESTAMP '{MATURE_SIGN_BY.date()}') AS r3_mature_funded,
                 count(k.date_apply_ts) FILTER (WHERE k.is_funded AND k.date_apply_ts < TIMESTAMP '{MATURE_SIGN_BY.date()}' AND k.max_dpd > 0) AS r3_mature_late,
                 count(DISTINCT k.skp_salesroom_id) AS r3_booking_shops
          FROM r2 LEFT JOIN k USING (skp_client_id) GROUP BY 1""").df()
    finally:c.close()
    out["applied_after"]=out.r3_applications>0
    out["applied_6m"]=out.r3_applications_6m>0
    out["funded_after"]=out.r3_funded>0
    out["applied_tet26"]=out.r3_tet26_applications>0
    out["late_after"]=np.where(out.r3_mature_funded>0,out.r3_mature_late>0,np.nan)
    return out


def network_monthly_applications()->pd.DataFrame:
    """If Tet drove borrowing, the Round 3 network would show a peak before Tet 2026 as it did before Tet 2025."""
    c=duckdb.connect()
    try:return c.execute(f"""SELECT date_trunc('month',date_apply_ts) AS month_start, count(*) AS applications FROM read_parquet('{(DATA/'contract_clean.parquet').as_posix()}')
                             WHERE date_apply_ts < TIMESTAMP '{EXTRACT_END.date()}' GROUP BY 1 ORDER BY 1""").df()
    finally:c.close()


def coverage_check(clients:pd.Series)->dict[str,Any]:
    """Do Round 2 contracts from Jan–May 2025 appear in Round 3? This tests whether a missing Round 3 row means 'no application'."""
    r2_contracts=R2_SOURCE.parent/"Data_clean"/"contract_clean.parquet"
    if not r2_contracts.exists():return {"status":"UNAVAILABLE"}
    c=duckdb.connect()
    try:
        row=c.execute(f"""
          WITH a AS (SELECT DISTINCT SKP_CREDIT_CASE id FROM read_parquet('{r2_contracts.as_posix()}')
                     WHERE apply_time >= TIMESTAMP '2025-01-01' AND apply_time < TIMESTAMP '2025-06-01'),
               b AS (SELECT DISTINCT skp_credit_case_id id FROM read_parquet('{(DATA/'contract_clean.parquet').as_posix()}')
                     WHERE date_apply_ts >= TIMESTAMP '2025-01-01' AND date_apply_ts < TIMESTAMP '2025-06-01')
          SELECT (SELECT count(*) FROM a) r2_cases, (SELECT count(*) FROM a JOIN b USING(id)) found_in_r3""").fetchone()
    finally:c.close()
    return {"status":"OK","window":"2025-01-01 to 2025-05-31","r2_credit_cases":int(row[0]),"found_in_r3":int(row[1]),
            "share_found":row[1]/row[0] if row[0] else None}


# %% Weight estimation -------------------------------------------------------------------------------
def nonnegative_logit_weights(x:np.ndarray,y:np.ndarray)->np.ndarray:
    """Logistic regression with coefficients >= 0 on standardized inputs; the coefficients become relative weights."""
    mu,sd=x.mean(0),x.std(0);sd[sd==0]=1;z=(x-mu)/sd
    def loss(b):
        eta=b[0]+z@b[1:];return float(np.mean(np.logaddexp(0,eta)-y*eta))
    def grad(b):
        p=1/(1+np.exp(-(b[0]+z@b[1:])));r=p-y;return np.r_[r.mean(),(z*r[:,None]).mean(0)]
    fit=minimize(loss,np.zeros(x.shape[1]+1),jac=grad,method="L-BFGS-B",bounds=[(None,None)]+[(0,None)]*x.shape[1])
    # A unit of each raw 0–100 component moves the logit by b/sd; normalise those to weights that sum to 1.
    raw=fit.x[1:]/sd
    return raw/raw.sum() if raw.sum()>0 else np.full(x.shape[1],1/x.shape[1])


def weighted_score(x:np.ndarray,weights,available:np.ndarray|None=None)->np.ndarray:
    w=np.tile(np.asarray(weights,float),(len(x),1))
    if available is not None:w[~available]=0
    values=np.nan_to_num(x)
    return (values*w).sum(1)/np.where(w.sum(1)>0,w.sum(1),1)


def auc(y,score)->float:
    y=np.asarray(y,float);mask=np.isfinite(y)&np.isfinite(score)
    return float(roc_auc_score(y[mask],score[mask])) if len(np.unique(y[mask]))==2 else float("nan")


def ces_weight_study(frame:pd.DataFrame)->dict[str,Any]:
    """Learn CES weights on half the customers (outcome: any Round 3 application within 6 months), test on the other half."""
    train=frame.train_half.to_numpy()
    x=frame[COMPONENTS].to_numpy(float);available=~np.isnan(x);y=frame.applied_6m.to_numpy(float)
    filled=np.where(available,x,np.nanmean(x,0))
    learned=nonnegative_logit_weights(filled[train],y[train])
    candidates={"Round 2 weights":R2_CES_WEIGHTS,"Equal weights":[0.2]*5,"Learned (non-negative logit)":learned.tolist()}
    for i,name in enumerate(COMPONENTS):
        w=np.array(R2_CES_WEIGHTS,float);w[i]=0;candidates[f"Round 2 without {name.split('_',1)[1]}"]=(w/w.sum()).tolist()
    rows=[{"weights":k,**{c:round(v,3) for c,v in zip(COMPONENTS,w)},"train_auc_6m":auc(y[train],weighted_score(x[train],w,available[train])),"test_auc_6m":auc(y[~train],weighted_score(x[~train],w,available[~train])),
           "test_auc_15m":auc(frame.applied_after.to_numpy(float)[~train],weighted_score(x[~train],w,available[~train]))} for k,w in candidates.items()]
    single=[{"component":c,"test_auc_6m":auc(y[~train],np.nan_to_num(x[~train,i],nan=np.nanmean(x[:,i])))} for i,c in enumerate(COMPONENTS)]
    return {"learned":dict(zip(COMPONENTS,learned)),"comparison":pd.DataFrame(rows),"single_component":pd.DataFrame(single),"train_n":int(train.sum()),"test_n":int((~train).sum())}


def fhs_weight_study(frame:pd.DataFrame)->dict[str,Any]:
    """Out-of-time check of FHS pillar weights against late payment on Round 3 loans funded after the snapshot."""
    m=frame[frame.late_after.notna()&~frame.fh_thin_file.astype(bool)].copy()
    y=m.late_after.to_numpy(float);x=m[PILLARS].to_numpy(float)
    rng=np.random.default_rng(SEED);train=rng.random(len(m))<0.5
    # Higher pillar points mean lower risk, so learn weights on the "good" outcome.
    learned=nonnegative_logit_weights(np.nan_to_num(x[train]),1-y[train])
    candidates={"Round 2 weights":R2_PILLAR_WEIGHTS,"Equal weights":[0.2]*5,"Learned (non-negative logit)":learned.tolist()}
    for i,name in enumerate(PILLARS):
        w=np.array(R2_PILLAR_WEIGHTS,float);w[i]=0;candidates[f"Round 2 without {name.replace('pillar_','')}"]=(w/w.sum()).tolist()
    rows=[{"weights":k,**{p.replace('pillar_',''):round(v,3) for p,v in zip(PILLARS,w)},
           "test_gini":2*auc(1-y[~train],weighted_score(x[~train],w))-1} for k,w in candidates.items()]
    rows.append({"weights":"Round 2 published FHS","test_gini":2*auc(1-y[~train],m.fhs_r2.to_numpy()[~train])-1})
    return {"learned":dict(zip([p.replace('pillar_','') for p in PILLARS],learned)),"comparison":pd.DataFrame(rows),
            "customers_with_mature_loan":int(len(m)),"late_rate":float(y.mean())}


# %% Thresholds and groups -------------------------------------------------------------------------
def outcome_anchored_cuts(score:pd.Series,outcome:pd.Series,low_ratio:float=2/3,high_ratio:float=1.5)->dict[str,float]:
    """Mirror the FHS rule (cut-offs at 0.5x/1.5x average stress): CES High starts where the smoothed
    re-application rate reaches 1.5x average; Low ends where it falls to 2/3 of average (same 1.5x ratio either side)."""
    base=float(outcome.mean());bins=pd.qcut(score.rank(method="first"),50,labels=False)
    curve=pd.DataFrame({"s":score,"y":outcome,"b":bins}).groupby("b").agg(s_min=("s","min"),s_max=("s","max"),rate=("y","mean"))
    curve["rate_smooth"]=np.maximum.accumulate(curve.rate.rolling(3,center=True,min_periods=1).mean().to_numpy())
    high=curve.loc[curve.rate_smooth>=high_ratio*base,"s_min"];low=curve.loc[curve.rate_smooth<=low_ratio*base,"s_max"]
    return {"average_rate":base,"high_cut":float(high.min()) if len(high) else float("nan"),
            "low_cut":float(low.max()) if len(low) else float("nan"),"curve":curve.reset_index(drop=True)}


def assign_groups(frame:pd.DataFrame,fhs_cuts=(50,80),ces_cuts=None)->pd.DataFrame:
    f=frame.copy()
    lo,hi=ces_cuts
    f["fh_tier"]=np.select([f.fhs_r2>=fhs_cuts[1],f.fhs_r2>=fhs_cuts[0]],["High","Moderate"],"Low")
    f["ces_tier"]=np.select([f.ces_v2>=hi,f.ces_v2>=lo],["High","Medium"],"Low")
    last_active=SNAPSHOT-pd.to_timedelta(f.days_since_last_activity,unit="D")
    one_time_tet=(last_active>=pd.Timestamp("2024-12-01"))&(last_active<pd.Timestamp("2025-02-01"))&(f.active_months_12m<=1)
    f["one_time_tet"]=one_time_tet
    thin=f.fh_thin_file.astype(bool)
    healthy=f.fh_tier.isin(["High","Moderate"])
    conditions=[f.fh_tier.eq("Low")&~thin,
                healthy&f.ces_tier.eq("Low")&one_time_tet,
                (f.fh_tier.eq("High")&f.ces_tier.isin(["High","Medium"]))|(f.fh_tier.eq("Moderate")&f.ces_tier.eq("High"))]
    f["action_group"]=np.select(conditions,["PROTECT","RE-TIME","GROW"],"NURTURE")
    f["customer_profile"]=np.select(
        [f.fh_tier.eq("Low")&thin,f.action_group.eq("PROTECT"),f.action_group.eq("RE-TIME"),thin],
        ["Thin file, no signed loan","Observed repayment stress","One-time pre-Tet borrower","Thin file above Low"],"Established history")
    f["phone_suppressed"]=(f.out_attempts>=5)&(f.out_connected==0)
    f["arrears_check"]=f.collection_calls>0
    f["matrix_cell"]=f.fh_tier+" x "+f.ces_tier
    return f


GROUP_PLAYBOOK=pd.DataFrame([
    {"action_group":"GROW","who":"High health x High/Medium engagement, Moderate health x High engagement","action":"Needs-based product review after affordability check; route through the customer's last booking channel","owner":"Shop sales lead (in-shop) / telesales (online)","kpi":"Funded contracts per 100 customers within 90 days","guardrail":"Late payment on new loans vs group baseline","stop_rule":"Stop if new-loan late rate exceeds the Moderate-tier average"},
    {"action_group":"RE-TIME","who":"Healthy, low engagement, last active only in the Dec-2024/Jan-2025 Tet wave","action":"No seasonal campaign at scale: Round 3 shows only {retime} applied before Tet 2026 (GROW {grow}). Keep one opt-in message for a 10% test cell; move budget to GROW","owner":"CRM / marketing automation","kpi":"Tet-window application rate, test cell vs hold-out","guardrail":"Opt-out rate","stop_rule":"Scale only if test cell beats hold-out by >= 2 points"},
    {"action_group":"NURTURE","who":"Thin files, Moderate x Medium, other quiet customers","action":"Low-cost digital education and account-utility content; no call-centre time","owner":"Digital team","kpi":"App activity and self-initiated applications","guardrail":"Complaints and opt-outs","stop_rule":"Stop channels with opt-out > 2x average"},
    {"action_group":"PROTECT","who":"Low health with observed loan history","action":"Repayment support and new-credit suppression; SMS/app when the customer does not answer","owner":"Collections / customer care","kpi":"Roll rate from first late instalment","guardrail":"No new-credit offers to customers in arrears","stop_rule":"Escalate if roll rate does not fall within two cycles"},
])


# %% Figures -----------------------------------------------------------------------------------------
def figure_ces_weights(study:dict)->None:
    comp=study["comparison"].set_index("weights")
    keep=["Round 2 weights","Equal weights","Learned (non-negative logit)"]
    fig,(a,b)=plt.subplots(1,2,figsize=(10,3.6),dpi=200,gridspec_kw={"width_ratios":[1.3,1]})
    x=np.arange(len(COMPONENTS));width=.27
    for i,(name,color) in enumerate(zip(keep,[COLORS["gray"],COLORS["light"],COLORS["blue"]])):
        a.bar(x+(i-1)*width,comp.loc[name,COMPONENTS].to_numpy(float),width,label=name,color=color)
    single=study["single_component"].set_index("component").test_auc_6m
    for i,c in enumerate(COMPONENTS):a.text(i,-.06,f"AUC {single[c]:.2f}",ha="center",fontsize=7,color=COLORS["navy"])
    a.set_xticks(x,[c.split("_",1)[1].capitalize() for c in COMPONENTS]);a.set_ylabel("Weight");a.set_ylim(-.09,max(.6,a.get_ylim()[1]));a.legend(frameon=False,fontsize=7)
    a.axhline(0,color=COLORS["gray"],linewidth=.6)
    order=comp.sort_values("test_auc_6m").test_auc_6m
    colors=[COLORS["blue"] if n.startswith("Learned") else COLORS["gray"] if n=="Round 2 weights" else COLORS["mid"] for n in order.index]
    b.barh(order.index,order.values,color=colors);b.set_xlim(.5,max(order.max()+.02,.7));b.set_xlabel("Hold-out AUC: applies again within 6 months")
    for y,v in enumerate(order.values):b.text(v+.002,y,f"{v:.3f}",va="center",fontsize=7)
    save(fig,"R2_01_CES_Weight_Evidence.png")


def figure_ces_cuts(cuts:dict)->None:
    curve=cuts["curve"];fig,ax=plt.subplots(figsize=(7,3.4),dpi=200)
    mid=(curve.s_min+curve.s_max)/2
    ax.plot(mid,curve.rate,color=COLORS["mid"],marker="o",markersize=2.5,linewidth=1,label="Observed (50 score bins)")
    ax.plot(mid,curve.rate_smooth,color=COLORS["blue"],linewidth=1.6,label="Smoothed, monotone")
    base=cuts["average_rate"]
    for ratio,label in ((1.5,"1.5x average"),(2/3,"2/3 of average")):ax.axhline(base*ratio,color=COLORS["gray"],linestyle=":",linewidth=.8);ax.text(mid.min(),base*ratio,f" {label}",va="bottom",fontsize=7,color=COLORS["gray"])
    for value,label in ((cuts["low_cut"],"Low | Medium"),(cuts["high_cut"],"Medium | High")):
        if np.isfinite(value):ax.axvline(value,color=COLORS["red"],linewidth=1);ax.text(value,ax.get_ylim()[1]*.95,f" {label}: {value:.0f}",fontsize=7,color=COLORS["red"])
    ax.set_xlabel("Revised engagement score (CES v2)");ax.set_ylabel("Share applying again within 6 months");ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));ax.legend(frameon=False,fontsize=7,loc="lower right")
    save(fig,"R2_02_CES_Outcome_Anchored_Cutoffs.png")


def figure_fhs_weights(study:dict)->None:
    comp=study["comparison"].set_index("weights").test_gini.sort_values()
    fig,ax=plt.subplots(figsize=(7,3.4),dpi=200)
    colors=[COLORS["blue"] if n.startswith("Learned") else COLORS["navy"] if n.startswith("Round 2 weights") else COLORS["mid"] for n in comp.index]
    ax.barh(comp.index,comp.values,color=colors)
    for y,v in enumerate(comp.values):ax.text(v+.003,y,f"{v:.3f}",va="center",fontsize=7)
    ax.set_xlabel("Hold-out Gini: late payment on loans funded after the R2 snapshot")
    save(fig,"R2_03_FHS_Out_of_Time_Weight_Check.png")


def figure_group_validation(table:pd.DataFrame)->None:
    t=table.set_index("action_group").reindex(GROUP_ORDER)
    metrics=[("applied_after","Applied again (Jun-25 to Sep-26)"),("applied_tet26","Applied 1 Jan-16 Feb 2026 (pre-Tet)"),("late_after","Late on a new mature loan")]
    fig,axes=plt.subplots(1,3,figsize=(10.5,3.2),dpi=200)
    for ax,(col,label) in zip(axes,metrics):
        ax.bar(t.index,t[col],color=[GROUP_COLORS[g] for g in t.index])
        for i,v in enumerate(t[col]):ax.text(i,v,f"{v:.1%}",ha="center",va="bottom",fontsize=7)
        ax.set_xlabel(label);ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:.0%}"));ax.tick_params(axis="x",labelsize=7)
    save(fig,"R2_04_Group_Out_of_Time_Validation.png")


def figure_group_sensitivity(sens:pd.DataFrame)->None:
    piv=sens.pivot(index="scenario",columns="action_group",values="customers").reindex(columns=GROUP_ORDER)
    fig,ax=plt.subplots(figsize=(7,3),dpi=200);left=np.zeros(len(piv))
    for g in GROUP_ORDER:
        ax.barh(piv.index,piv[g],left=left,color=GROUP_COLORS[g],label=g);left+=piv[g].to_numpy()
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v/1e3:,.0f}K"));ax.set_xlabel("Customers");ax.legend(ncol=4,frameon=False,fontsize=7,loc="upper center",bbox_to_anchor=(.5,-.22))
    save(fig,"R2_05_Group_Threshold_Sensitivity.png")


# %% Pipeline ----------------------------------------------------------------------------------------
def build()->dict[str,Any]:
    OUT.mkdir(parents=True,exist_ok=True)
    frame=freeze_round2_inputs()
    frame=frame.merge(round3_outcomes(frame.skp_client_id),on="skp_client_id",how="left",validate="one_to_one")
    frame["train_half"]=np.random.default_rng(SEED).random(len(frame))<0.5
    coverage=coverage_check(frame.skp_client_id)
    ces=ces_weight_study(frame)
    # Final CES weights: best hold-out AUC summed over both horizons; the candidates are listed in R2_01.
    # Final CES weights: chosen on the TRAIN half (6-month AUC) so the hold-out stays untouched.
    comparison=ces["comparison"]
    chosen=comparison.loc[comparison.train_auc_6m.idxmax()]
    final_weights=chosen[COMPONENTS].to_numpy(float)
    x=frame[COMPONENTS].to_numpy(float)
    frame["ces_v2"]=weighted_score(x,final_weights,~np.isnan(x))
    train=frame.train_half
    cuts=outcome_anchored_cuts(frame.ces_v2[train],frame.applied_6m[train].astype(float))
    if not (np.isfinite(cuts["low_cut"]) and np.isfinite(cuts["high_cut"])): raise RuntimeError(f"CES cut-offs not identifiable: {cuts}")
    fhs=fhs_weight_study(frame)
    grouped=assign_groups(frame,ces_cuts=(cuts["low_cut"],cuts["high_cut"]))
    holdout=grouped[~grouped.train_half]
    validation=holdout.groupby("action_group").agg(customers=("skp_client_id","size"),applied_after=("applied_after","mean"),applied_6m=("applied_6m","mean"),
        funded_after=("funded_after","mean"),applied_tet26=("applied_tet26","mean"),late_after=("late_after","mean"),
        customers_with_mature_loan=("late_after","count")).reset_index()
    validation["share"]=validation.customers/len(holdout)
    # Seasonality test for RE-TIME: of customers who came back, what share came back pre-Tet (47 of ~482 days, about 10%, if flat)?
    validation["tet_share_of_returners"]=validation.applied_tet26/validation.applied_after
    tet_check=holdout.groupby(holdout.action_group.eq("RE-TIME")).applied_tet26.mean().rename({True:"RE-TIME",False:"all other"}).to_dict()
    # The Round 2 recommendation used Round 2 tiers (CES < 50), so test that exact definition too.
    r2_retime=holdout.fh_tier.isin(["High","Moderate"])&(holdout.ces_r2<50)&holdout.one_time_tet&~holdout.fh_thin_file.astype(bool)
    tet_check["R2 definition RE-TIME"]=float(holdout.loc[r2_retime,"applied_tet26"].mean());tet_check["R2 definition others"]=float(holdout.loc[~r2_retime,"applied_tet26"].mean())
    tet_check["R2 definition customers (full base)"]=int((grouped.fh_tier.isin(["High","Moderate"])&(grouped.ces_r2<50)&grouped.one_time_tet&~grouped.fh_thin_file.astype(bool)).sum())
    monthly=network_monthly_applications()
    sens=[]
    for name,fc,shift in [("Base",(50,80),0),("FHS -5",(45,75),0),("FHS +5",(55,85),0),("CES -5",(50,80),-5),("CES +5",(50,80),5)]:
        g=assign_groups(frame,fc,(cuts["low_cut"]+shift,cuts["high_cut"]+shift)).action_group.value_counts()
        sens+= [{"scenario":name,"action_group":k,"customers":int(v)} for k,v in g.items()]
    sens=pd.DataFrame(sens)
    keep=["skp_client_id","train_half","one_time_tet","fhs_r2","fh_tier","ces_r2","ces_v2","ces_tier","matrix_cell","action_group","customer_profile","fh_thin_file",
          "phone_suppressed","arrears_check","applied_after","funded_after","applied_tet26","late_after"]
    grouped[keep].to_parquet(R2_DATA/"r2_customer_groups.parquet",index=False,compression="zstd")
    figure_ces_weights(ces);figure_ces_cuts(cuts);figure_fhs_weights(fhs);figure_group_validation(validation);figure_group_sensitivity(sens)
    playbook=GROUP_PLAYBOOK.copy()
    playbook["action"]=playbook.action.str.replace("{retime}",f"{tet_check['RE-TIME']:.1%}").str.replace("{grow}",f"{validation.set_index('action_group').applied_tet26['GROW']:.1%}")
    playbook.to_csv(OUT/"r2_group_playbook.csv",index=False)
    old=pd.cut(frame.ces_r2,[-1,50,80,101],right=False,labels=["Low","Medium","High"]).astype(str)
    report={"status":"SUCCESS","snapshot":SNAPSHOT,"customers":len(grouped),"round3_coverage_of_r2_contracts":coverage,
            "ces_weights":{"round2":dict(zip(COMPONENTS,R2_CES_WEIGHTS)),"learned":ces["learned"],"final":dict(zip(COMPONENTS,final_weights)),
                           "final_rule":f"highest train-half 6-month AUC: {chosen.weights}","comparison":ces["comparison"],"single_component":ces["single_component"],
                           "train_n":ces["train_n"],"test_n":ces["test_n"],"outcome":"any Round 3 application within 6 months after snapshot"},
            "ces_cutoffs":{k:v for k,v in cuts.items() if k!="curve"},"ces_tier_counts":{"round2":old.value_counts().to_dict(),"v2":grouped.ces_tier.value_counts().to_dict()},
            "fhs_weights":{"round2":dict(zip([p.replace('pillar_','') for p in PILLARS],R2_PILLAR_WEIGHTS)),**{k:v for k,v in fhs.items()}},
            "group_validation":validation,"validation_sample":"hold-out half (weights and cut-offs fit on the other half)",
            "tet26_application_rate":tet_check,"tet26_window":TET_WINDOW,"network_monthly_applications":monthly,"threshold_sensitivity":sens,
            "limits":["Validation measures business-as-usual behaviour, not the effect of any action.",
                      "Round 3 holds about a third of the Round 2 customers' Jan-May 2025 contracts, so outcome rates are 'observed in the Round 3 shop network', not total re-borrowing; group comparisons assume this sampling does not depend on the group.",
                      "Late payment uses Round 3 dpd_1pd-dpd_4pd > 0 on loans funded before May 2026; checkpoint timing is undocumented."]}
    write_json(OUT/"r2_revision_report.json",report)
    return {"report":report,"groups":grouped}


if __name__=="__main__":
    result=build();r=result["report"]
    print(json.dumps(safe_json({k:r[k] for k in ["customers","round3_coverage_of_r2_contracts","ces_cutoffs","ces_tier_counts","tet26_application_rate"]}),indent=1))
    print(r["ces_weights"]["comparison"].to_string());print(r["fhs_weights"]["comparison"].to_string());print(r["group_validation"].to_string())
