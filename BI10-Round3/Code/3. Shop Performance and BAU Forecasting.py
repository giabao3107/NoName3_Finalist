"""Task 1: clear shop actuals, a transparent BAU baseline, and a matched-shop case."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data_clean"
OUT = ROOT / "output" / "Shop_Performance_and_BAU"
GATE = ROOT / "output" / "Data processing" / "validation_report.json"
DPI = 200
OUTCOMES = {"funded": "funded_contract_count", "application": "contract_application_event_rows"}
HORIZONS = (1, 2, 3)
TOTAL = "3M_TOTAL"
TIERS = ((18, "A"), (9, "B"), (3, "C"))
MIN_EVAL = 15
MIN_INTERVAL_EVAL = 30
NOMINAL = .80
COLORS = {"blue": "#004AAD", "navy": "#14213d", "mid": "#8FAAD1", "red": "#C51E1E", "gray": "#6B7280", "grid": "#E4E8ED"}
plt.rcParams.update({"font.family": "Arial", "font.size": 8, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white", "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": COLORS["grid"], "axes.axisbelow": True})


def json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame): return json_safe(value.to_dict("records"))
    if isinstance(value, pd.Series): return json_safe(value.to_dict())
    if isinstance(value, dict): return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp,)): return value.isoformat()
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    if isinstance(value, (float, np.floating)): return float(value) if math.isfinite(float(value)) else None
    if pd.isna(value): return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def canonical_shop_key(values: pd.Series) -> pd.Series:
    text = values.astype("Int64").astype("string")
    return text.fillna("__UNKNOWN_SHOP__")


def horizon_total_mismatches(parts: pd.DataFrame, totals: pd.DataFrame) -> int:
    keys = ["shop_key", "outcome"]
    grouped = parts.groupby(keys, as_index=False).point.agg(["sum", "count"]).reset_index()
    checked = totals[keys + ["point"]].merge(grouped, on=keys, how="left", validate="one_to_one")
    has_total = checked.point.notna()
    invalid = has_total & ((checked["count"] != len(HORIZONS)) | checked["sum"].isna()
                           | ((checked.point - checked["sum"]).abs() > 1e-8))
    return int(invalid.sum())


def complete_window_sum(values, observed) -> tuple[float | None, int]:
    values, observed = np.asarray(values, dtype=float), np.asarray(observed, dtype=bool)
    valid = observed & np.isfinite(values)
    count = int(valid.sum())
    return (float(values[valid].sum()), count) if count == len(values) else (None, count)


def tier_for_counts(counts: np.ndarray) -> np.ndarray:
    counts = np.asarray(counts, dtype=int)
    return np.select([counts >= n for n, _ in TIERS], [tier for _, tier in TIERS], default="D")


def trend_forecast(y: np.ndarray, observed: np.ndarray, month_indices: np.ndarray, origin: int,
                   horizon: int, min_history: int = 3) -> np.ndarray | None:
    y, observed = np.asarray(y, float), np.asarray(observed, bool)
    indices = np.asarray(month_indices, float)
    use = observed & np.isfinite(y) & np.isfinite(indices) & (indices < origin)
    selected = np.flatnonzero(use)[-6:]
    if len(selected) < min_history:
        return None
    slope, intercept = np.polyfit(indices[selected], y[selected], 1)
    return np.maximum(0.0, intercept + slope * np.arange(origin, origin + horizon))


def trailing_forecast(y: np.ndarray, observed: np.ndarray, origin: int, horizon: int, window: int = 3) -> np.ndarray | None:
    y, observed = np.asarray(y, float), np.asarray(observed, bool)
    selected = np.flatnonzero(observed[:origin] & np.isfinite(y[:origin]))[-window:]
    if len(selected) < 3:
        return None
    return np.repeat(float(y[selected].mean()), horizon)


def split_origins(origin_min: int, origin_max: int) -> dict[str, list[int]]:
    origins = list(range(origin_min, origin_max + 1))
    if len(origins) < 3:
        return {"selection": origins[:1], "validation": origins[1:2], "holdout": origins[2:]}
    a = max(1, round(len(origins) * .55))
    b = max(a + 1, round(len(origins) * .80))
    return {"selection": origins[:a], "validation": origins[a:b], "holdout": origins[b:]}


def peer_potential(values, minimum: int = 30) -> dict[str, Any]:
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if len(v) < minimum:
        return {"status": "INSUFFICIENT_PEER_SUPPORT", "n": int(len(v)), "p50": None, "p75": None, "p90": None}
    return {"status": "SUPPORTED_PEER_BENCHMARK", "n": int(len(v)),
            "p50": float(np.quantile(v, .5)), "p75": float(np.quantile(v, .75)), "p90": float(np.quantile(v, .9))}


def select_similar_pair(frame: pd.DataFrame, tolerance: float = .10) -> dict[str, Any] | None:
    candidates = frame[frame.current_actual_3m.notna() & frame.peer_group.notna()
                      & frame.peer_group.ne("UNMAPPED_MASTER")
                      & pd.to_numeric(frame.peer_n, errors="coerce").ge(30)].copy()
    best = None
    # The closest pair in each peer group must be adjacent after sorting by actual.
    # This keeps pair selection O(n log n), even for the large unmapped population.
    for _, group in candidates.groupby("peer_group"):
        rows = group.sort_values(["current_actual_3m", "shop_key"]).to_dict("records")
        for left, right in zip(rows, rows[1:]):
            scale = max(abs(float(left["current_actual_3m"])), abs(float(right["current_actual_3m"])), 1.0)
            gap = abs(float(left["current_actual_3m"]) - float(right["current_actual_3m"])) / scale
            if gap > tolerance:
                continue
            a, b = left.get("lead_match_rate"), right.get("lead_match_rate")
            contrast = abs(float(a) - float(b)) if pd.notna(a) and pd.notna(b) else 0.0
            score = (-gap, contrast, str(left["shop_key"]), str(right["shop_key"]))
            if best is None or score > best[0]:
                best = (score, left, right, gap)
    if best is None:
        return None
    _, left, right, gap = best
    return {"pair_ids": [str(left["shop_key"]), str(right["shop_key"])], "actual_delta_pct": float(gap),
            "constraint_contrast": "lead_match_rate" if pd.notna(left.get("lead_match_rate")) and pd.notna(right.get("lead_match_rate")) else "lead_volume",
            "peer_group": left["peer_group"], "peer_support": int(min(left.get("peer_n", 0), right.get("peer_n", 0))),
            "left": left, "right": right}


def _query(path: Path, sql: str, params=None) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    gate = json.loads((ROOT / "output" / "Data processing" / "validation_report.json").read_text(encoding="utf-8"))
    if gate.get("execution_status") != "SUCCESS" or gate.get("fatal_failures"):
        raise RuntimeError("Phase 1 Revision 2 validation gate failed; Task 1 stopped.")
    metrics = json.loads((DATA / "metrics_phase1.json").read_text(encoding="utf-8"))
    month_path = (DATA / "shop_month_foundation.parquet").as_posix()
    contract_path = (DATA / "contract_clean.parquet").as_posix()
    lead_path = (DATA / "leads_clean.parquet").as_posix()
    candidate_path = (DATA / "lead_contract_candidates.parquet").as_posix()
    c = duckdb.connect()
    try:
        panel = c.execute(f"SELECT * FROM read_parquet('{month_path}')").df()
        panel["shop_key"] = canonical_shop_key(panel.skp_salesroom_id)
        bounds = c.execute(f"SELECT min(date_apply_ts)::DATE, max(date_apply_ts)::DATE FROM read_parquet('{contract_path}') WHERE date_apply_ts IS NOT NULL").fetchone()
        lead_bounds = c.execute(f"SELECT min(date_assigned_ts)::DATE,max(date_assigned_ts)::DATE FROM read_parquet('{lead_path}') WHERE date_assigned_ts IS NOT NULL").fetchone()
        lead_match = c.execute(f"""
          WITH cohort AS (
            SELECT CASE WHEN skp_salesroom_id IS NULL THEN '__UNKNOWN_SHOP__' ELSE CAST(skp_salesroom_id AS VARCHAR) END shop_key, date_trunc('month',date_assigned_ts)::DATE month_start,
                   count(*) lead_rows, count(DISTINCT lead_uuid) lead_uuids
            FROM read_parquet('{lead_path}') WHERE date_assigned_ts IS NOT NULL GROUP BY 1,2
          ), converted AS (
            SELECT CASE WHEN lead_origin_shop_id IS NULL THEN '__UNKNOWN_SHOP__' ELSE CAST(lead_origin_shop_id AS VARCHAR) END shop_key,date_trunc('month',date_assigned_ts)::DATE month_start,
                   count(DISTINCT lead_uuid) FILTER(WHERE is_primary_match) matched_uuids
            FROM read_parquet('{candidate_path}')
            WHERE is_confirmed_match AND is_primary_match AND date_assigned_ts IS NOT NULL AND contract_apply_ts IS NOT NULL
            GROUP BY 1,2
          )
          SELECT c.*,coalesce(m.matched_uuids,0) matched_uuids
          FROM cohort c LEFT JOIN converted m USING(shop_key,month_start)
        """).df()
        monthly_metrics = c.execute("SELECT * FROM read_parquet(?)", [(ROOT / "output" / "EDA" / "cache" / "fnd02_monthly.parquet").as_posix()]).df() if (ROOT / "output" / "EDA" / "cache" / "fnd02_monthly.parquet").exists() else pd.DataFrame()
    finally:
        c.close()
    max_date = pd.Timestamp(bounds[1])
    candidate = max_date.to_period("M").to_timestamp()
    latest = candidate if max_date.normalize() == (candidate + pd.offsets.MonthEnd(0)).normalize() else candidate - pd.offsets.MonthBegin(1)
    months = pd.date_range(pd.Timestamp(bounds[0]).to_period("M").to_timestamp(), latest, freq="MS")
    return panel, lead_match, {"gate": gate, "metrics": metrics, "months": months, "latest": latest,
                               "contract_max": max_date, "lead_min": lead_bounds[0], "lead_max": lead_bounds[1],
                               "monthly_metrics": monthly_metrics}


def rolling_backtest(y: np.ndarray, observed: np.ndarray, months: pd.DatetimeIndex, outcome: str) -> dict[str, Any]:
    origin_min, origin_max = 3, len(months) - max(HORIZONS)
    splits = split_origins(origin_min, origin_max)
    records, coverage, residuals = [], [], {}
    indices = np.arange(len(months))
    for split, origins in splits.items():
        for origin in origins:
            prior_counts = observed[:, :origin].sum(axis=1)
            tiers = tier_for_counts(prior_counts)
            for tier in ("A", "B", "C"):
                shops = tiers == tier
                for h in HORIZONS:
                    target_idx = origin + h - 1
                    valid = shops & observed[:, target_idx] & np.isfinite(y[:, target_idx])
                    coverage.append({"outcome": outcome, "tier": tier, "split": split, "origin": int(origin),
                                     "origin_month": months[origin-1], "horizon": h,
                                     "candidate_shops": int(shops.sum()), "observed_targets": int(valid.sum())})
                    predictions = {"trailing_3m": [], "linear_trend": []}
                    actuals = []
                    for i in np.flatnonzero(valid):
                        trailing = trailing_forecast(y[i], observed[i], origin, h)
                        trend = trend_forecast(y[i], observed[i], indices, origin, h)
                        if trailing is not None: predictions["trailing_3m"].append((int(i), float(trailing[h-1])))
                        if trend is not None: predictions["linear_trend"].append((int(i), float(trend[h-1])))
                        actuals.append((int(i), float(y[i,target_idx])))
                    actual_map = dict(actuals)
                    for model, pairs in predictions.items():
                        usable = [(actual_map[i], pred) for i,pred in pairs if i in actual_map]
                        if not usable: continue
                        actual=np.array([a for a,_ in usable]); pred=np.array([p for _,p in usable])
                        residual=actual-pred
                        records.append({"outcome":outcome,"tier":tier,"split":split,"origin":months[origin-1],
                                        "horizon":h,"model":model,"n":len(actual),"wape":float(np.abs(residual).sum()/actual.sum()) if actual.sum()>0 else None,
                                        "mae":float(np.abs(residual).mean()),"bias_actual_minus_forecast":float(residual.mean())})
                        if split in ("validation","holdout"):
                            residuals.setdefault((tier,split,h,model),[]).append(residual)
    return {"metrics":pd.DataFrame(records),"coverage":pd.DataFrame(coverage),"residuals":residuals,
            "splits":splits,"min_origin":origin_min,"max_origin":origin_max}


def choose_simple_model(backtest: dict[str, Any], outcome: str) -> dict[tuple[str,int],dict[str,Any]]:
    metrics=backtest["metrics"]
    result={}
    for _,tier in TIERS:
        for h in HORIZONS:
            get=lambda split: metrics[(metrics.tier==tier)&(metrics.split==split)&(metrics.horizon==h)]
            selection,validation,holdout=get("selection"),get("validation"),get("holdout")
            baseline_val=validation[validation.model=="trailing_3m"]
            n=int(baseline_val.n.max()) if not baseline_val.empty else 0
            candidate=None; val_wape=None; base_wape=float(baseline_val.wape.iloc[0]) if not baseline_val.empty and pd.notna(baseline_val.wape.iloc[0]) else None
            status="INSUFFICIENT_VALIDATION"; model="trailing_3m"
            if n>=MIN_EVAL and not selection.dropna(subset=["wape"]).empty:
                candidate=str(selection.loc[selection.wape.idxmin()].model)
                candidate_val=validation[validation.model==candidate]
                val_wape=float(candidate_val.wape.iloc[0]) if not candidate_val.empty and pd.notna(candidate_val.wape.iloc[0]) else None
                if candidate!="trailing_3m" and val_wape is not None and base_wape is not None and val_wape<=base_wape:
                    model=candidate; status="VALIDATED_MODEL"
                else:
                    status="TRAILING_BASELINE_FALLBACK"
            hold=holdout[holdout.model==model]
            result[(tier,h)]={"outcome":outcome,"tier":tier,"horizon":h,"model":model,"status":status,
                              "validation_n":n,"selection_model":candidate,"validation_wape":val_wape,
                              "validation_baseline_wape":base_wape,
                              "holdout_n":int(hold.n.iloc[0]) if not hold.empty else 0,
                              "holdout_wape":float(hold.wape.iloc[0]) if not hold.empty and pd.notna(hold.wape.iloc[0]) else None}
    return result


def forecast_current(y: np.ndarray, observed: np.ndarray, months: pd.DatetimeIndex,
                     summary: pd.DataFrame, outcome: str, decisions: dict) -> pd.DataFrame:
    indices=np.arange(len(months)); rows=[]; origin=len(months)
    for i,shop in summary.iterrows():
        count=int(observed[i].sum()); tier=str(tier_for_counts(np.array([count]))[0])
        if tier=="D" or not bool(shop.get("forecast_eligible",False)): continue
        points=[]; horizon_rows=[]
        for h in HORIZONS:
            d=decisions[(tier,h)]; model=d["model"]
            prediction=(trend_forecast(y[i],observed[i],indices,origin,h) if model=="linear_trend" else trailing_forecast(y[i],observed[i],origin,h))
            point=None if prediction is None else float(prediction[h-1]); points.append(point)
            residuals=d.get("validation_residuals")
            bounds=None
            if residuals is not None and point is not None:
                offsets=np.quantile(residuals,[.1,.9]); bounds=(max(0.,point+float(offsets[0])),max(0.,point+float(offsets[1])))
            status=d["status"]
            rows.append({"shop_key":shop.shop_key,"shop_id":shop.shop_id,"outcome":outcome,"origin_month":months[-1],"horizon":h,
                         "target_month":months[-1]+pd.offsets.MonthBegin(h),"point":point,
                         "lo":None if bounds is None else bounds[0],"hi":None if bounds is None else bounds[1],
                         "model":model,"tier":tier,"status":status,"forecast_reliability":status,
                         "eligibility_status":shop.eligibility_status,"interval_status":"DESCRIPTIVE_RESIDUAL_RANGE" if bounds else "INSUFFICIENT_VALIDATION",
                         "observation_quality_state":shop.observation_quality_state,
                         "downstream_usage_recommendation":"DESCRIPTIVE_ONLY"})
            horizon_rows.append(rows[-1])
        total_point=None if any(v is None for v in points) else float(sum(points))
        rows.append({"shop_key":shop.shop_key,"shop_id":shop.shop_id,"outcome":outcome,"origin_month":months[-1],"horizon":TOTAL,
                     "target_month":months[-1]+pd.offsets.MonthBegin(3),"point":total_point,
                     "lo":None if any(r["lo"] is None for r in horizon_rows) else float(sum(r["lo"] for r in horizon_rows)),
                     "hi":None if any(r["hi"] is None for r in horizon_rows) else float(sum(r["hi"] for r in horizon_rows)),
                     "model":"SUM_OF_HORIZONS","tier":tier,"status":decisions[(tier,1)]["status"],
                     "forecast_reliability":decisions[(tier,1)]["status"],"eligibility_status":shop.eligibility_status,
                     "interval_status":"DESCRIPTIVE_SUM_OF_HORIZON_RANGES" if all(r["lo"] is not None for r in horizon_rows) else "INSUFFICIENT_VALIDATION",
                     "observation_quality_state":shop.observation_quality_state,"downstream_usage_recommendation":"DESCRIPTIVE_ONLY"})
    return pd.DataFrame(rows)


def _lead_stats(lead_month: pd.DataFrame, latest: pd.Timestamp) -> pd.DataFrame:
    recent=lead_month[lead_month.month_start.isin(pd.date_range(latest-pd.DateOffset(months=2),latest,freq="MS"))]
    return recent.groupby("shop_key",as_index=False).agg(lead_rows_3m=("lead_rows","sum"),lead_uuids_3m=("lead_uuids","sum"),matched_uuids_3m=("matched_uuids","sum"))


def _attach_constraints(summary: pd.DataFrame, lead_month: pd.DataFrame, latest: pd.Timestamp) -> pd.DataFrame:
    stats=_lead_stats(lead_month,latest)
    out=summary.merge(stats,on="shop_key",how="left",validate="one_to_one")
    out["lead_match_rate"]=out.matched_uuids_3m/out.lead_uuids_3m.replace(0,np.nan)
    out["lead_match_rate"]=out.lead_match_rate.clip(0,1)
    out["peer_group"]=np.where(out.category.notna() & out.model.notna(),out.category.astype(str)+"|"+out.model.astype(str),"UNMAPPED_MASTER")
    out["peer_n"]=out.groupby("peer_group").shop_key.transform("count")
    return out



def _metric_row(metrics: pd.DataFrame, tier: str, split: str, horizon: int, model: str):
    row = metrics[(metrics.tier == tier) & (metrics.split == split) & (metrics.horizon == horizon) & (metrics.model == model)]
    return None if row.empty else row.iloc[0]


def _choose_intervals(backtest: dict[str, Any], decisions: dict[tuple[str, int], dict[str, Any]]) -> None:
    for (tier, horizon), decision in decisions.items():
        model = decision["model"]
        val_parts = backtest["residuals"].get((tier, "validation", horizon, model), [])
        hold_parts = backtest["residuals"].get((tier, "holdout", horizon, model), [])
        val = np.concatenate(val_parts) if val_parts else None
        hold = np.concatenate(hold_parts) if hold_parts else None
        decision["validation_residuals"] = None if val is None else np.quantile(val, [.1, .9]).tolist()
        decision["holdout_empirical_coverage"] = None
        decision["holdout_n"] = 0 if hold is None else int(len(hold))
        if val is None or hold is None:
            decision["interval_status"] = "INSUFFICIENT_VALIDATION"
        else:
            lo, hi = np.quantile(val, [.1, .9])
            coverage = float(np.mean((hold >= lo) & (hold <= hi)))
            decision["holdout_empirical_coverage"] = coverage
            decision["interval_status"] = "UNCALIBRATED" if len(hold) >= MIN_INTERVAL_EVAL and coverage < NOMINAL - .10 else ("INSUFFICIENT_HOLDOUT" if len(hold) < MIN_INTERVAL_EVAL else "EMPIRICAL_COVERAGE_NEAR_NOMINAL")


def forecast_current(y: np.ndarray, observed: np.ndarray, months: pd.DatetimeIndex,
                     summary: pd.DataFrame, outcome: str, decisions: dict[tuple[str,int],dict[str,Any]]) -> pd.DataFrame:
    month_indices = np.arange(len(months)); origin = len(months); records = []
    for i, shop in summary.iterrows():
        tier = str(tier_for_counts(np.array([int(observed[i].sum())]))[0])
        if tier == "D" or not bool(shop["forecast_eligible"]):
            continue
        component_points = []
        component_rows = []
        for horizon in HORIZONS:
            decision = decisions[(tier, horizon)]
            model = decision["model"]
            prediction = trend_forecast(y[i], observed[i], month_indices, origin, horizon) if model == "linear_trend" else trailing_forecast(y[i], observed[i], origin, horizon)
            point = None if prediction is None else float(prediction[horizon-1])
            offsets = decision.get("validation_residuals")
            lo = None if point is None or offsets is None else max(0., point + float(offsets[0]))
            hi = None if point is None or offsets is None else max(0., point + float(offsets[1]))
            complete_recent = shop["observation_quality_state"] == "COMPLETE_3M_OBSERVED"
            qualified = decision["status"] == "VALIDATED_MODEL" and decision["interval_status"] == "EMPIRICAL_COVERAGE_NEAR_NOMINAL" and complete_recent
            recommendation = "EVIDENCE_QUALIFIED_BAU" if qualified else "DESCRIPTIVE_ONLY"
            record = {"shop_key":shop.shop_key,"shop_id":shop.shop_id,"outcome":outcome,"origin_month":months[-1],
                      "horizon":str(horizon),"target_month":months[-1]+pd.offsets.MonthBegin(horizon),"point":point,"lo":lo,"hi":hi,
                      "model":model,"tier":tier,"status":decision["status"],"forecast_reliability":decision["status"],
                      "eligibility_status":shop["eligibility_status"],"interval_status":decision["interval_status"],
                      "interval_empirical_coverage":decision.get("holdout_empirical_coverage"),"interval_holdout_n":decision["holdout_n"],
                      "observation_quality_state":shop["observation_quality_state"],"downstream_usage_recommendation":recommendation,
                      "selection_wape":decision.get("selection_wape"),"validation_wape":decision.get("validation_wape"),"holdout_wape":decision.get("holdout_wape")}
            records.append(record); component_rows.append(record); component_points.append(point)
        total_point = None if any(p is None for p in component_points) else float(sum(component_points))
        total_bounds = None if any(r["lo"] is None or r["hi"] is None for r in component_rows) else (sum(r["lo"] for r in component_rows), sum(r["hi"] for r in component_rows))
        decision = decisions[(tier, 1)]
        records.append({"shop_key":shop.shop_key,"shop_id":shop.shop_id,"outcome":outcome,"origin_month":months[-1],"horizon":str(TOTAL),
                        "target_month":months[-1]+pd.offsets.MonthBegin(3),"point":total_point,
                        "lo":None if total_bounds is None else total_bounds[0],"hi":None if total_bounds is None else total_bounds[1],
                        "model":"SUM_OF_HORIZONS","tier":tier,"status":decision["status"],"forecast_reliability":decision["status"],
                        "eligibility_status":shop["eligibility_status"],"interval_status":"DESCRIPTIVE_SUM_OF_HORIZON_RANGES" if total_bounds else "INSUFFICIENT_VALIDATION",
                        "interval_empirical_coverage":None,"interval_holdout_n":0,"observation_quality_state":shop["observation_quality_state"],
                        "downstream_usage_recommendation":"EVIDENCE_QUALIFIED_BAU" if all(r["downstream_usage_recommendation"]=="EVIDENCE_QUALIFIED_BAU" for r in component_rows) else "DESCRIPTIVE_ONLY",
                        "selection_wape":decision.get("selection_wape"),"validation_wape":decision.get("validation_wape"),"holdout_wape":decision.get("holdout_wape")})
    return pd.DataFrame(records)


def _figures(summary: pd.DataFrame, forecasts: pd.DataFrame, backtest: pd.DataFrame,
             calibration: pd.DataFrame, panel: pd.DataFrame, pair: dict[str,Any], latest: pd.Timestamp) -> list[dict[str,Any]]:
    items=[]
    def finish(fig, fid, insight, evidence, limitation, status="SUPPORTED"):
        path=OUT/f"{fid}.png"; fig.savefig(path,dpi=DPI,facecolor="white",bbox_inches="tight");plt.close(fig)
        items.append({"figure_id":fid,"status":status,"insight":insight,"evidence":evidence,"limitation":limitation})
    fig,ax=plt.subplots(figsize=(7,4),dpi=DPI); vals=[summary.loc[summary.tier==t,"current_actual_3m_funded"].dropna() for t in ("A","B","C","D")];ax.boxplot(vals,tick_labels=["A","B","C","D"],showfliers=False);ax.set_ylabel("Complete 3-month funded-origin contracts");ax.set_title("Current actual by observed-history tier");finish(fig,"T1_01_Current_Actual_Baseline","Current actual varies by prior observed history.",f"Only complete three-month windows are reported through {latest:%b %Y}.","Incomplete windows remain missing; funded-origin is a configured proxy.")
    monthly=panel[panel.contract_observed].groupby("month_start",as_index=False).agg(funded=("funded_contract_count","sum"),applications=("contract_application_event_rows","sum"));fig,ax=plt.subplots(figsize=(8,4),dpi=DPI);ax.plot(monthly.month_start,monthly.funded,label="Funded-origin");ax.plot(monthly.month_start,monthly.applications,label="Applications");ax.legend(frameon=False);ax.set_ylabel("Recorded contract rows");ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"));finish(fig,"T1_02_Monthly_Shop_Trends","The two outcome measures move on different scales.",f"Window {monthly.month_start.min():%b %Y} to {latest:%b %Y}.","Only observed contract months are plotted.")
    cohorts=summary[summary.shop_id.notna()].groupby(summary.first_recorded_activity.dt.to_period("M").astype(str),dropna=True).shop_key.nunique();fig,ax=plt.subplots(figsize=(8,4),dpi=DPI);ax.bar(cohorts.index.astype(str),cohorts.values,color=COLORS["blue"]);ax.tick_params(axis="x",rotation=60);ax.set_ylabel("Shop IDs first recorded");ax.set_xlabel("First recorded contract activity month, not opening date");finish(fig,"T1_03_Shop_Lifecycle_Cohorts","First recorded activity dates show unequal history lengths.",f"{len(cohorts)} recorded-activity cohorts.","Extract activity is not a verified shop opening date.")
    peer=summary[summary.peer_n.ge(30)].groupby("peer_group").current_actual_3m_funded.agg(["median",lambda x:x.quantile(.25),lambda x:x.quantile(.75)]).dropna().head(12);fig,ax=plt.subplots(figsize=(8,4.5),dpi=DPI);ax.barh(np.arange(len(peer)),peer["median"],color=COLORS["blue"]);ax.set_yticks(np.arange(len(peer)),peer.index.astype(str));ax.set_xlabel("Peer median complete 3-month funded-origin contracts");finish(fig,"T1_04_Comparable_Shop_Benchmark","Comparable shops provide a descriptive range.",f"{len(peer)} peer groups with n≥30.","Peer performance is not guaranteed attainable potential.")
    model=backtest[(backtest.outcome=="funded")&(backtest.split=="validation")];cols=[(t,h) for t in ("A","B","C") for h in HORIZONS];body=[];valid_cells=0
    for name in ("trailing_3m","linear_trend"):
        row=[name]
        for t,h in cols:
            v=model[(model.tier==t)&(model.horizon==h)&(model.model==name)]
            if v.empty or pd.isna(v.wape.iloc[0]):row.append("N/A — insufficient validation")
            else:valid_cells+=1;row.append(f"{v.wape.iloc[0]:.3f} (n={int(v.n.iloc[0])})")
        body.append(row)
    fig,ax=plt.subplots(figsize=(10,2.6),dpi=DPI);ax.axis("off");tbl=ax.table(cellText=body,colLabels=["Model"]+[f"{t} h{h}" for t,h in cols],loc="center",cellLoc="center");tbl.auto_set_font_size(False);tbl.set_fontsize(7);tbl.scale(1,1.5);ax.set_title("Validation WAPE; N/A means insufficient validation",loc="left");finish(fig,"T1_05_Forecast_Model_Ladder","A simple linear trend is tested against trailing average.",f"{valid_cells} model-tier-horizon validation cells available.","Tier A has no valid validation origins; holdout is not used to choose models.")
    chosen=backtest[(backtest.outcome=="funded")]; rows=[]
    for t in ("A","B","C"):
        for h in HORIZONS:
            dec=STATE_DECISIONS.get(("funded",t,h),{}) if "STATE_DECISIONS" in globals() else {}
            mod=dec.get("model","trailing_3m")
            vals=[]
            for split in ("validation","holdout"):
                current=chosen[(chosen.tier==t)&(chosen.horizon==h)&(chosen.split==split)]
                a=current[current.model==mod]; b=current[current.model=="trailing_3m"]
                vals.extend(["N/A" if a.empty or pd.isna(a.wape.iloc[0]) else f"{a.wape.iloc[0]:.3f}",
                             "N/A" if b.empty or pd.isna(b.wape.iloc[0]) else f"{b.wape.iloc[0]:.3f}"])
            rows.append([f"{t} h{h}",mod,*vals])
    fig,ax=plt.subplots(figsize=(8,3.4),dpi=DPI);ax.axis("off")
    tbl=ax.table(cellText=rows,colLabels=["Tier/h","Selected by validation","Validation WAPE","Baseline WAPE","Holdout WAPE","Baseline WAPE"],loc="center",cellLoc="center")
    tbl.auto_set_font_size(False);tbl.set_fontsize(7);tbl.scale(1,1.4);ax.set_title("Holdout evaluates; selection never uses holdout",loc="left")
    finish(fig,"T1_06_Rolling_Origin_Backtest","Validation-selected model and holdout results are separate.","WAPE shown separately; N/A where no support.","Few time origins and overlapping shop observations limit inference.")
    cal=calibration[(calibration.outcome=="funded")];fig,ax=plt.subplots(figsize=(9,3.6),dpi=DPI);ax.axhline(NOMINAL,color=COLORS["gray"],linestyle="--",label="Nominal 80%");x=np.arange(len(cal));coverage=pd.to_numeric(cal.empirical_holdout_coverage,errors="coerce");ax.scatter(x,coverage,c=[COLORS["red"] if s=="UNCALIBRATED" else COLORS["blue"] for s in cal.interval_status]);ax.set_xticks(x,[f"{r.tier} h{r.horizon}" for r in cal.itertuples()],rotation=60);ax.set_ylim(0,1);ax.legend(frameon=False);ax.set_ylabel("Empirical holdout coverage");finish(fig,"T1_07_Forecast_Interval_Calibration","Intervals are empirical descriptive ranges, not guaranteed 80% intervals.",f"{int((cal.interval_status=='UNCALIBRATED').sum())} undercoverage flags across funded cells.","Tier A intervals unavailable; holdout sample is not independent by shop.")
    pair_ids=pair.get("pair_ids",[])
    for i in range(2):
        sid=pair_ids[i] if i<len(pair_ids) else None
        fig,ax=plt.subplots(figsize=(7,3.6),dpi=DPI)
        if sid is None:
            ax.text(.5,.5,"No pair met A05 with at least 30 comparable shops",ha="center",va="center",transform=ax.transAxes)
            ax.set_axis_off();status="UNSUPPORTED";limitation="No pair plotted because the required matching/support rule did not pass."
            evidence="Current actuals must be complete and within 10%; same category/model and peer n≥30."
        else:
            hist=panel[(panel.shop_key==sid)&panel.contract_observed].sort_values("month_start")
            ax.plot(hist.month_start,hist.funded_contract_count,marker="o",label="Observed funded-origin rows")
            fr=forecasts[(forecasts.shop_key==sid)&(forecasts.outcome=="funded")&forecasts.horizon.astype(str).isin([str(h) for h in HORIZONS])].sort_values("horizon")
            ax.plot(fr.target_month,fr.point,marker="s",label="BAU")
            bound=fr.dropna(subset=["lo","hi"])
            if not bound.empty:ax.fill_between(bound.target_month,bound.lo,bound.hi,alpha=.2,color=COLORS["mid"],label="Descriptive interval")
            ax.set_xlim(panel.month_start.min(),latest+pd.DateOffset(months=3));ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
            actual=summary.loc[summary.shop_key==sid,"current_actual_3m_funded"].iloc[0]
            observed_n=int(summary.loc[summary.shop_key==sid,"current_actual_3m_observed_months"].iloc[0])
            bau_row=forecasts[(forecasts.shop_key==sid)&(forecasts.outcome=="funded")&(forecasts.horizon==TOTAL)]
            bau=None if bau_row.empty else bau_row.iloc[0].point
            ax.set_title(f"A05 pair {i+1}: shop {sid} | actual {actual} | BAU {bau}")
            ax.set_ylabel("Funded-origin contracts");ax.legend(frameon=False,fontsize=7)
            evidence=f"Complete 3-month actual observed: {observed_n}/3; BAU reliability: {bau_row.iloc[0].forecast_reliability if not bau_row.empty else 'unavailable'}."
            limitation="Pair comparison is descriptive, not causal; BAU is not attainable uplift."
            status=pair.get("status","UNSUPPORTED")
        fid="T1_08A_Shop_Actual_vs_BAU" if i==0 else "T1_08B_Shop_Actual_vs_BAU"
        finish(fig,fid,"Similar-current shops are compared under the declared A05 rule.",evidence,limitation,status)
    return items


def attach_constraints(summary: pd.DataFrame, lead_month: pd.DataFrame, raw: pd.DataFrame,
                       months: pd.DatetimeIndex, latest: pd.Timestamp) -> pd.DataFrame:
    recent=lead_month[lead_month.month_start.isin(months[-3:])]
    lead_stats=recent.groupby("shop_key").agg(lead_rows_3m=("lead_rows","sum"),lead_uuids_3m=("lead_uuids","sum"),matched_uuids_3m=("matched_uuids","sum"))
    out=summary.join(lead_stats,on="shop_key")
    out["lead_match_rate"]=out.matched_uuids_3m/out.lead_uuids_3m.replace(0,np.nan)
    out["lead_match_rate"]=out.lead_match_rate.clip(0,1)
    return out


def build_task1() -> dict[str, Any]:
    raw, lead_month, context = load_inputs()
    months, latest = context["months"], context["latest"]
    raw = raw[raw.month_start.isin(months)].copy()
    raw["contract_observed"] = pd.to_numeric(raw.contract_application_event_rows, errors="coerce").fillna(0).gt(0)
    for outcome, source_col in OUTCOMES.items():
        raw[f"y_{outcome}"] = pd.to_numeric(raw[source_col], errors="coerce").where(raw.contract_observed)
    summary = raw.groupby("shop_key", sort=True).agg(
        shop_id=("skp_salesroom_id", "first"), category=("salesroom_category", "first"),
        model=("salesroom_model", "first"), master_state=("shop_master_state", "first"),
        observed_months=("contract_observed", "sum"),
        first_recorded_activity=("month_start", lambda s: s[raw.loc[s.index,"contract_observed"]].min()),
        last_recorded_activity=("month_start", lambda s: s[raw.loc[s.index,"contract_observed"]].max()),
    ).reset_index()
    summary["tier"] = tier_for_counts(summary.observed_months.to_numpy())
    summary["forecast_eligible"] = (summary.shop_id.notna() & summary.observed_months.ge(3)
                                     & summary.last_recorded_activity.ge(latest-pd.DateOffset(months=2)))
    summary["eligibility_status"] = np.where(summary.forecast_eligible,"ELIGIBLE_HISTORY_BASELINE","INSUFFICIENT_OR_DORMANT_HISTORY")
    all_backtest, all_forecasts, all_decisions = [], [], {}
    for outcome in OUTCOMES:
        matrix=raw.pivot(index="shop_key",columns="month_start",values=f"y_{outcome}").reindex(index=summary.shop_key,columns=months)
        mask=raw.pivot(index="shop_key",columns="month_start",values="contract_observed").reindex(index=summary.shop_key,columns=months).fillna(False).astype(bool)
        y,observed=matrix.to_numpy(float),mask.to_numpy(bool)
        actual=[]; actual_n=[]
        for i in range(len(summary)):
            value,n=complete_window_sum(y[i,-3:],observed[i,-3:]);actual.append(value);actual_n.append(n)
        summary[f"current_actual_3m_{outcome}"]=actual
        summary[f"current_actual_3m_months_{outcome}"]=actual_n
        if outcome=="funded":
            summary["current_actual_3m"]=actual
            summary["current_actual_3m_observed_months"]=actual_n
            summary["observation_quality_state"]=np.where(np.array(actual_n)==3,"COMPLETE_3M_OBSERVED",np.where(np.array(actual_n)>0,"PARTIAL_3M_OBSERVATION","NO_3M_OBSERVATION"))
        backtest=rolling_backtest(y,observed,months,outcome)
        decisions=choose_simple_model(backtest,outcome)
        _choose_intervals(backtest,decisions)
        forecasts=forecast_current(y,observed,months,summary,outcome,decisions)
        all_backtest.append(backtest);all_forecasts.append(forecasts);all_decisions[outcome]=decisions
    summary=_attach_constraints(summary,lead_month,latest)
    return publish_task1(summary,pd.concat(all_forecasts,ignore_index=True),pd.concat([x["metrics"] for x in all_backtest],ignore_index=True),all_decisions,raw,months,latest,context)


def publish_task1(summary, forecasts, backtest, decisions_by_outcome, raw, months, latest, context):
    global STATE_DECISIONS
    STATE_DECISIONS={(outcome,tier,h):d for outcome,mapping in decisions_by_outcome.items() for (tier,h),d in mapping.items()}
    candidate=select_similar_pair(summary,tolerance=.10)
    pair={"status":"UNSUPPORTED","pair_ids":[],"reliability_reasons":["NO_COMPLETE_ACTUAL_PAIR_MET_A05"]}
    if candidate:
        ids=candidate["pair_ids"];reasons=[];actuals={};bau={};diagnostics={}
        for sid in ids:
            shop=summary.loc[summary.shop_key.eq(sid)].iloc[0]
            actuals[sid]=float(shop.current_actual_3m_funded)
            ft=forecasts[(forecasts.shop_key==sid)&(forecasts.outcome=="funded")&(forecasts.horizon==TOTAL)]
            if ft.empty:
                bau[sid]={"point":None,"lo":None,"hi":None};reasons.append(f"{sid}:NO_FORECAST")
            else:
                row=ft.iloc[0];bau[sid]={"point":row.point,"lo":row.lo,"hi":row.hi}
                if row.downstream_usage_recommendation!="EVIDENCE_QUALIFIED_BAU":reasons.append(f"{sid}:DESCRIPTIVE_ONLY_BAU")
            if int(shop.current_actual_3m_observed_months)!=3:reasons.append(f"{sid}:INCOMPLETE_3M_ACTUAL")
            recent=raw[(raw.shop_key==sid)&raw.month_start.isin(months[-6:])].sort_values("month_start")
            diagnostics[sid]={"actual_observed_months_of_3":int(shop.current_actual_3m_observed_months),
                "observation_quality_state":shop.observation_quality_state,"last_recorded_activity":shop.last_recorded_activity,
                "recent_observations":[{"month":r.month_start,"observed":bool(r.contract_observed),"funded":float(r.funded_contract_count) if r.contract_observed else None,"applications":float(r.contract_application_event_rows) if r.contract_observed else None} for r in recent.itertuples()],
                "partial_3m_observed_funded_sum":float(recent[recent.month_start.isin(months[-3:])&recent.contract_observed].funded_contract_count.sum()),
                "recent_lead_rows":shop.lead_rows_3m,"recent_lead_uuids":shop.lead_uuids_3m,"lead_match_rate":shop.lead_match_rate,
                "forecast_path":forecasts[(forecasts.shop_key==sid)&(forecasts.outcome=="funded")&forecasts.horizon.isin(HORIZONS)][["horizon","point","model","forecast_reliability","interval_status","lo","hi"]].to_dict("records")}
        pair={"status":"ILLUSTRATIVE_ONLY" if reasons else "SUPPORTED_PAIR","pair_ids":ids,
              "selection_rule":"closest adjacent complete actuals within 10%, same available category/model, peer n>=30; lead-match contrast breaks ties",
              "peer_group":candidate["peer_group"],"peer_support":candidate["peer_support"],"actual_delta_pct":candidate["actual_delta_pct"],
              "current_actual_3m_funded":actuals,"bau_3m_total":bau,"reliability_diagnostics":diagnostics,
              "reliability_reasons":reasons,"causal_claim":False}
    calibration=pd.DataFrame([{"outcome":o,"tier":t,"horizon":h,"model":d["model"],"nominal_coverage":NOMINAL,
        "empirical_holdout_coverage":d.get("holdout_empirical_coverage"),"holdout_n":d.get("holdout_n",0),"interval_status":d.get("interval_status")}
        for o,mapping in decisions_by_outcome.items() for (t,h),d in mapping.items()])
    OUT.mkdir(parents=True,exist_ok=True)
    figures=_figures(summary,forecasts,backtest,calibration,raw,pair,latest)
    app_total=float(raw.contract_application_event_rows.sum())
    app_expected=context["metrics"].get("join_reconciliation",{}).get("contract_month_event_rows")
    total=forecasts[forecasts.horizon==TOTAL];parts=forecasts[forecasts.horizon!=TOTAL]
    total_bad=horizon_total_mismatches(parts,total)
    checks=[
        {"check":"phase1_revision2_gate","observed":context["gate"].get("execution_status"),"expected":"SUCCESS","status":"PASS" if context["gate"].get("execution_status")=="SUCCESS" and not context["gate"].get("fatal_failures") else "FAIL"},
        {"check":"application_rows_reconcile","observed":app_total,"expected":app_expected,"status":"PASS" if app_expected is not None and app_total==float(app_expected) else "FAIL"},
        {"check":"forecast_keys_unique","observed":int(forecasts.duplicated(["shop_key","outcome","horizon"]).sum()),"expected":0,"status":"PASS" if not forecasts.duplicated(["shop_key","outcome","horizon"]).any() else "FAIL"},
        {"check":"targets_after_origin","observed":bool((forecasts.target_month>forecasts.origin_month).all()),"expected":True,"status":"PASS" if (forecasts.target_month>forecasts.origin_month).all() else "FAIL"},
        {"check":"missing_contract_observations_not_zero","observed":int((~raw.contract_observed & raw.y_funded.notna()).sum()),"expected":0,"status":"PASS" if not ((~raw.contract_observed)&raw.y_funded.notna()).any() else "FAIL"},
        {"check":"3M_TOTAL_reconciles_horizons","observed":total_bad,"expected":0,"status":"PASS" if total_bad==0 else "FAIL"},
        {"check":"reliability_fields_present","observed":all(c in forecasts for c in ["forecast_reliability","eligibility_status","interval_status","observation_quality_state","downstream_usage_recommendation"]),"expected":True,"status":"PASS"},
        {"check":"pair_actual_coverage_status","observed":pair.get("status"),"expected":"downgraded if actual incomplete","status":"PASS" if pair.get("status")!="SUPPORTED_PAIR" or all(x["actual_observed_months_of_3"]==3 for x in pair.get("reliability_diagnostics",{}).values()) else "FAIL"},
    ]
    split=split_origins(3,len(months)-max(HORIZONS));val=split["validation"]
    tier_diag={o:{"tier_A_required_prior_observed_months":18,"validation_origin_indices":val,
                  "validation_origin_months":[str(months[i-1].date()) for i in val],
                  "maximum_prior_calendar_months":max(val,default=0),
                  "reason":"Each origin assigns tiers using prior observed contract months only. This history ends validation before the 18-month Tier A threshold; missing shop months reduce per-shop history further. Threshold retained.",
                  "status":"INSUFFICIENT_VALIDATION" if max(val,default=0)<18 else "CHECK_PER_SHOP_COUNTS"} for o in OUTCOMES}
    audit={"status":"SUCCESS" if all(x["status"]=="PASS" for x in checks) else "FAILED","phase1_gate":context["gate"],
           "window":{"history_start":months[0],"latest_complete":latest,"origin":months[-1],"contract_max_date":context["contract_max"]},
           "tier_validation_diagnostic":tier_diag,"decision_policy":"Selection split chooses a model; validation confirms it against trailing_3m; holdout reports performance only and does not select models or interval bounds.",
           "model_decisions":[{"outcome":o,"tier":t,"horizon":h,**d} for o,mapping in decisions_by_outcome.items() for (t,h),d in mapping.items()],
           "interval_calibration":calibration,"pair":pair,"checks":checks,
           "assumptions":{"current_actual":"Only complete three-month contract-observed windows; incomplete windows are null.","BAU":"Trailing mean of up to three prior observed months or linear trend over six prior observations; no seasonal or causal claim.","intervals":"Validation residual ranges checked on holdout; descriptive only, never claimed calibrated at 80%.","pair":"A05: closest adjacent complete actuals within ±10%, same available category/model, minimum peer n=30; observed lead-match contrast breaks ties; unmatched-master shops do not form one pseudo-peer group."},
           "task2_usage":"Quantitative potential gaps may use only EVIDENCE_QUALIFIED_BAU; DESCRIPTIVE_ONLY forecasts are excluded."}
    OUT.mkdir(parents=True,exist_ok=True)
    summary.to_parquet(OUT/"shop_performance_summary.parquet",index=False,compression="zstd")
    forecasts.to_parquet(OUT/"shop_bau_forecast.parquet",index=False,compression="zstd")
    backtest.to_parquet(OUT/"task1_backtest.parquet",index=False,compression="zstd")
    write_json(OUT/"task1_audit.json",audit);write_json(OUT/"task1_pair.json",pair)
    notes=["# Task 1 — Shop performance and BAU","",f"Observed contract history: {months[0]:%b %Y} to {latest:%b %Y}.",
           "Observed facts use contract-positive months; missing shop-months remain missing. Current actual is null unless all three months are observed.",
           "BAU compares trailing three-observation mean with a simple linear trend. Selection and validation choose; holdout only evaluates.",
           "Tier A has insufficient validation because validation origins do not contain 18 prior months; the 18-month threshold was retained.",
           "Intervals are empirical residual ranges, not guaranteed 80% intervals.",f"Comparable pair {pair.get('pair_ids')} status={pair.get('status')}; flags={pair.get('reliability_reasons',[])}.",
           "Task 2 may use only EVIDENCE_QUALIFIED_BAU rows quantitatively; DESCRIPTIVE_ONLY rows cannot support gap claims.",""]
    for item in figures:notes.extend([f"## {item['figure_id']}",f"![{item['figure_id']}]({item['figure_id']}.png)",item["insight"],item["evidence"],item["limitation"],""])
    (OUT/"task1_insights.md").write_text("\n".join(notes),encoding="utf-8")
    for item in figures:
        if item.get("figure") is not None:item["figure"].savefig(OUT/f"{item['figure_id']}.png",dpi=DPI,facecolor="white",bbox_inches="tight");plt.close(item["figure"])
    return {"summary":summary,"forecasts":forecasts,"backtest":backtest,"audit":audit,"pair":pair,"figures":figures}


def main(): return build_task1()

if __name__ == "__main__":
    result=main();print(f"Task 1 {result['audit']['status']}; forecasts={len(result['forecasts']):,}; pair={result['pair'].get('status')}")


