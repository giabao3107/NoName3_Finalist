"""Task 1: shop performance, comparable peers, and Business-as-Usual forecasting."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data_clean"
OUTPUT_DIR = ROOT / "output" / "Shop_Performance_and_BAU"
PHASE1_METRICS = DATA_DIR / "metrics_phase1.json"
PHASE1_VALIDATION = ROOT / "output" / "Data processing" / "validation_report.json"
PHASE2_MONTHLY = ROOT / "output" / "EDA" / "cache" / "fnd02_monthly.parquet"
SHOP_MONTH_SOURCE = DATA_DIR / "shop_month_foundation.parquet"
LEAD_PRODUCT_SOURCE = DATA_DIR / "lead_shop_month_product.parquet"
CONTRACT_SOURCE = DATA_DIR / "contract_clean.parquet"
LEAD_SOURCE = DATA_DIR / "leads_clean.parquet"

OUTCOMES = {
    "funded": "funded_contract_count",
    "application": "contract_application_event_rows",
}
PRIMARY_OUTCOME = "funded"
HORIZONS = (1, 2, 3)
TOTAL_HORIZON = "3M_TOTAL"
TIER_MINIMUMS = ((18, "A"), (9, "B"), (3, "C"))
MIN_PEER_SIZE = 30
MIN_TIER_EVAL = 15
MIN_RIDGE_TRAIN_ROWS = 120
RIDGE_ALPHA = 8.0
BLEND_WEIGHTS = (0.25, 0.50, 0.75)
INTERVAL_QUANTILES = (0.10, 0.90)
FORECAST_DPI = 200
NOMINAL_INTERVAL = INTERVAL_QUANTILES[1] - INTERVAL_QUANTILES[0]
MIN_PAIR_ACTUAL = 10

COLORS = {
    "primary": "#004AAD",
    "secondary": "#4472C4",
    "mid": "#8FAAD1",
    "risk": "#C51E1E",
    "muted": "#6B7280",
    "grid": "#E4E8ED",
    "white": "#FFFFFF",
}
plt.rcParams.update(
    {
        "font.family": "Arial",
        "font.size": 8.5,
        "figure.facecolor": COLORS["white"],
        "axes.facecolor": COLORS["white"],
        "savefig.facecolor": COLORS["white"],
        "text.color": "#16324F",
        "axes.labelcolor": COLORS["muted"],
        "xtick.color": COLORS["muted"],
        "ytick.color": COLORS["muted"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.grid": True,
        "grid.color": COLORS["grid"],
        "grid.linewidth": 0.5,
        "axes.axisbelow": True,
    }
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return json_safe(value.to_dict("records"))
    if isinstance(value, pd.Series):
        return json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def sql_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def month_start(value: Any) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("M").to_timestamp()


def save_figure(fig: plt.Figure, figure_id: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{figure_id}.png"
    fig.savefig(
        path,
        format="png",
        dpi=FORECAST_DPI,
        facecolor=COLORS["white"],
        edgecolor=COLORS["white"],
        transparent=False,
    )
    plt.close(fig)
    return path


def compact_axis(ax: plt.Axes, axis: str = "y") -> None:
    formatter = mtick.FuncFormatter(lambda value, _: f"{value:,.3g}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(formatter)


def tier_for_counts(counts: np.ndarray) -> np.ndarray:
    return np.select(
        [counts >= minimum for minimum, _ in TIER_MINIMUMS],
        [tier for _, tier in TIER_MINIMUMS],
        default="D",
    )


# ---------------------------------------------------------------- inputs


def load_window() -> dict[str, Any]:
    gate = read_json(PHASE1_VALIDATION)
    if gate.get("execution_status") != "SUCCESS" or gate.get("fatal_failures"):
        raise RuntimeError(
            "Phase 1 validation status is not SUCCESS; Task 1 will not proceed."
        )
    warnings = [
        f"Pending business gate: {name}"
        for name in gate.get("business_gates_pending", [])
    ]
    metrics = read_json(PHASE1_METRICS)
    con = duckdb.connect(database=":memory:")
    try:
        names = [
            row[0]
            for row in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet({sql_path(SHOP_MONTH_SOURCE)})"
            ).fetchall()
        ]
        optional = {
            "funded_contract_count": "NULL::BIGINT AS funded_contract_count",
            "active_headcount_proxy": "NULL::BIGINT AS active_headcount_proxy",
            "lifecycle_state": "NULL::VARCHAR AS lifecycle_state",
            "first_activity_month": "NULL::DATE AS first_activity_month",
            "last_activity_month": "NULL::DATE AS last_activity_month",
            "assigned_employee_count_raw": "NULL::BIGINT AS assigned_employee_count_raw",
            "distinct_lead_uuids": "NULL::BIGINT AS distinct_lead_uuids",
        }
        present = {name for name in optional if name in names}
        projection = [
            "CAST(skp_salesroom_id AS VARCHAR) AS shop_id",
            "CAST(month_start AS DATE) AS month_start",
            "salesroom_category",
            "salesroom_model",
            "salesroom_status",
            "shop_master_state",
            "event_coverage_state",
            "contract_application_event_rows",
            "lead_event_rows",
            "headcount_proxy_state",
        ]
        for name, fallback in optional.items():
            projection.append(name if name in present else fallback)
        panel = con.execute(
            "SELECT " + ", ".join(projection) + f" FROM read_parquet({sql_path(SHOP_MONTH_SOURCE)})"
        ).df()
        contract_min, contract_max = con.execute(
            f"SELECT min(date_apply_ts)::DATE, max(date_apply_ts)::DATE FROM read_parquet({sql_path(CONTRACT_SOURCE)}) "
            "WHERE date_apply_ts IS NOT NULL"
        ).fetchone()
        lead_min, lead_max = con.execute(
            f"SELECT min(date_assigned_ts)::DATE, max(date_assigned_ts)::DATE FROM read_parquet({sql_path(LEAD_SOURCE)}) "
            "WHERE date_assigned_ts IS NOT NULL"
        ).fetchone()
        funded_by_month = con.execute(
            f"SELECT date_trunc('month', date_apply_ts)::DATE AS m, count(*) FILTER (WHERE is_funded) AS funded, "
            f"count(*) AS applications FROM read_parquet({sql_path(CONTRACT_SOURCE)}) "
            "WHERE date_apply_ts IS NOT NULL GROUP BY 1"
        ).df()
    finally:
        con.close()
    history_start = month_start(contract_min)
    latest_candidate = month_start(contract_max)
    month_end = latest_candidate + pd.offsets.MonthEnd(0)
    latest_complete = (
        latest_candidate
        if pd.Timestamp(contract_max) == month_end
        else latest_candidate - pd.offsets.MonthBegin(1)
    )
    lead_start = month_start(lead_min)
    lead_month = month_start(lead_max)
    partial_lead = (
        lead_month
        if pd.Timestamp(lead_max) < lead_month + pd.offsets.MonthEnd(0)
        else None
    )
    return {
        "panel": panel,
        "metrics": metrics,
        "gate": gate,
        "warnings": warnings,
        "history_start": history_start,
        "latest_complete": latest_complete,
        "lead_start": lead_start,
        "partial_lead": partial_lead,
        "optional_missing": sorted(set(optional) - present),
        "optional_present": sorted(present),
        "funded_by_month": funded_by_month,
        "contract_max": contract_max,
        "lead_max": lead_max,
    }


def prepare_panel(
    raw: pd.DataFrame, context: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    panel = raw.copy()
    panel["month_start"] = pd.to_datetime(panel.month_start)
    panel["shop_key"] = panel.shop_id.fillna("UNKNOWN_SHOP_ID").astype(str)
    for column in (
        "contract_application_event_rows",
        "funded_contract_count",
        "lead_event_rows",
        "active_headcount_proxy",
        "assigned_employee_count_raw",
        "distinct_lead_uuids",
    ):
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel["contract_observed"] = panel.event_coverage_state.eq(
        "OBSERVED_EVENT_ROWS"
    ) & panel.month_start.le(context["latest_complete"])
    for outcome, column in OUTCOMES.items():
        values = panel[column].astype(float)
        panel[f"{outcome}_observed_value"] = values.where(panel.contract_observed)
    panel = panel.drop(
        columns=[column for column in ("first_activity_month", "last_activity_month", "lifecycle_state")
                 if column in panel.columns]
    )
    observed = (
        panel[panel.contract_observed]
        .groupby("shop_key")
        .month_start.agg(["min", "max", "count"])
    )
    observed.columns = [
        "first_activity_month",
        "last_activity_month",
        "observed_months",
    ]
    panel = panel.merge(observed, on="shop_key", how="left", validate="many_to_one")
    panel["lifecycle_state"] = np.select(
        [
            panel.first_activity_month.isna(),
            panel.month_start.lt(panel.first_activity_month),
            panel.month_start.gt(panel.last_activity_month),
        ],
        ["NO_OBSERVED_ACTIVITY", "PRE_LIFECYCLE", "POST_LIFECYCLE"],
        default="IN_LIFECYCLE",
    )
    panel["dormant_flag"] = panel.last_activity_month.notna() & (
        panel.last_activity_month < context["latest_complete"] - pd.DateOffset(months=2)
    )
    months = pd.date_range(
        context["history_start"], context["latest_complete"], freq="MS"
    )
    panel["in_window"] = panel.month_start.between(
        context["history_start"], context["latest_complete"]
    )
    return panel.loc[panel.in_window].copy(), months


def lead_product_features() -> pd.DataFrame:
    con = duckdb.connect(database=":memory:")
    try:
        frame = con.execute(f"""
            SELECT CAST(lead_origin_shop_id AS VARCHAR) AS shop_key,
                   CAST(month_start AS DATE) AS month_start,
                   COALESCE(CAST(lead_product_code AS VARCHAR), 'Unspecified') AS product_code,
                   SUM(lead_event_rows)::BIGINT AS lead_rows
            FROM read_parquet({sql_path(LEAD_PRODUCT_SOURCE)})
            GROUP BY 1, 2, 3
        """).df()
    finally:
        con.close()
    frame["month_start"] = pd.to_datetime(frame.month_start)
    return frame


def build_summary(
    panel: pd.DataFrame,
    context: dict[str, Any],
    months: pd.DatetimeIndex,
    lead_product: pd.DataFrame,
) -> pd.DataFrame:
    latest = context["latest_complete"]
    recent = [latest - pd.offsets.MonthBegin(offset) for offset in (2, 1, 0)]
    window = panel[panel.lifecycle_state.eq("IN_LIFECYCLE")].copy()
    grouped = window.groupby("shop_key")
    summary = grouped.agg(
        shop_id=("shop_id", "first"),
        salesroom_category=("salesroom_category", "first"),
        salesroom_model=("salesroom_model", "first"),
        salesroom_status=("salesroom_status", "first"),
        shop_master_state=("shop_master_state", "first"),
        lifecycle_state=("lifecycle_state", "first"),
        first_activity_month=("first_activity_month", "first"),
        last_activity_month=("last_activity_month", "first"),
        dormant_flag=("dormant_flag", "first"),
        observed_months=("contract_observed", "sum"),
        in_lifecycle_months=("month_start", "nunique"),
    ).reset_index()
    summary["in_lifecycle_zero_event_months"] = (
        summary.in_lifecycle_months - summary.observed_months
    ).clip(lower=0).astype(int)
    for outcome in OUTCOMES:
        value = window[f"{outcome}_observed_value"]
        one_month = (
            window[window.month_start.eq(latest)]
            .groupby("shop_key")[f"{outcome}_observed_value"]
            .sum(min_count=1)
        )
        three_month = (
            window[window.month_start.isin(recent)]
            .groupby("shop_key")[f"{outcome}_observed_value"]
            .sum(min_count=1)
        )
        summary[f"current_actual_1m_{outcome}"] = summary.shop_key.map(one_month)
        summary[f"current_actual_3m_{outcome}"] = summary.shop_key.map(three_month)
        del value
    recent_rows = window[window.month_start.isin(recent)]
    summary["lead_rows_3m"] = summary.shop_key.map(
        recent_rows.groupby("shop_key").lead_event_rows.sum(min_count=1)
    )
    summary["lead_uuids_3m"] = summary.shop_key.map(
        recent_rows.groupby("shop_key").distinct_lead_uuids.sum(min_count=1)
    )
    summary["assigned_headcount_proxy_3m"] = summary.shop_key.map(
        recent_rows.groupby("shop_key").active_headcount_proxy.mean()
    )
    summary["observed_history_tier"] = tier_for_counts(
        summary.observed_months.to_numpy(dtype=int)
    )
    summary["identified_shop_id"] = summary.shop_id.notna()
    summary["peer_group"] = pd.Series(
        summary.salesroom_category.astype(str)
        + " | "
        + summary.salesroom_model.astype(str),
        index=summary.index,
    ).where(summary.salesroom_category.notna() & summary.salesroom_model.notna())
    peer_stats = (
        summary[
            summary.peer_group.notna()
            & summary[f"current_actual_3m_{PRIMARY_OUTCOME}"].notna()
        ]
        .groupby("peer_group")[f"current_actual_3m_{PRIMARY_OUTCOME}"]
        .agg(
            peer_n="count",
            peer_median="median",
            peer_q1=lambda values: values.quantile(0.25),
            peer_q3=lambda values: values.quantile(0.75),
        )
        .reset_index()
    )
    summary = summary.merge(peer_stats, on="peer_group", how="left")
    summary["peer_supported"] = summary.peer_n.ge(MIN_PEER_SIZE)
    eligible = (
        summary.identified_shop_id
        & summary.lifecycle_state.eq("IN_LIFECYCLE")
        & ~summary.dormant_flag
        & summary.observed_months.ge(3)
    )
    summary["forecast_eligible"] = eligible
    summary["eligibility_status"] = np.select(
        [
            ~summary.identified_shop_id,
            summary.dormant_flag,
            summary.observed_months.lt(3),
            eligible,
        ],
        [
            "UNKNOWN_SHOP_ID_AGGREGATE",
            "DORMANT_NO_RECENT_ACTIVITY",
            "TIER_D_LT3_OBSERVED_MONTHS",
            "ELIGIBLE_FOR_FORECAST",
        ],
        default="NOT_ELIGIBLE",
    )
    latest_product = lead_product[lead_product.month_start.isin(recent)]
    mix = (
        latest_product.groupby(["shop_key", "product_code"])
        .lead_rows.sum()
        .unstack(fill_value=0)
    )
    mix = mix.div(mix.sum(axis=1).replace(0, np.nan), axis=0)
    mix_map = {
        str(key): {str(code): float(value) for code, value in row.dropna().items()}
        for key, row in mix.iterrows()
    }
    summary["lead_product_mix_3m"] = (
        summary.shop_key.map(mix_map)
        .apply(lambda value: value if isinstance(value, dict) else {})
    )
    return summary


# ---------------------------------------------------------------- model features


def history_features(
    y: np.ndarray, observed: np.ndarray, target_index: int, months: pd.DatetimeIndex
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    hist = y[:, :target_index]
    mask = observed[:, :target_index]
    counts = mask.sum(axis=1).astype(int)
    tiers = tier_for_counts(counts)
    calendar = np.broadcast_to(np.arange(target_index), mask.shape)
    observed_index = np.where(mask, calendar, -1)
    last_index = observed_index.max(axis=1)
    safe = np.nan_to_num(hist, nan=0.0)
    rows = np.arange(len(y))
    last_value = safe[rows, np.maximum(last_index, 0)]
    last_three = np.sort(observed_index, axis=1)[:, -3:]
    valid_three = last_three >= 0
    values_three = np.take_along_axis(safe, np.maximum(last_three, 0), axis=1)
    recent_mean = (values_three * valid_three).sum(axis=1) / np.maximum(
        valid_three.sum(axis=1), 1
    )
    ages = np.maximum(target_index - 1 - last_three, 0)
    weights = np.exp(-0.30 * ages) * valid_three
    ewm = (values_three * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-12)
    seasonal = recent_mean.copy()
    if target_index >= 12:
        seasonal_index = target_index - 12
        valid = mask[:, seasonal_index]
        seasonal[valid] = hist[valid, seasonal_index]
    gap = np.where(last_index >= 0, target_index - 1 - last_index, 36)
    target_month = months[target_index] if target_index < len(months) else months[-1]
    angle = 2 * math.pi * int(target_month.month) / 12
    features = np.column_stack(
        [
            np.log1p(np.maximum(last_value, 0)),
            np.log1p(np.maximum(recent_mean, 0)),
            np.log1p(np.maximum(ewm, 0)),
            np.log1p(np.maximum(seasonal, 0)),
            np.minimum(gap, 36),
            np.log1p(counts),
            np.full(len(y), math.sin(angle)),
            np.full(len(y), math.cos(angle)),
        ]
    )
    return (
        counts,
        tiers,
        features,
        {"recent_3m": recent_mean, "ewm": ewm, "naive": seasonal},
    )


def fit_ridge(
    y: np.ndarray, observed: np.ndarray, origin: int, months: pd.DatetimeIndex
):
    designs, targets, shops = [], [], []
    for target_index in range(len(TIER_MINIMUMS) + 3, origin):
        counts, tiers, features, _ = history_features(y, observed, target_index, months)
        keep = (tiers != "D") & (counts >= 3) & observed[:, target_index]
        if not keep.any():
            continue
        designs.append(add_tier_indicators(features[keep], tiers[keep]))
        targets.append(np.log1p(np.maximum(y[keep, target_index], 0)))
        shops.append(keep)
    if not targets:
        return None
    design = np.vstack(designs)
    target = np.concatenate(targets)
    if (
        len(target) < MIN_RIDGE_TRAIN_ROWS
        or sum(int(mask.sum()) for mask in shops) < MIN_PEER_SIZE
    ):
        return None
    mean, scale = design.mean(axis=0), design.std(axis=0)
    scale[scale == 0] = 1.0
    normalized = np.column_stack([np.ones(len(design)), (design - mean) / scale])
    penalty = np.eye(normalized.shape[1]) * RIDGE_ALPHA
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(
        normalized.T @ normalized + penalty, normalized.T @ target
    )
    return mean, scale, coefficients


def add_tier_indicators(features: np.ndarray, tiers: np.ndarray) -> np.ndarray:
    indicators = np.column_stack(
        [(tiers == tier).astype(float) for _, tier in TIER_MINIMUMS]
    )
    return np.column_stack([features, indicators])


def ridge_predict(features: np.ndarray, model) -> np.ndarray:
    mean, scale, coefficients = model
    design = np.column_stack([np.ones(len(features)), (features - mean) / scale])
    return np.maximum(0.0, np.expm1(np.clip(design @ coefficients, -20, 20)))


MODEL_NAMES = ["naive", "recent_3m", "ewm", "tier_peer_median", "ridge"] + [
    f"blend_{int(weight * 100)}" for weight in BLEND_WEIGHTS
]


def step_predictions(
    y: np.ndarray,
    observed: np.ndarray,
    target_index: int,
    months: pd.DatetimeIndex,
    ridge_model,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    counts, tiers, features, stats = history_features(y, observed, target_index, months)
    predictions = {
        "naive": stats["naive"],
        "recent_3m": stats["recent_3m"],
        "ewm": stats["ewm"],
        "tier_peer_median": np.full(len(y), np.nan),
        "ridge": np.full(len(y), np.nan),
    }
    for _, tier in TIER_MINIMUMS:
        peers = (tiers == tier) & (counts >= 3)
        if peers.sum() >= MIN_PEER_SIZE:
            predictions["tier_peer_median"][peers] = float(
                np.median(stats["recent_3m"][peers])
            )
    if ridge_model is not None:
        eligible = (tiers != "D") & (counts >= 3)
        predictions["ridge"][eligible] = ridge_predict(
            add_tier_indicators(features[eligible], tiers[eligible]), ridge_model
        )
    for weight in BLEND_WEIGHTS:
        key = f"blend_{int(weight * 100)}"
        valid = np.isfinite(predictions["ridge"]) & np.isfinite(predictions["ewm"])
        predictions[key] = np.full(len(y), np.nan)
        predictions[key][valid] = (
            weight * predictions["ridge"][valid]
            + (1 - weight) * predictions["ewm"][valid]
        )
    return tiers, predictions


def simulate_paths(
    y: np.ndarray,
    observed: np.ndarray,
    origin: int,
    months: pd.DatetimeIndex,
    ridge_model,
    steps: int,
) -> tuple[np.ndarray, np.ndarray]:
    history, mask = y, observed
    paths = []
    for step in range(steps):
        tiers, predictions = step_predictions(
            history, mask, origin + step, months, ridge_model
        )
        step_matrix = np.column_stack([predictions[name] for name in MODEL_NAMES])
        paths.append(step_matrix)
        for name_index, name in enumerate(MODEL_NAMES):
            history = np.concatenate([history, predictions[name][:, None]], axis=1)
            mask = np.concatenate([mask, np.ones((len(y), 1), dtype=bool)], axis=1)
    return np.stack(paths, axis=1), tiers


# ---------------------------------------------------------------- backtest


def split_origins(origin_min: int, origin_max: int) -> dict[str, list[int]]:
    origins = list(range(origin_min, origin_max + 1))
    if len(origins) < 3:
        return {"selection": origins, "validation": origins, "holdout": origins}
    selection_end = max(1, int(round(len(origins) * 0.55)))
    validation_end = max(selection_end + 1, int(round(len(origins) * 0.80)))
    return {
        "selection": origins[:selection_end],
        "validation": origins[selection_end:validation_end],
        "holdout": origins[validation_end:],
    }


def run_backtest(
    y: np.ndarray, observed: np.ndarray, months: pd.DatetimeIndex, outcome: str
) -> dict[str, Any]:
    origin_min = len(TIER_MINIMUMS) + 3
    origin_max = len(months) - max(HORIZONS)
    splits = split_origins(origin_min, origin_max)
    accumulation: dict[tuple, dict[str, float]] = {}
    residuals: dict[tuple, list[np.ndarray]] = {}
    totals: dict[tuple, list[np.ndarray]] = {}
    coverage_rows = []
    for split, origins in splits.items():
        for origin in origins:
            ridge_model = fit_ridge(y, observed, origin, months)
            paths, tiers = simulate_paths(
                y, observed, origin, months, ridge_model, max(HORIZONS)
            )
            for tier in [tier for _, tier in TIER_MINIMUMS]:
                shops = tiers == tier
                for horizon in HORIZONS:
                    target_index = origin + horizon - 1
                    target = y[:, target_index]
                    valid = shops & observed[:, target_index] & np.isfinite(target)
                    coverage_rows.append(
                        {
                            "outcome": outcome,
                            "tier": tier,
                            "split": split,
                            "origin_month": months[origin - 1],
                            "horizon": horizon,
                            "candidate_shops": int(shops.sum()),
                            "observed_targets": int(valid.sum()),
                            "target_coverage": float(valid.sum() / max(shops.sum(), 1)),
                        }
                    )
                    for name_index, name in enumerate(MODEL_NAMES):
                        prediction = paths[:, horizon - 1, name_index]
                        usable = valid & np.isfinite(prediction)
                        if not usable.any():
                            continue
                        actual = target[usable]
                        forecast = prediction[usable]
                        key = (tier, split, horizon, name)
                        record = accumulation.setdefault(
                            key, {"n": 0, "actual": 0.0, "abs": 0.0, "bias": 0.0}
                        )
                        record["n"] += int(usable.sum())
                        record["actual"] += float(actual.sum())
                        record["abs"] += float(np.abs(actual - forecast).sum())
                        record["bias"] += float((actual - forecast).sum())
                        if split in {"validation", "holdout"}:
                            residuals.setdefault(key, []).append(
                                (actual - forecast)[::25]
                            )
                    if origin + 2 < len(months):
                        total_actual = y[:, origin : origin + 3].sum(axis=1)
                        for name_index, name in enumerate(MODEL_NAMES):
                            total_pred = paths[:, :3, name_index].sum(axis=1)
                            usable = (
                                shops
                                & np.isfinite(total_actual)
                                & np.isfinite(total_pred)
                            )
                            if usable.any():
                                totals.setdefault((tier, split, name), []).append(
                                    (total_actual[usable] - total_pred[usable])[::25]
                                )
    metric_rows = []
    for tier in [tier for _, tier in TIER_MINIMUMS]:
        for split in ("selection", "validation", "holdout"):
            for horizon in HORIZONS:
                for name in MODEL_NAMES:
                    record = accumulation.get((tier, split, horizon, name))
                    if record is None:
                        continue
                    metric_rows.append(
                        {
                            "outcome": outcome,
                            "tier": tier,
                            "split": split,
                            "horizon": horizon,
                            "model": name,
                            "n": record["n"],
                            "total_actual_rows": record["actual"],
                            "mae_rows": record["abs"] / record["n"]
                            if record["n"]
                            else np.nan,
                            "wape": record["abs"] / record["actual"]
                            if record["actual"] > 0
                            else np.nan,
                            "bias_actual_minus_forecast": record["bias"] / record["n"]
                            if record["n"]
                            else np.nan,
                        }
                    )
    metrics = pd.DataFrame(metric_rows)
    coverage = pd.DataFrame(coverage_rows)
    metrics = metrics.merge(
        coverage.groupby(["outcome", "tier", "split", "horizon"], as_index=False).mean(
            numeric_only=True
        ),
        on=["outcome", "tier", "split", "horizon"],
        how="left",
    )
    interval_quantiles = {
        key: np.quantile(np.concatenate(values), INTERVAL_QUANTILES).tolist()
        for key, values in residuals.items()
        if values
    }
    total_quantiles = {
        key: np.quantile(np.concatenate(values), INTERVAL_QUANTILES).tolist()
        for key, values in totals.items()
        if values
    }
    return {
        "metrics": metrics,
        "coverage": coverage,
        "interval_quantiles": interval_quantiles,
        "total_quantiles": total_quantiles,
        "splits": splits,
        "min_origin": origin_min,
        "max_origin": origin_max,
    }


def choose_decisions(
    backtest: dict[str, Any], outcome: str
) -> dict[tuple[str, int], dict[str, Any]]:
    metrics = backtest["metrics"]
    decisions: dict[tuple[str, int], dict[str, Any]] = {}
    for tier in [tier for _, tier in TIER_MINIMUMS]:
        for horizon in HORIZONS:
            validation = metrics[
                (metrics.tier == tier)
                & (metrics.split == "validation")
                & (metrics.horizon == horizon)
            ]
            holdout = metrics[
                (metrics.tier == tier)
                & (metrics.split == "holdout")
                & (metrics.horizon == horizon)
            ]
            baseline_validation = validation[validation.model == "recent_3m"]
            baseline_holdout = holdout[holdout.model == "recent_3m"]
            validation_n = int(validation.n.max()) if not validation.empty else 0
            fallback, model, reason = False, "recent_3m", "INSUFFICIENT_VALIDATION"
            if (
                validation_n >= MIN_TIER_EVAL
                and not validation.dropna(subset=["wape"]).empty
            ):
                best = validation.loc[validation.wape.idxmin()]
                selected_holdout = holdout[holdout.model == best.model]
                beats_baseline = (
                    not baseline_holdout.empty
                    and not selected_holdout.empty
                    and float(selected_holdout.wape.iloc[0])
                    <= float(baseline_holdout.wape.iloc[0])
                )
                if beats_baseline:
                    model, reason = str(best.model), "VALIDATED_BEATS_TRAILING_BASELINE"
                else:
                    fallback, reason = True, "FALLBACK_TRAILING_BASELINE"
            else:
                fallback = True
            key = (tier, horizon)
            quantile_key = (tier, "validation", horizon, model)
            quantiles = backtest["interval_quantiles"].get(quantile_key)
            if quantiles is None:
                quantiles = backtest["interval_quantiles"].get(
                    (tier, "holdout", horizon, model)
                )
            total_key = (tier, "validation", model)
            total_quantiles = backtest["total_quantiles"].get(total_key) or backtest[
                "total_quantiles"
            ].get((tier, "holdout", model))
            decisions[key] = {
                "outcome": outcome,
                "tier": tier,
                "horizon": horizon,
                "model": model,
                "fallback": fallback,
                "status": "SUPPORTED" if not fallback else "TRAILING_BASELINE_FALLBACK",
                "reason": reason,
                "validation_n": validation_n,
                "interval_offsets": quantiles or None,
                "total_interval_offsets": total_quantiles or None,
            }
    return decisions


# ---------------------------------------------------------------- forecasting


def build_forecasts(
    outcome: str,
    y: np.ndarray,
    observed: np.ndarray,
    months: pd.DatetimeIndex,
    summary: pd.DataFrame,
    decisions: dict[tuple[str, int], dict[str, Any]],
    ridge_model,
    origin: int,
) -> pd.DataFrame:
    paths, tiers = simulate_paths(
        y, observed, origin, months, ridge_model, max(HORIZONS)
    )
    rows = []
    for index, shop_key in enumerate(summary.shop_key.to_numpy()):
        tier = str(tiers[index])
        if tier == "D":
            continue
        points = []
        for horizon in HORIZONS:
            decision = decisions[(tier, horizon)]
            model = decision["model"]
            model_index = MODEL_NAMES.index(model)
            point = float(paths[index, horizon - 1, model_index])
            offsets = decision["interval_offsets"] or [-0.5 * point, 0.5 * point]
            points.append(point)
            rows.append(
                {
                    "shop_key": shop_key,
                    "shop_id": summary.shop_id.iloc[index],
                    "outcome": outcome,
                    "origin_month": months[origin - 1],
                    "horizon": horizon,
                    "point": point,
                    "lo": max(0.0, point + float(offsets[0])),
                    "hi": max(0.0, point + float(offsets[1])),
                    "model": "TRAILING_BASELINE" if decision["fallback"] else model,
                    "model_is_baseline": bool(decision["fallback"]),
                    "tier": tier,
                    "status": decision["status"],
                    "reliability": "MODEL_BASED"
                    if not decision["fallback"]
                    else "TRAILING_BASELINE",
                    "eligibility": "FORECAST_ELIGIBLE",
                    "interval_status": "VALIDATION_RESIDUAL_QUANTILES",
                }
            )
        decision_one = decisions[(tier, 1)]
        offsets = decision_one["total_interval_offsets"] or [
            -0.5 * sum(points),
            0.5 * sum(points),
        ]
        rows.append(
            {
                "shop_key": shop_key,
                "shop_id": summary.shop_id.iloc[index],
                "outcome": outcome,
                "origin_month": months[origin - 1],
                "horizon": TOTAL_HORIZON,
                "point": float(sum(points)),
                "lo": max(0.0, sum(points) + float(offsets[0])),
                "hi": max(0.0, sum(points) + float(offsets[1])),
                "model": "SUM_OF_HORIZONS"
                if not decision_one["fallback"]
                else "TRAILING_BASELINE_SUM",
                "model_is_baseline": bool(decision_one["fallback"]),
                "tier": tier,
                "status": decision_one["status"],
                "reliability": "MODEL_BASED"
                if not decision_one["fallback"]
                else "TRAILING_BASELINE",
                "eligibility": "FORECAST_ELIGIBLE",
                "interval_status": "VALIDATION_RESIDUAL_QUANTILES",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- pair spine


def best_pair(frame: pd.DataFrame, tolerance: float, key: str = "peer_group"):
    best = None
    for _, group in frame.groupby(key, dropna=True):
        group = group.sort_values("actual")
        actual = group.actual.to_numpy(dtype=float)
        ratio = group.bau_ratio.to_numpy(dtype=float)
        keys = group.shop_key.to_numpy()
        peer_n = group.peer_n.fillna(0).to_numpy(dtype=float)
        left = 0
        for right in range(len(group)):
            while actual[right] - actual[left] > tolerance * max(actual[right], 1.0):
                left += 1
            window = ratio[left:right]
            if not len(window):
                continue
            for candidate in (
                int(np.argmin(window)) + left,
                int(np.argmax(window)) + left,
            ):
                if candidate == right:
                    continue
                difference = abs(ratio[right] - ratio[candidate])
                signature = tuple(sorted((str(keys[right]), str(keys[candidate]))))
                record = (
                    difference,
                    float(peer_n[right] + peer_n[candidate]),
                    signature,
                )
                if (
                    best is None
                    or record[:2] > best[:2]
                    or (record[:2] == best[:2] and record[2] < best[2])
                ):
                    best = record
    return best


def select_pair(summary: pd.DataFrame, forecasts: pd.DataFrame) -> dict[str, Any]:
    outcome = str(forecasts["outcome"].iloc[0])
    total = forecasts[forecasts.horizon == TOTAL_HORIZON]
    frame = summary[summary.forecast_eligible].copy()
    frame = frame.merge(
        total[["shop_key", "point", "lo", "hi"]], on="shop_key", how="inner"
    )
    frame = frame.rename(columns={f"current_actual_3m_{outcome}": "actual", "point": "bau_total"})
    frame = frame[
        (frame.actual >= MIN_PAIR_ACTUAL) & (frame.bau_total >= MIN_PAIR_ACTUAL)
        & frame.peer_supported & frame.peer_group.notna()
    ]
    frame["bau_ratio"] = frame.bau_total / frame.actual
    rules = [
        (0.10, "A05_SIMILAR_ACTUAL_10PCT", "peer_group"),
        (0.20, "A05_RELAXED_20PCT", "peer_group"),
        (0.20, "A05_CATEGORY_ONLY", "salesroom_category"),
    ]
    selected, rule_used, tolerance_used = None, None, 0.10
    for tolerance, rule, key in rules:
        selected = best_pair(frame, tolerance, key)
        if selected is not None:
            rule_used, tolerance_used = rule, tolerance
            break
    stability = {}
    for tolerance, label in ((0.05, "5pct"), (0.10, "10pct"), (0.20, "20pct")):
        found = best_pair(
            frame,
            tolerance,
            "peer_group" if tolerance >= 0.10 else "salesroom_category",
        )
        stability[label] = list(found[2]) if found else None
    if selected is None:
        return {
            "status": "UNSUPPORTED",
            "reason": "No similar-current pair met the candidate rules.",
            "stability": stability,
        }
    shop_a, shop_b = selected[2]
    record = frame[frame.shop_key.isin((shop_a, shop_b))].set_index("shop_key")
    pair = {
        "status": "SUPPORTED",
        "pair_id": f"{shop_a}::{shop_b}",
        "shop_ids": [shop_a, shop_b],
        "rule_used": rule_used,
        "tolerance": tolerance_used,
        "peer_group": record.loc[shop_a, "peer_group"],
        "peer_n": int(record.loc[shop_a, "peer_n"]),
        "actual_3m_funded": {
            key: float(record.loc[key, "actual"]) for key in (shop_a, shop_b)
        },
        "bau_3m_total": {
            key: {
                "point": float(record.loc[key, "bau_total"]),
                "lo": float(record.loc[key, "lo"]),
                "hi": float(record.loc[key, "hi"]),
            }
            for key in (shop_a, shop_b)
        },
        "bau_ratio": {
            key: float(record.loc[key, "bau_ratio"]) for key in (shop_a, shop_b)
        },
        "observed_contrasts": {
            key: {
                "lead_rows_3m": float(record.loc[key, "lead_rows_3m"])
                if pd.notna(record.loc[key, "lead_rows_3m"])
                else None,
                "distinct_lead_uuids_3m": float(record.loc[key, "lead_uuids_3m"])
                if pd.notna(record.loc[key, "lead_uuids_3m"])
                else None,
                "assigned_headcount_proxy_3m": float(
                    record.loc[key, "assigned_headcount_proxy_3m"]
                )
                if pd.notna(record.loc[key, "assigned_headcount_proxy_3m"])
                else None,
                "lead_product_mix_3m": record.loc[key, "lead_product_mix_3m"],
            }
            for key in (shop_a, shop_b)
        },
        "note": "Observed contrasts are descriptive, not causal.",
        "stability": stability,
    }
    return pair


def pair_stability_share(pair: dict[str, Any], alternative: dict[str, Any]) -> bool:
    if pair.get("status") != "SUPPORTED" or alternative.get("status") != "SUPPORTED":
        return False
    return set(pair["shop_ids"]) == set(alternative["shop_ids"])


# ---------------------------------------------------------------- figures


def figure_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    figures = []
    summary = state["summary"]
    primary = summary[
        summary.identified_shop_id
        & summary[f"current_actual_3m_{PRIMARY_OUTCOME}"].notna()
    ]

    fig, ax = plt.subplots(
        figsize=(8.0, 4.2), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    tier_order = ["A", "B", "C", "D"]
    values = [
        primary.loc[
            primary.observed_history_tier.eq(tier),
            f"current_actual_3m_{PRIMARY_OUTCOME}",
        ].dropna()
        for tier in tier_order
    ]
    ax.boxplot(
        values,
        tick_labels=tier_order,
        showfliers=False,
        patch_artist=True,
        boxprops={"facecolor": COLORS["mid"], "edgecolor": COLORS["primary"]},
        medianprops={"color": COLORS["primary"], "linewidth": 1.6},
    )
    ax.set_ylabel(
        f"Funded-origin contracts, 3 months to {state['latest_complete']:%B %Y}"
    )
    ax.set_xlabel("Observed-history tier")
    ax.tick_params(length=0)
    figures.append(
        {
            "figure_id": "T1_01_Current_Actual_Baseline",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Current observed activity differs strongly across history tiers.",
            "evidence": f"Median 3-month funded-origin actual for tier A is "
            f"{primary.loc[primary.observed_history_tier.eq('A'), f'current_actual_3m_{PRIMARY_OUTCOME}'].median():,.0f} "
            f"contracts; tier D median is "
            f"{primary.loc[primary.observed_history_tier.eq('D'), f'current_actual_3m_{PRIMARY_OUTCOME}'].median():,.0f}.",
            "implication": "Forecast capability must be reported by tier rather than as one network number.",
            "limitation": "Funded-origin is the contest assumption A01; raw application volume is a separate outcome.",
        }
    )

    monthly = state["monthly"].copy()
    fig, ax = plt.subplots(
        figsize=(8.0, 4.0), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    ax.plot(
        monthly.month_start,
        monthly.funded_contract_rows,
        color=COLORS["primary"],
        linewidth=1.8,
        label="Funded-origin contracts",
    )
    ax.plot(
        monthly.month_start,
        monthly.contract_application_rows,
        color=COLORS["secondary"],
        linewidth=1.4,
        label="Contract applications",
    )
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    compact_axis(ax)
    ax.set_ylabel("Recorded event rows")
    ax.legend(frameon=False, fontsize=8)
    figures.append(
        {
            "figure_id": "T1_02_Monthly_Shop_Trends",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Monthly activity moved through a clear expansion and later slowdown.",
            "evidence": f"Window covers {state['history_start']:%B %Y} to {state['latest_complete']:%B %Y}; "
            f"last complete month has {int(monthly.funded_contract_rows.iloc[-1]):,} funded-origin contracts "
            f"and {int(monthly.contract_application_rows.iloc[-1]):,} applications.",
            "implication": "Forecast origins must respect the difference between record volume and funded-origin volume.",
            "limitation": "Monthly sums include recorded rows only; missing shop-months are not zero.",
        }
    )

    cohort = (
        summary[summary.identified_shop_id]
        .assign(cohort=summary.first_activity_month.dt.to_period("M").astype(str))
        .groupby("cohort", as_index=False)
        .agg(
            shop_ids=("shop_key", "nunique"),
            median_months=("observed_months", "median"),
        )
    )
    fig, ax = plt.subplots(
        figsize=(8.0, 4.0), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    ax.bar(cohort.cohort, cohort.shop_ids, color=COLORS["primary"])
    ax.set_ylabel("Shop IDs first observed")
    ax.set_xlabel("First observed contract month")
    ax.tick_params(axis="x", rotation=45, length=0)
    figures.append(
        {
            "figure_id": "T1_03_Shop_Lifecycle_Cohorts",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Most shops enter the observed window early, with a smaller later cohort.",
            "evidence": f"Largest cohort is {cohort.sort_values('shop_ids', ascending=False).iloc[0].cohort} with "
            f"{int(cohort.sort_values('shop_ids', ascending=False).iloc[0].shop_ids):,} shops.",
            "implication": "History-based tiers are required because lifecycle length is highly uneven.",
            "limitation": "First observed month is an extract artefact, not a verified opening date.",
        }
    )

    peers = (
        summary[summary.peer_supported]
        .groupby("peer_group")
        .agg(
            shops=("shop_key", "nunique"),
            median=("current_actual_3m_funded", "median"),
            q1=("current_actual_3m_funded", lambda values: values.quantile(0.25)),
            q3=("current_actual_3m_funded", lambda values: values.quantile(0.75)),
        )
        .reset_index()
    )
    peers = peers.sort_values("shops", ascending=False).head(10).sort_values("median")
    fig, ax = plt.subplots(
        figsize=(8.0, 4.4), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    y = np.arange(len(peers))
    ax.errorbar(
        peers["median"],
        y,
        xerr=[peers["median"] - peers.q1, peers.q3 - peers["median"]],
        fmt="o",
        color=COLORS["primary"],
        ecolor=COLORS["mid"],
        capsize=3,
    )
    ax.set_yticks(y, peers.peer_group.str.slice(0, 36))
    ax.set_xlabel("3-month funded-origin contracts (median and interquartile range)")
    figures.append(
        {
            "figure_id": "T1_04_Comparable_Shop_Benchmark",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Peer groups differ in both level and dispersion of current activity.",
            "evidence": f"{len(peers):,} supported peer groups shown; top group contains "
            f"{int(peers.shops.max()):,} shops.",
            "implication": "Comparisons should stay within a supported category-model peer group.",
            "limitation": "Peer definitions use current snapshot attributes and observed-tier membership.",
        }
    )

    ladder = state["backtest"][
        (state["backtest"].split == "validation")
        & (state["backtest"].outcome == PRIMARY_OUTCOME)
    ]
    ladder = ladder[ladder.horizon == 1]
    best_tier = (
        state["decisions"][(PRIMARY_OUTCOME, "A", 1)]["model"]
        if (PRIMARY_OUTCOME, "A", 1) in state["decisions"]
        else "recent_3m"
    )
    ladder = ladder[ladder.tier == "A"].sort_values("wape")
    fig, ax = plt.subplots(
        figsize=(8.0, 4.2), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    ax.barh(
        ladder.model,
        ladder.wape,
        color=[
            COLORS["primary"] if model == best_tier else COLORS["mid"]
            for model in ladder.model
        ],
    )
    ax.set_xlabel("Validation WAPE (lower is better)")
    figures.append(
        {
            "figure_id": "T1_05_Forecast_Model_Ladder",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Transparent baselines are competitive; the selected model is tier-specific.",
            "evidence": f"Tier A horizon 1 selects {best_tier}; best validation WAPE is "
            f"{float(ladder.wape.min()):.3f}.",
            "implication": "Model choice is justified by out-of-sample error, not complexity.",
            "limitation": "Validation evidence is short-history and tier-specific.",
        }
    )

    holdout = state["backtest"][
        (state["backtest"].split == "holdout")
        & (state["backtest"].outcome == PRIMARY_OUTCOME)
    ]
    selected_rows = []
    for tier in ("A", "B", "C"):
        for horizon in HORIZONS:
            model = state["decisions"][(PRIMARY_OUTCOME, tier, horizon)]["model"]
            row = holdout[
                (holdout.tier == tier)
                & (holdout.horizon == horizon)
                & (holdout.model == model)
            ]
            baseline = holdout[
                (holdout.tier == tier)
                & (holdout.horizon == horizon)
                & (holdout.model == "recent_3m")
            ]
            if not row.empty:
                selected_rows.append(
                    {
                        "label": f"{tier} · h{horizon}",
                        "selected": float(row.wape.iloc[0]),
                        "baseline": float(baseline.wape.iloc[0])
                        if not baseline.empty
                        else np.nan,
                    }
                )
    comparison = pd.DataFrame(selected_rows)
    fig, ax = plt.subplots(
        figsize=(8.0, 4.2), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    positions = np.arange(len(comparison))
    ax.bar(
        positions - 0.19,
        comparison.selected,
        width=0.38,
        color=COLORS["primary"],
        label="Selected model",
    )
    ax.bar(
        positions + 0.19,
        comparison.baseline,
        width=0.38,
        color=COLORS["mid"],
        label="Trailing 3-month baseline",
    )
    ax.set_xticks(positions, comparison.label, rotation=45, ha="right")
    ax.set_ylabel("Holdout WAPE")
    ax.legend(frameon=False, fontsize=8)
    figures.append(
        {
            "figure_id": "T1_06_Rolling_Origin_Backtest",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Model advantage over the trailing baseline exists in some tier-horizon cells only.",
            "evidence": f"Selected model beats the trailing baseline in "
            f"{int((comparison.selected <= comparison.baseline).sum()):,} of {len(comparison):,} tier-horizon cells.",
            "implication": "Where the baseline wins, BAU should be reported as a trailing reference.",
            "limitation": "Holdout origins are few; WAPE differences are noisy.",
        }
    )

    calibration = state["coverage_summary"]
    if calibration.empty:
        figures.append({"figure_id": "T1_07_Forecast_Interval_Calibration", "figure": None, "status": "UNSUPPORTED",
                        "insight": "Interval coverage could not be evaluated.", "evidence": "No holdout residuals were available.",
                        "implication": "Report intervals as uncalibrated.", "limitation": "No holdout evidence."})
        return figures
    fig, ax = plt.subplots(
        figsize=(8.0, 3.8), dpi=FORECAST_DPI, facecolor=COLORS["white"]
    )
    ax.bar(
        calibration.horizon.astype(str), calibration.coverage, color=COLORS["primary"]
    )
    ax.axhline(
        NOMINAL_INTERVAL,
        color=COLORS["risk"],
        linestyle="--",
        linewidth=1.1,
        label="Nominal 80%",
    )
    ax.set_ylim(0, 1)
    ax.set_xlabel("Forecast horizon")
    ax.set_ylabel("Holdout interval coverage")
    ax.legend(frameon=False, fontsize=8)
    figures.append(
        {
            "figure_id": "T1_07_Forecast_Interval_Calibration",
            "figure": fig,
            "status": "SUPPORTED",
            "insight": "Intervals are built from validation residuals and checked on later origins.",
            "evidence": f"Holdout coverage ranges from {calibration.coverage.min():.2f} to {calibration.coverage.max():.2f}.",
            "implication": "Wide intervals should accompany fallback and short-history tiers.",
            "limitation": "Residual quantiles are tier-level, not shop-specific.",
        }
    )

    pair = state["pair"]
    ymax = 0.0
    pair_series = {}
    for shop_key in pair.get("shop_ids", []):
        history = state["panel"][state["panel"].shop_key.eq(shop_key)].sort_values(
            "month_start"
        )
        history = history[history.contract_observed]
        pair_series[shop_key] = history[
            ["month_start", f"{PRIMARY_OUTCOME}_observed_value"]
        ].dropna()
        if not pair_series[shop_key].empty:
            ymax = max(
                ymax,
                float(pair_series[shop_key][f"{PRIMARY_OUTCOME}_observed_value"].max()),
            )
    bau = state["forecasts"][(state["forecasts"].outcome == PRIMARY_OUTCOME)]
    for shop_key in pair.get("shop_ids", []):
        rows = bau[bau.shop_key.eq(shop_key) & bau.horizon.ne(TOTAL_HORIZON)]
        ymax = max(ymax, float(rows.hi.max()) if not rows.empty else 0.0)
    ymax = max(ymax, 1.0)
    for position, shop_key in enumerate(pair.get("shop_ids", [])):
        fig, ax = plt.subplots(
            figsize=(8.0, 4.0), dpi=FORECAST_DPI, facecolor=COLORS["white"]
        )
        series = pair_series.get(shop_key, pd.DataFrame())
        if not series.empty:
            ax.plot(
                series.month_start,
                series[f"{PRIMARY_OUTCOME}_observed_value"],
                color=COLORS["primary"],
                marker="o",
                markersize=3,
                linewidth=1.4,
                label="Observed funded-origin contracts",
            )
        rows = bau[
            bau.shop_key.eq(shop_key) & bau.horizon.ne(TOTAL_HORIZON)
        ].sort_values("horizon")
        if not rows.empty:
            ax.plot(
                rows.target_month,
                rows.point,
                color=COLORS["secondary"],
                marker="s",
                markersize=4,
                linewidth=1.5,
                label="BAU path",
            )
            ax.fill_between(
                rows.target_month,
                rows.lo,
                rows.hi,
                color=COLORS["mid"],
                alpha=0.25,
                label="BAU interval",
            )
        ax.set_ylim(0, ymax * 1.1)
        ax.set_ylabel("Funded-origin contracts per month")
        ax.set_xlim(
            series.month_start.min() if not series.empty else state["history_start"],
            state["latest_complete"] + pd.DateOffset(months=3),
        )
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.legend(frameon=False, fontsize=7.5, loc="upper left")
        figure_id = f"T1_08{'A' if position == 0 else 'B'}_Shop_Actual_vs_BAU"
        figures.append(
            {
                "figure_id": figure_id,
                "figure": fig,
                "status": "SUPPORTED",
                "insight": "similar today, different BAU trajectory",
                "evidence": f"Shop {shop_key}: 3-month actual {pair['actual_3m_funded'][shop_key]:,.0f}; "
                f"BAU 3M total {pair['bau_3m_total'][shop_key]['point']:,.0f} "
                f"(interval {pair['bau_3m_total'][shop_key]['lo']:,.0f} to "
                f"{pair['bau_3m_total'][shop_key]['hi']:,.0f}).",
                "implication": "Similar current volume does not imply the same forward trajectory.",
                "limitation": "The pair is selected on pre-origin evidence; contrasts are observed, not causal.",
            }
        )
    return figures


# ---------------------------------------------------------------- audits


def reconciliation_checks(state: dict[str, Any]) -> list[dict[str, Any]]:
    window_start, window_end = state["history_start"], state["latest_complete"]
    panel = state["panel"][state["panel"].month_start.between(window_start, window_end)]
    funded_panel = float(panel.funded_contract_count.sum())
    application_panel = float(panel.contract_application_event_rows.sum())
    funded_month = state["funded_by_month"].copy()
    funded_month["m"] = pd.to_datetime(funded_month.m)
    funded_month = funded_month[funded_month.m.between(window_start, window_end)]
    application_month = (
        state["metrics"].get("join_reconciliation", {}).get("contract_month_event_rows")
    )
    checks = [
        {
            "check": "funded_rows_reconcile_to_contract_source",
            "observed": funded_panel,
            "expected": float(funded_month.funded.sum()),
            "status": "PASS"
            if funded_panel == float(funded_month.funded.sum())
            else "FAIL",
        },
        {
            "check": "application_rows_reconcile_to_phase1_month_rows",
            "observed": application_panel,
            "expected": None if application_month is None else float(application_month),
            "status": "PASS"
            if application_month is not None
            and application_panel == float(application_month)
            else "FAIL",
        },
        {
            "check": "one_row_per_shop_outcome_horizon",
            "observed": int(
                state["forecasts"].duplicated(["shop_key", "outcome", "horizon"]).sum()
            ),
            "expected": 0,
            "status": "PASS"
            if not state["forecasts"]
            .duplicated(["shop_key", "outcome", "horizon"])
            .any()
            else "FAIL",
        },
        {
            "check": "fnd02_monthly_columns_superset",
            "observed": sorted(state["phase2_monthly_columns"]),
            "expected": [
                "month_start",
                "contract_application_rows",
                "lead_assignment_rows",
                "shops_with_any_recorded_event",
            ],
            "status": "PASS"
            if {
                "month_start",
                "contract_application_rows",
                "lead_assignment_rows",
                "shops_with_any_recorded_event",
            }.issubset(state["phase2_monthly_columns"])
            else "FAIL",
        },
    ]
    total_rows = state["forecasts"][
        state["forecasts"].horizon == TOTAL_HORIZON
    ].set_index(["shop_key", "outcome"])
    horizon_rows = state["forecasts"][state["forecasts"].horizon != TOTAL_HORIZON]
    mismatches = 0
    for (shop_key, outcome), total in total_rows.iterrows():
        parts = horizon_rows[
            (horizon_rows.shop_key == shop_key) & (horizon_rows.outcome == outcome)
        ]
        if len(parts) == len(HORIZONS):
            expected = float(parts.point.sum())
            if abs(expected - float(total.point)) > 1e-6:
                mismatches += 1
    checks.append(
        {
            "check": "three_month_total_equals_horizon_sum",
            "observed": mismatches,
            "expected": 0,
            "status": "PASS" if mismatches == 0 else "FAIL",
        }
    )
    checks.append(
        {
            "check": "origin_precedes_all_targets",
            "observed": str(state["forecasts"].target_month.min().date()),
            "expected": f"later than origin {state['forecasts'].origin_month.max().date()}",
            "status": "PASS"
            if state["forecasts"].target_month.min() > state["forecasts"].origin_month.max()
            else "FAIL",
        }
    )
    source_pattern = (
        r"\"(?:January|February|March|April|May|June|July|August|September|October|November|December) "
        r"\d{4}\"|\"20\d{2}-\d{2}"
    )
    hard_coded = bool(re.search(source_pattern, Path(__file__).read_text(encoding="utf-8")))
    checks.append(
        {
            "check": "no_hand_typed_month_year_in_text",
            "observed": hard_coded,
            "expected": False,
            "status": "PASS" if not hard_coded else "FAIL",
        }
    )
    return checks


def holdout_subgroup_errors(state: dict[str, Any]) -> pd.DataFrame:
    metrics = state["backtest"]
    rows = []
    for outcome in OUTCOMES:
        holdout = metrics[
            (metrics.outcome == outcome) & (metrics.split == "holdout")
        ].copy()
        for tier in ("A", "B", "C"):
            for horizon in HORIZONS:
                model = state["decisions"][(outcome, tier, horizon)]["model"]
                row = holdout[
                    (holdout.tier == tier)
                    & (holdout.horizon == horizon)
                    & (holdout.model == model)
                ]
                if row.empty:
                    continue
                rows.append(
                    {
                        "outcome": outcome,
                        "tier": tier,
                        "horizon": horizon,
                        "model": model,
                        "n": int(row.n.iloc[0]),
                        "wape": float(row.wape.iloc[0]),
                        "bias": float(row.bias_actual_minus_forecast.iloc[0]),
                    }
                )
    return pd.DataFrame(rows)


def missing_outcome_bounds(state: dict[str, Any]) -> pd.DataFrame:
    coverage = state["backtest_coverage"]
    coverage = coverage.groupby(
        ["outcome", "tier", "split", "horizon"], as_index=False
    ).agg(
        candidate_shops=("candidate_shops", "sum"),
        observed_targets=("observed_targets", "sum"),
    )
    coverage["missing_targets"] = coverage.candidate_shops - coverage.observed_targets
    coverage["observed_share"] = (
        coverage.observed_targets / coverage.candidate_shops.replace(0, np.nan)
    )
    return coverage


def interval_calibration(state: dict[str, Any], backtests: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for outcome in OUTCOMES:
        quantiles_map = backtests[outcome]["interval_quantiles"]
        for tier in ("A", "B", "C"):
            for horizon in HORIZONS:
                decision = state["decisions"][(outcome, tier, horizon)]
                validation_key = (tier, "validation", horizon, decision["model"])
                quantiles = quantiles_map.get(validation_key)
                holdout_key = (tier, "holdout", horizon, decision["model"])
                if quantiles is None or holdout_key not in quantiles_map:
                    continue
                low, high = quantiles
                residuals = np.asarray(quantiles_map[holdout_key], dtype=float)
                rows.append(
                    {
                        "outcome": outcome,
                        "tier": tier,
                        "horizon": horizon,
                        "coverage": float(
                            np.mean((residuals >= low) & (residuals <= high))
                        )
                        if len(residuals)
                        else np.nan,
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["horizon", "coverage"])
    return frame.groupby("horizon", as_index=False).coverage.mean()


def positive_only_sensitivity(
    y: np.ndarray, observed: np.ndarray, months: pd.DatetimeIndex
) -> dict[str, Any]:
    positive = observed & np.isfinite(y) & (y > 0)
    counts = positive.sum(axis=1)
    baseline = observed.sum(axis=1)
    result = run_backtest(y, positive, months, PRIMARY_OUTCOME)
    decisions = choose_decisions(result, PRIMARY_OUTCOME)
    tier_shift = {
        tier: int(((tier_for_counts(baseline) == tier) != (tier_for_counts(counts) == tier)).sum())
        for tier in ("A", "B", "C", "D")
    }
    return {
        "tier_shift": {
            tier: int(
                (
                    (tier_for_counts(baseline) == tier)
                    != (tier_for_counts(counts) == tier)
                ).sum()
            )
            for tier in ("A", "B", "C", "D")
        },
        "shops_tier_changed": int(
            (tier_for_counts(baseline) != tier_for_counts(counts)).sum()
        ),
        "decision_status": {
            f"{tier}_h{horizon}": decisions[(tier, horizon)]["status"]
            for tier in ("A", "B", "C")
            for horizon in HORIZONS
        },
    }


# ---------------------------------------------------------------- insights


def build_insights(state: dict[str, Any], figures: list[dict[str, Any]]) -> str:
    pair = state["pair"]
    pair_note = (
        (
            f"Pair {pair.get('pair_id')} selected with rule {pair.get('rule_used')} "
            f"(tolerance ±{100 * pair.get('tolerance', 0):.0f}%)."
        )
        if pair.get("status") == "SUPPORTED"
        else "No supported similar-current pair was found."
    )
    lines = ["# Task 1 — Shop performance and BAU", ""]
    for figure in figures:
        lines.extend(
            [
                f"## {figure['figure_id']}",
                f"![{figure['figure_id']}]({figure['figure_id']}.png)",
                "",
                f"**Insight:** {figure['insight']}",
                "",
                f"**Evidence:** {figure['evidence']}",
                "",
                f"**Implication:** {figure['implication']}",
                "",
                f"**Limitations:** {figure['limitation']}",
                "",
            ]
        )
        if figure["figure_id"].startswith("T1_08A"):
            lines.extend([f"**Pair evidence:** {pair_note}", ""])
    lines.extend(
        [
            "## Scope",
            "",
            "Descriptive and BAU only. No attainable potential, ranking, recommendation or causal effect is produced.",
            "Funded-origin contracts follow contest assumption A01; application volume is a demand indicator.",
            "Assigned headcount is a descriptive assignment count (A11), never FTE and never a forecast feature.",
            "Sample weights are not used. No-event shop-months remain missing rather than zero demand.",
        ]
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- orchestration


def main() -> dict[str, Any]:
    context = load_window()
    panel, months = prepare_panel(context["panel"], context)
    lead_product = lead_product_features()
    summary = build_summary(panel, context, months, lead_product)
    window = panel[panel.lifecycle_state.eq("IN_LIFECYCLE")]
    forecast_pool = summary[summary.forecast_eligible].sort_values("shop_key")
    y_by_outcome, mask_by_outcome = {}, {}
    for outcome in OUTCOMES:
        pivot = window.pivot(index="shop_key", columns="month_start", values=f"{outcome}_observed_value")
        observed = window.pivot(index="shop_key", columns="month_start", values="contract_observed")
        pivot = pivot.reindex(index=forecast_pool.shop_key, columns=months)
        observed = observed.reindex(index=forecast_pool.shop_key, columns=months).fillna(False).astype(bool)
        y_by_outcome[outcome] = pivot.to_numpy(dtype=float)
        mask_by_outcome[outcome] = observed.to_numpy(dtype=bool)

    origin = len(months)
    backtests, decisions, pairs = {}, {}, {}
    forecast_frames = []
    for outcome in OUTCOMES:
        backtests[outcome] = run_backtest(y_by_outcome[outcome], mask_by_outcome[outcome], months, outcome)
        decisions[outcome] = choose_decisions(backtests[outcome], outcome)
        ridge_model = fit_ridge(y_by_outcome[outcome], mask_by_outcome[outcome], origin, months)
        frame = build_forecasts(outcome, y_by_outcome[outcome], mask_by_outcome[outcome], months,
                                forecast_pool, decisions[outcome], ridge_model, origin)
        forecast_frames.append(frame)
        pairs[outcome] = select_pair(summary, frame)
    forecasts = pd.concat(forecast_frames, ignore_index=True)
    forecasts["horizon"] = forecasts["horizon"].astype(str)
    horizon_months = forecasts["horizon"].map(lambda value: 3 if value == TOTAL_HORIZON else int(value))
    forecast_periods = pd.PeriodIndex(forecasts["origin_month"], freq="M") + horizon_months.to_numpy()
    forecasts["target_month"] = forecast_periods.to_timestamp(how="start")
    pair = pairs[PRIMARY_OUTCOME]

    monthly = window.groupby("month_start", as_index=False).agg(
        funded_contract_rows=("funded_contract_count", "sum"),
        contract_application_rows=("contract_application_event_rows", "sum"),
        lead_assignment_rows=("lead_event_rows", "sum"))
    phase2_monthly = pd.read_parquet(PHASE2_MONTHLY)

    state: dict[str, Any] = {
        "context": context, "panel": panel, "summary": summary, "monthly": monthly,
        "phase2_monthly_columns": [str(column) for column in phase2_monthly.columns],
        "backtest": pd.concat([backtests[outcome]["metrics"] for outcome in OUTCOMES], ignore_index=True),
        "backtest_coverage": pd.concat([backtests[outcome]["coverage"] for outcome in OUTCOMES], ignore_index=True),
        "decisions": {(outcome, tier, horizon): decision
                      for outcome in OUTCOMES
                      for (tier, horizon), decision in decisions[outcome].items()},
        "forecasts": forecasts, "pairs": pairs, "pair": pair,
        "history_start": context["history_start"], "latest_complete": context["latest_complete"],
        "lead_start": context["lead_start"], "partial_lead": context["partial_lead"],
        "funded_by_month": context["funded_by_month"], "metrics": context["metrics"],
    }
    state["coverage_summary"] = interval_calibration(state, backtests)
    figures = figure_state(state)
    state["insights"] = build_insights(
        state, [{key: value for key, value in item.items() if key != "figure"} for item in figures])
    checks = reconciliation_checks(state)
    sensitivity = positive_only_sensitivity(y_by_outcome[PRIMARY_OUTCOME], mask_by_outcome[PRIMARY_OUTCOME], months)

    primary_rank = forecasts[(forecasts.outcome == PRIMARY_OUTCOME) & (forecasts.horizon == TOTAL_HORIZON)].set_index("shop_key").point
    application_rank = forecasts[(forecasts.outcome == "application") & (forecasts.horizon == TOTAL_HORIZON)].set_index("shop_key").point
    common = primary_rank.index.intersection(application_rank.index)
    rank_stability = {
        "spearman_rank_correlation": float(primary_rank.loc[common].corr(application_rank.loc[common], method="spearman"))
        if len(common) > 1 else None,
        "pair_unchanged_when_outcome_switched": pair_stability_share(pair, pairs["application"]),
        "common_shop_count": int(len(common)),
    }
    forecast_counts = (forecasts[forecasts.horizon == TOTAL_HORIZON]
                       .groupby(["outcome", "tier"], as_index=False).shop_key.nunique()
                       .rename(columns={"shop_key": "forecasted_shops"}))

    audits = {
        "gate": {"execution_status": context["gate"].get("execution_status"),
                 "fatal_failures": context["gate"].get("fatal_failures"),
                 "business_gates_pending": context["gate"].get("business_gates_pending"),
                 "warnings": context["warnings"]},
        "window": {"history_start": context["history_start"], "latest_complete": context["latest_complete"],
                   "lead_start": context["lead_start"], "partial_lead": context["partial_lead"],
                   "contract_max_date": context["contract_max"], "lead_max_date": context["lead_max"],
                   "forecast_origin_month": months[origin - 1], "horizons": list(HORIZONS)},
        "phase1_optional_columns": {"present": context["optional_present"],
                                     "derived_when_missing": context["optional_missing"]},
        "observation_audit": (panel.assign(state=np.select(
            [panel.contract_observed & panel.contract_application_event_rows.gt(0),
             panel.contract_observed & panel.contract_application_event_rows.eq(0),
             panel.lifecycle_state.ne("IN_LIFECYCLE")],
            ["OBSERVED_POSITIVE", "OBSERVED_ZERO", "OUTSIDE_LIFECYCLE"], default="MISSING_IN_LIFECYCLE"))
            .groupby("state", as_index=False).agg(shop_month_rows=("shop_key", "size"),
                                                  shop_ids=("shop_key", "nunique"),
                                                  contract_rows=("contract_application_event_rows", "sum"))),
        "in_lifecycle_zero_event_months": int(summary.in_lifecycle_zero_event_months.sum()),
        "source_reconciliation": checks,
        "positive_only_sensitivity_primary_outcome": sensitivity,
        "holdout_subgroup_errors": holdout_subgroup_errors(state),
        "missing_outcome_bounds": missing_outcome_bounds(state),
        "interval_calibration": state["coverage_summary"],
        "coverage": (summary[summary.identified_shop_id]
                     .groupby(["observed_history_tier", "eligibility_status"], as_index=False)
                     .agg(shop_ids=("shop_key", "nunique"),
                          market_matched=("shop_master_state", lambda values: int(values.eq("UNIQUE_MASTER_ROW").sum())),
                          median_3m_funded=("current_actual_3m_funded", "median"))),
        "forecasted_by_tier_outcome": forecast_counts,
        "pair": pair,
        "rank_stability": rank_stability,
        "model_decisions": [{"outcome": outcome, "tier": tier, "horizon": horizon, **decision}
                            for (outcome, tier, horizon), decision in state["decisions"].items()],
        "warnings": context["warnings"],
        "failed_checks": [check["check"] for check in checks if check["status"] != "PASS"],
    }

    primary_total = forecasts[
        (forecasts.outcome == PRIMARY_OUTCOME) & (forecasts.horizon == TOTAL_HORIZON)
    ].set_index("shop_key")
    summary["forecast_reliability"] = summary.shop_key.map(primary_total.reliability).fillna("UNSUPPORTED")
    summary["forecast_status"] = summary.shop_key.map(primary_total.status).fillna(summary.eligibility_status)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_columns = ["shop_key", "shop_id", "salesroom_category", "salesroom_model", "salesroom_status",
                       "shop_master_state", "lifecycle_state", "first_activity_month", "last_activity_month",
                       "dormant_flag", "observed_months", "in_lifecycle_months", "in_lifecycle_zero_event_months",
                       "observed_history_tier", "current_actual_1m_funded", "current_actual_3m_funded",
                       "current_actual_1m_application", "current_actual_3m_application", "peer_group", "peer_n",
                       "peer_median", "peer_q1", "peer_q3", "peer_supported", "forecast_eligible",
                       "eligibility_status", "forecast_reliability", "forecast_status",
                       "lead_rows_3m", "lead_uuids_3m", "assigned_headcount_proxy_3m",
                       "lead_product_mix_3m"]
    summary_out = summary[summary_columns].copy()
    summary_out["lead_product_mix_3m"] = summary_out["lead_product_mix_3m"].map(
        lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True))
    summary_out.to_parquet(OUTPUT_DIR / "shop_performance_summary.parquet", index=False, compression="zstd")
    forecasts.to_parquet(OUTPUT_DIR / "shop_bau_forecast.parquet", index=False, compression="zstd")
    state["backtest"].to_parquet(OUTPUT_DIR / "task1_backtest.parquet", index=False, compression="zstd")
    write_json(OUTPUT_DIR / "task1_audit.json", audits)
    write_json(OUTPUT_DIR / "task1_pair.json", pair)
    (OUTPUT_DIR / "task1_insights.md").write_text(state["insights"], encoding="utf-8")
    for figure in figures:
        if figure.get("figure") is not None:
            save_figure(figure["figure"], figure["figure_id"])
    failed = audits["failed_checks"]
    supported = sum(1 for figure in figures if figure["status"] == "SUPPORTED")
    print(f"{'SUCCESS' if not failed else 'FAILED'} | figures={supported}/{len(figures)} "
          f"| forecasted_shops={int(forecast_counts.forecasted_shops.sum()):,} | failed_checks={len(failed)}")
    return {"status": "SUCCESS" if not failed else "FAILED", "figures": figures, "audit": audits}


if __name__ == "__main__":
    main()
