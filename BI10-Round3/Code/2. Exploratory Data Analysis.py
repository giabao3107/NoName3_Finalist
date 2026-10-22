# %% [markdown]
# # Phase 2 — Exploratory Data Analysis
# DuckDB-only descriptive analysis of the Phase 1 handoff; no forecasting, potential, ranking or recommendations.

# %%
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
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
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "Data_clean"
OUTPUT_DIR = ROOT / "output" / "EDA"
CACHE_DIR = OUTPUT_DIR / "cache"
PHASE1_METRICS = DATA_DIR / "metrics_phase1.json"
PHASE1_VALIDATION = ROOT / "output" / "Data processing" / "validation_report.json"
TRANSFORMATION_VERSION = "bi10-r3-phase2-eda-v1"
CACHE_ROW_GROUP_SIZE = 65_536
FIGURE_IDS = tuple(f"FND_{index:02d}" for index in range(1, 10))
LAYOUT_WARNINGS: list[dict[str, Any]] = []

COLORS = {
    "primary": "#004AAD", "secondary": "#4472C4", "mid": "#8FAAD1",
    "risk": "#C51E1E", "muted": "#6C737B", "grid": "#E6E8EB", "white": "#FFFFFF",
}
DISPLAY_LABELS = {
    "CONTRACT_TO_CURRENT_SHOP": "Contracts linked to current shop",
    "LEAD_TO_CURRENT_SHOP": "Leads linked to current shop",
    "CONTRACT_APPLICATIONS:STRICTLY_POST_COMMON_CUTOFF": "Post-cutoff contracts with Customer Profile",
    "LEAD_ASSIGNMENTS:STRICTLY_POST_COMMON_CUTOFF": "Post-cutoff leads with Customer Profile",
    "LEAD_EVENT_ROWS": "Lead events with configured product mapping",
    "LEAD_CONTRACT_BRIDGE_ROWS": "Criterion-qualified lead-contract pairs",
    "NO_R2_SEGMENT": "Unclassified",
    "CONTRACT_APPLICATION": "Contract applications",
    "LEAD_ORIGIN": "Lead events",
    "UNMATCHED_NO_CANDIDATE": "No contract candidate",
    "TEMPORAL_UNKNOWN": "Date unavailable",
    "TEMPORAL_FAIL": "Date rule failed",
    "PRODUCT_MAPPING_UNAPPROVED": "Product mapping not configured",
    "PRODUCT_UNMAPPED_OR_INCOMPATIBLE": "Product not mapped",
    "CLIENT_MISMATCH": "Client mismatch",
    "CANDIDATE_REQUIRES_REVIEW": "Candidate needs review",
    "SCC": "SCC", "SCC PR2": "SCC PR2", "SCC PR3": "SCC PR3",
    "dpd_1pd_nonnull_rows": "dpd_1pd", "dpd_2pd_nonnull_rows": "dpd_2pd",
    "dpd_3pd_nonnull_rows": "dpd_3pd", "dpd_4pd_nonnull_rows": "dpd_4pd",
    "TITLE:FND_01": "Coverage by definition and join",
    "TITLE:FND_02": "Observed event dates and monthly volume",
    "TITLE:FND_03": "Lead UUID and weight-cell audit",
    "TITLE:FND_04": "Lead-contract match states and primary attribution",
    "TITLE:FND_05": "Lead product mapping and contract detail",
    "TITLE:FND_06": "Shop behavior across the full fact universe",
    "TITLE:FND_07": "Customer Profile coverage after cutoff",
    "TITLE:FND_08": "Employee assignment status and intervals",
    "TITLE:FND_09": "DPD checkpoint field availability",
}

PARQUET_INPUTS = {
    "contract": "contract_clean.parquet",
    "leads": "leads_clean.parquet",
    "contract_product": "contract_product_clean.parquet",
    "shop": "shop_clean.parquet",
    "seller": "seller_clean.parquet",
    "employee": "employee_shop_clean.parquet",
    "candidate": "lead_contract_candidates.parquet",
    "shop_month": "shop_month_foundation.parquet",
    "lead_month_product": "lead_shop_month_product.parquet",
    "lead_conversion": "lead_conversion_shop_month.parquet",
    "shop_behavior": "shop_behavior_profile.parquet",
    "r2_segment": "R2/r2_customer_segment.parquet",
}
SOURCE_COLUMNS = {
    "contract": ["contract_fact_id", "skp_salesroom_id", "skp_credit_case_id", "skp_client_id",
        "product_raw", "contract_status_raw", "business_outcome", "credit_amount_raw", "date_apply_ts",
        "date_apply_state", "date_sign_ts", "date_sign_state", "date_sign_was_sentinel",
        "is_funded", "is_funded_sign_date", "is_funded_status", "is_funded_billing", "after_common_r2_cutoff",
        "contract_version_state", "distinct_source_versions", "exact_duplicate_group_size",
        "dpd_1pd_raw", "dpd_2pd_raw", "dpd_3pd_raw", "dpd_4pd_raw",
        "goods_categories", "goods_types", "goods_groups", "producers"],
    "leads": ["lead_row_id", "lead_uuid", "uuid_source_row_count", "skp_client_id", "skp_salesroom_id",
        "skp_employee_id", "skp_credit_case_id", "lead_source_raw", "lead_product_code",
        "lead_product_original_code", "lead_status_code_raw", "lead_status_id", "lead_reason_mapping_state",
        "date_assigned_ts", "date_assigned_state", "dtime_created_ts", "dtime_created_state",
        "date_assigned_was_sentinel", "dtime_created_was_sentinel", "sample_weight_raw", "sample_weight",
        "after_common_r2_cutoff", "weight_status", "candidate_contract_count", "direct_case_candidate_count",
        "same_client_product_candidate_count", "confirmed_match_count", "unapproved_product_candidate_count",
        "temporal_fail_candidate_count", "temporal_unknown_candidate_count", "is_ambiguous", "lead_match_state"],
    "contract_product": ["skp_credit_case_id", "producer_raw", "goods_category_raw", "goods_type_raw", "goods_group_raw"],
    "shop": ["master_record_id", "skp_salesroom_id", "salesroom_category", "salesroom_model", "salesroom_product",
        "salesroom_status", "salesroom_province", "salesroom_area", "master_version_state", "attribute_vintage", "seller_match_state"],
    "seller": ["master_record_id", "skp_seller_id", "seller_model", "seller_status", "seller_type", "seller_product", "master_version_state"],
    "employee": ["employee_assignment_id", "skp_salesroom_id", "skp_employee_id", "role_raw", "code_status_raw",
        "valid_from_ts", "valid_to_ts", "valid_from_state", "valid_to_state", "valid_to_was_sentinel",
        "assignment_interval_state", "overlaps_prior_interval", "status_is_approved_active", "shop_match_state"],
    "candidate": ["lead_row_id", "contract_fact_id", "booking_shop_id", "contract_product_raw", "contract_status_raw",
        "contract_apply_ts", "candidate_credit_amount_raw", "is_funded", "via_direct_case_key", "via_client_product",
        "candidate_evidence", "lead_skp_client_id", "lead_origin_shop_id", "lead_product_code",
        "lead_product_original_code", "date_assigned_ts", "lead_uuid", "client_match_state",
        "product_compatibility_state", "temporal_state", "match_status", "is_confirmed_match",
        "is_primary_match", "direct_key_agrees_with_primary"],
    "shop_month": ["skp_salesroom_id", "month_start", "salesroom_category", "salesroom_model", "salesroom_product",
        "salesroom_status", "salesroom_province", "salesroom_area", "contract_application_event_rows",
        "contract_distinct_credit_cases", "contract_distinct_customers", "contract_credit_amount_raw_sum",
        "funded_contract_count", "funded_credit_amount_raw_sum",
        "lead_event_rows", "distinct_lead_uuids", "lead_distinct_customers", "raw_weight_sensitivity_sum_qa_only",
        "assigned_employee_count_raw", "assignment_interval_rows", "active_headcount_proxy", "headcount_proxy_state",
        "event_coverage_state", "shop_master_state", "shop_attribute_vintage", "outcome_definition_state",
        "amount_semantics_state", "weight_status"],
    "lead_month_product": ["lead_origin_shop_id", "month_start", "lead_product_code", "lead_event_rows", "distinct_lead_uuids",
        "distinct_customers", "exact_duplicate_event_rows", "raw_weight_sensitivity_sum_qa_only",
        "event_rows_with_confirmed_match", "event_rows_product_mapping_unapproved", "primary_matched_contracts",
        "funded_primary_matched_contracts", "weight_status"],
    "lead_conversion": ["lead_origin_shop_id", "booking_shop_id", "month_start", "normalized_product",
        "primary_matched_contracts", "funded_primary_matched_contracts", "matched_credit_amount_raw",
        "lead_origin_shop_category", "booking_shop_category", "is_cross_shop", "is_cross_category"],
    "shop_behavior": ["skp_salesroom_id", "observed_contract_months", "avg_contracts_per_observed_month", "avg_funded_share",
        "lead_volume", "product_mix_share_tw", "product_mix_share_cl", "product_mix_share_cc", "product_mix_share_cd",
        "product_mix_share_other", "share_of_months_with_leads", "first_observed_month", "last_observed_month", "master_matched_flag"],
    "r2_segment": ["skp_client_id", "fh_short", "eng_short", "customer_segment", "fh_thin_file", "score_join_state",
        "segment_join_eligible", "common_segment_outcome_cutoff", "cutoff_provenance_state"],
}

# %%
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_signature(inputs: dict[str, str], transformation_version: str) -> str:
    payload = {"transformation_version": transformation_version, "inputs": dict(sorted(inputs.items()))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()




def validate_required_columns(con: duckdb.DuckDBPyConnection, required: dict[str, set[str]]) -> dict[str, list[str]]:
    actual = {}
    for view, expected in required.items():
        if not con.execute("SELECT count(*) FROM information_schema.views WHERE table_name=?", [view]).fetchone()[0]:
            raise ValueError(f"Required source view missing: {view}")
        present = {str(row[0]) for row in con.execute(f'DESCRIBE "{view}"').fetchall()}
        missing = sorted(expected - present)
        if missing:
            raise ValueError(f"Source view {view} missing required columns: {missing}")
        actual[view] = sorted(present)
    return actual


def duckdb_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_json_value(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [safe_json_value(item) for item in value]
    if isinstance(value, (float, np.floating)): return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.bool_): return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)): return value.isoformat()
    try: return None if pd.isna(value) else value
    except (TypeError, ValueError): return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = safe_json_value(payload)
    Path(path).write_text(json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")




def register_source_views(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    for view, relative in PARQUET_INPUTS.items():
        path = DATA_DIR / relative
        if not path.is_file():
            raise FileNotFoundError(f"Phase 1 input missing: {path}")
        columns = SOURCE_COLUMNS[view]
        projection = ", ".join(quote_identifier(column) for column in columns)
        con.execute(f"CREATE TEMP VIEW {quote_identifier(view)} AS SELECT {projection} FROM read_parquet({duckdb_literal(path)})")
    return validate_required_columns(con, {view: set(columns) for view, columns in SOURCE_COLUMNS.items()})




def input_fingerprints() -> dict[str, str]:
    paths = {**{name: DATA_DIR / rel for name, rel in PARQUET_INPUTS.items()}, "phase1_metrics": PHASE1_METRICS}
    if not PHASE1_METRICS.is_file():
        raise FileNotFoundError(f"Phase 1 metrics missing: {PHASE1_METRICS}")
    return {name: sha256_file(path) for name, path in sorted(paths.items())}


def initialize_connection() -> duckdb.DuckDBPyConnection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=":memory:")
    con.execute("SET memory_limit='28GB'")
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET max_temp_directory_size='0B'")
    return con


# %%
AGGREGATION_SQL: dict[str, str] = {
    "fnd02_date_quality": """
        SELECT 'Contract' AS source, 'Application date' AS date_field, date_apply_state AS date_state,
               count(*) AS source_rows, count(*) FILTER (WHERE date_apply_ts IS NOT NULL) AS parsed_rows,
               0::BIGINT AS sentinel_rows
        FROM contract GROUP BY 1,2,3
        UNION ALL
        SELECT 'Contract', 'Sign date', date_sign_state, count(*),
               count(*) FILTER (WHERE date_sign_ts IS NOT NULL),
               count(*) FILTER (WHERE date_sign_was_sentinel)
        FROM contract GROUP BY 1,2,3
        UNION ALL
        SELECT 'Lead', 'Assignment date', date_assigned_state, count(*),
               count(*) FILTER (WHERE date_assigned_ts IS NOT NULL),
               count(*) FILTER (WHERE date_assigned_was_sentinel)
        FROM leads GROUP BY 1,2,3
        UNION ALL
        SELECT 'Lead', 'Created date', dtime_created_state, count(*),
               count(*) FILTER (WHERE dtime_created_ts IS NOT NULL),
               count(*) FILTER (WHERE dtime_created_was_sentinel)
        FROM leads GROUP BY 1,2,3
    """,
    "fnd02_monthly": """
        SELECT month_start, sum(contract_application_event_rows)::BIGINT AS contract_application_rows,
               sum(lead_event_rows)::BIGINT AS lead_assignment_rows,
               count(*) FILTER (WHERE event_coverage_state='OBSERVED_EVENT_ROWS')::BIGINT AS shops_with_any_recorded_event
        FROM shop_month GROUP BY month_start
    """,
    "fnd03_uuid_multiplicity": """
        SELECT uuid_source_row_count AS source_rows_per_uuid, count(*) AS lead_event_rows,
               sum(1.0 / nullif(uuid_source_row_count,0)) AS uuid_groups_estimate
        FROM leads WHERE lead_uuid IS NOT NULL GROUP BY uuid_source_row_count
    """,
    "fnd03_uuid_variation": """
        WITH repeated AS (
            SELECT lead_uuid,
                   count(*) AS source_rows,
                   count(DISTINCT lead_source_raw) AS distinct_sources,
                   count(DISTINCT lead_product_code) AS distinct_normalized_products,
                   count(DISTINCT lead_product_original_code) AS distinct_original_products,
                   count(DISTINCT lead_status_code_raw) AS distinct_status_codes,
                   count(DISTINCT date_assigned_ts) AS distinct_assignment_timestamps
            FROM leads
            WHERE lead_uuid IS NOT NULL AND uuid_source_row_count > 1
            GROUP BY lead_uuid
        )
        SELECT count(*) AS repeated_uuid_groups,
               sum(source_rows) AS repeated_uuid_event_rows,
               count(*) FILTER (WHERE distinct_sources>1) AS groups_with_source_variation,
               count(*) FILTER (WHERE distinct_normalized_products>1) AS groups_with_normalized_product_variation,
               count(*) FILTER (WHERE distinct_original_products>1) AS groups_with_original_product_variation,
               count(*) FILTER (WHERE distinct_status_codes>1) AS groups_with_status_variation,
               count(*) FILTER (WHERE distinct_assignment_timestamps>1) AS groups_with_assignment_time_variation,
               max(source_rows) AS maximum_rows_per_uuid
        FROM repeated
    """,
    "fnd04_lead_states": """
        SELECT lead_match_state, count(*) AS lead_rows,
               sum(candidate_contract_count)::BIGINT AS candidate_pairs_after_temporal_filters,
               sum(confirmed_match_count)::BIGINT AS confirmed_matches,
               sum(unapproved_product_candidate_count)::BIGINT AS unapproved_product_pairs,
               sum(temporal_fail_candidate_count)::BIGINT AS temporal_fail_pairs,
               count(*) FILTER (WHERE is_ambiguous) AS ambiguous_leads
        FROM leads GROUP BY lead_match_state
    """,
    "fnd04_candidate_quality": """
        SELECT match_status, temporal_state, client_match_state, product_compatibility_state,
               count(*) AS candidate_pairs,
               count(*) FILTER (WHERE is_confirmed_match) AS confirmed_pairs,
               count(*) FILTER (WHERE is_primary_match) AS primary_matches,
               count(*) FILTER (WHERE direct_key_agrees_with_primary) AS direct_key_agrees,
               median(date_diff('day', date_assigned_ts::DATE, contract_apply_ts::DATE))
                   FILTER (WHERE date_assigned_ts IS NOT NULL AND contract_apply_ts IS NOT NULL) AS median_assignment_to_application_lag_days
        FROM candidate GROUP BY 1,2,3,4
    """,
    "fnd04_primary_summary": """
        SELECT count(*) FILTER (WHERE is_confirmed_match) AS confirmed_pairs,
               count(DISTINCT lead_row_id) FILTER (WHERE is_confirmed_match) AS unique_confirmed_lead_rows,
               count(DISTINCT lead_uuid) FILTER (WHERE is_confirmed_match) AS unique_confirmed_uuids,
               count(*) FILTER (WHERE is_primary_match) AS primary_matches,
               count(*) FILTER (WHERE direct_key_agrees_with_primary) AS direct_key_primary_agreements
        FROM candidate
    """,
    "fnd04_conversion_channels": """
        SELECT is_cross_shop, is_cross_category,
               sum(primary_matched_contracts)::BIGINT AS primary_matched_contracts,
               sum(funded_primary_matched_contracts)::BIGINT AS funded_primary_matched_contracts,
               sum(matched_credit_amount_raw) AS matched_credit_amount_raw,
               count(*) AS shop_month_product_groups
        FROM lead_conversion GROUP BY 1,2
    """,
    "fnd04_lag_bins": """
        WITH lags AS (
            SELECT date_diff('day', date_assigned_ts::DATE, contract_apply_ts::DATE) AS lag_days
            FROM candidate WHERE date_assigned_ts IS NOT NULL AND contract_apply_ts IS NOT NULL
        )
        SELECT CASE WHEN lag_days<0 THEN 'Before assignment (invalid temporal order)'
                    WHEN lag_days=0 THEN 'Same day'
                    WHEN lag_days<=7 THEN '1–7 days'
                    WHEN lag_days<=30 THEN '8–30 days'
                    WHEN lag_days<=90 THEN '31–90 days'
                    ELSE '91+ days' END AS lag_bucket,
               count(*) AS candidate_pairs
        FROM lags GROUP BY 1
    """,
    "fnd05_contract_details": """
        SELECT coalesce(goods_category_raw,'(missing category)') AS goods_category,
               coalesce(goods_type_raw,'(missing type)') AS goods_type,
               coalesce(goods_group_raw,'(missing group)') AS goods_group,
               count(*) AS detail_rows, count(DISTINCT skp_credit_case_id) AS credit_cases
        FROM contract_product GROUP BY 1,2,3
    """,
    "fnd06_shop_month_by_shop": """
        SELECT skp_salesroom_id,
               coalesce(salesroom_category,'(unknown category)') AS salesroom_category,
               coalesce(salesroom_model,'(unknown model)') AS salesroom_model,
               coalesce(salesroom_product,'(unknown product)') AS salesroom_product,
               count(*) AS calendar_month_rows,
               count(*) FILTER (WHERE event_coverage_state='OBSERVED_EVENT_ROWS') AS observed_event_months,
               sum(contract_application_event_rows)::BIGINT AS contract_application_rows,
               sum(lead_event_rows)::BIGINT AS lead_assignment_rows,
               avg(contract_application_event_rows) FILTER (WHERE event_coverage_state='OBSERVED_EVENT_ROWS') AS avg_contract_rows_per_observed_month,
               avg(lead_event_rows) FILTER (WHERE event_coverage_state='OBSERVED_EVENT_ROWS') AS avg_lead_rows_per_observed_month,
               median(assigned_employee_count_raw) FILTER (WHERE assignment_interval_rows>0) AS median_raw_assigned_employees,
               count(*) FILTER (WHERE assignment_interval_rows>0) AS months_with_raw_assignment,
               bool_or(shop_master_state='UNMATCHED_CURRENT_SHOP_MASTER') AS has_unmatched_current_shop_master
        FROM shop_month GROUP BY 1,2,3,4
    """,
    "fnd06_shop_behavior": """
        SELECT master_matched_flag, count(*) AS shops,
               median(avg_contracts_per_observed_month) AS median_contracts_per_observed_month,
               median(avg_funded_share) AS median_funded_share,
               median(lead_volume) AS median_lead_volume,
               avg(share_of_months_with_leads) AS mean_share_of_months_with_leads
        FROM shop_behavior GROUP BY master_matched_flag
    """,
    "fnd07_r2_segment_product_role": """
        WITH events AS (
            SELECT c.skp_client_id, c.product_raw AS product_code,
                   'CONTRACT_APPLICATION' AS event_role, c.customer_segment,
                   c.segment_join_eligible, 1::BIGINT AS event_rows
            FROM (
                SELECT f.skp_client_id, f.product_raw, f.after_common_r2_cutoff,
                       s.customer_segment, s.segment_join_eligible
                FROM contract f LEFT JOIN r2_segment s USING (skp_client_id)
            ) c
            WHERE c.after_common_r2_cutoff IS TRUE
            UNION ALL
            SELECT l.skp_client_id, l.lead_product_code, 'LEAD_ORIGIN' AS event_role,
                   s.customer_segment, s.segment_join_eligible, 1::BIGINT
            FROM leads l LEFT JOIN r2_segment s USING (skp_client_id)
            WHERE l.after_common_r2_cutoff IS TRUE
        )
        SELECT event_role, coalesce(customer_segment,'NO_R2_SEGMENT') AS customer_segment,
               coalesce(product_code,'(missing product)') AS product_code,
               count(*) AS raw_event_rows,
               count(DISTINCT skp_client_id) AS distinct_event_customers,
               count(*) FILTER (WHERE segment_join_eligible) AS segment_eligible_event_rows,
               count(DISTINCT skp_client_id) FILTER (WHERE segment_join_eligible) AS segment_eligible_customers
        FROM events GROUP BY 1,2,3
    """,
    "fnd08_employee_interval_states": """
        SELECT assignment_interval_state, code_status_raw,
               count(*) AS assignment_rows,
               count(DISTINCT skp_employee_id) AS distinct_employee_ids,
               count(DISTINCT skp_salesroom_id) AS distinct_shop_ids,
               count(*) FILTER (WHERE overlaps_prior_interval) AS overlap_rows,
               count(*) FILTER (WHERE status_is_approved_active) AS approved_active_status_rows
        FROM employee GROUP BY 1,2
    """,
    "fnd09_dpd_availability": """
        SELECT date_trunc('quarter', date_apply_ts)::DATE AS application_quarter,
               count(*) AS application_rows,
               count(dpd_1pd_raw) AS dpd_1pd_nonnull_rows,
               count(dpd_2pd_raw) AS dpd_2pd_nonnull_rows,
               count(dpd_3pd_raw) AS dpd_3pd_nonnull_rows,
               count(dpd_4pd_raw) AS dpd_4pd_nonnull_rows
        FROM contract WHERE date_apply_ts IS NOT NULL GROUP BY 1
    """,
}
SQL_AGGREGATE_DEPENDENCIES = {
    "fnd02_date_quality": {"contract", "leads"}, "fnd02_monthly": {"shop_month"},
    "fnd03_uuid_multiplicity": {"leads"}, "fnd03_uuid_variation": {"leads"},
    "fnd04_lead_states": {"leads"}, "fnd04_candidate_quality": {"candidate"},
    "fnd04_primary_summary": {"candidate"}, "fnd04_lag_bins": {"candidate"},
    "fnd05_contract_details": {"contract_product"}, "fnd06_shop_month_by_shop": {"shop_month"},
    "fnd06_shop_behavior": {"shop_behavior"},
    "fnd04_conversion_channels": {"lead_conversion"},
    "fnd07_r2_segment_product_role": {"contract", "leads", "r2_segment"},
    "fnd08_employee_interval_states": {"employee"}, "fnd09_dpd_availability": {"contract"},
}


# %%
def sql_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def aggregate_signature(name: str, inputs: dict[str, str], dependencies: set[str], logic_hash: str) -> str:
    used = {key: inputs[key] for key in sorted(dependencies)}
    return cache_signature({"inputs": used, "logic": logic_hash}, TRANSFORMATION_VERSION + ":" + name)


def reusable_legacy_aggregate_signature(name: str, query: str, inputs: dict[str, str],
                                         dependencies: set[str], previous: dict[str, Any]) -> str | None:
    if previous.get("transformation_version") != TRANSFORMATION_VERSION:
        return None
    old_inputs = previous.get("inputs", {})
    if any(old_inputs.get(key) != inputs.get(key) for key in dependencies):
        return None
    old_record = previous.get("aggregates", {}).get(name, {})
    legacy = cache_signature({"base": previous.get("base_signature"), "sql": sql_hash(query)},
                             TRANSFORMATION_VERSION + ":" + name)
    return legacy if old_record.get("signature") == legacy else None


def install_cached_view(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    existing = con.execute("SELECT table_type FROM information_schema.tables WHERE table_name=?", [name]).fetchone()
    if existing:
        kind = "VIEW" if existing[0] == "VIEW" else "TABLE"
        con.execute(f"DROP {kind} IF EXISTS {quote_identifier(name)}")
    columns = pq.ParquetFile(path).schema_arrow.names
    projection = ", ".join(quote_identifier(column) for column in columns)
    con.execute(f"CREATE TEMP VIEW {quote_identifier(name)} AS SELECT {projection} FROM read_parquet({duckdb_literal(path)})")


def create_aggregate(con: duckdb.DuckDBPyConnection, name: str, query: str, signature: str,
                     manifest: dict[str, Any], *, legacy_signature: str | None = None) -> dict[str, Any]:
    path = CACHE_DIR / f"{name}.parquet"
    old = manifest.get("aggregates", {}).get(name, {})
    reusable_signature = signature if old.get("signature") == signature else legacy_signature
    if (reusable_signature is not None and old.get("signature") == reusable_signature
            and path.is_file() and old.get("sha256") == sha256_file(path)):
        install_cached_view(con, name, path)
        old["signature"] = signature
        return {"name": name, "cache": "hit", "path": path.relative_to(OUTPUT_DIR).as_posix(),
                "rows": old.get("rows"), "sha256": old["sha256"]}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {quote_identifier(name)} AS {query}")
    con.execute(f"COPY {quote_identifier(name)} TO {duckdb_literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {CACHE_ROW_GROUP_SIZE})")
    record = {"name": name, "cache": "miss", "path": path.relative_to(OUTPUT_DIR).as_posix(),
              "rows": int(pq.ParquetFile(path).metadata.num_rows), "sha256": sha256_file(path)}
    manifest.setdefault("aggregates", {})[name] = {"signature": signature, "rows": record["rows"], "sha256": record["sha256"]}
    return record


def _frames_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    if set(left.columns) != set(right.columns):
        return False
    columns = sorted(left.columns)
    left = left[columns].sort_values(columns, na_position="first", kind="stable").reset_index(drop=True)
    right = right[columns].sort_values(columns, na_position="first", kind="stable").reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-12)
        return True
    except AssertionError:
        return False


def cache_dataframe(con: duckdb.DuckDBPyConnection, name: str, frame: pd.DataFrame, signature: str,
                    manifest: dict[str, Any]) -> dict[str, Any]:
    path = CACHE_DIR / f"{name}.parquet"
    old = manifest.get("aggregates", {}).get(name, {})
    if path.is_file() and old.get("sha256") == sha256_file(path) and _frames_equal(frame, pd.read_parquet(path)):
        install_cached_view(con, name, path)
        old["signature"] = signature
        return {"name": name, "cache": "hit", "path": path.relative_to(OUTPUT_DIR).as_posix(),
                "rows": old.get("rows"), "sha256": old["sha256"]}
    con.register("_eda_metrics_frame", frame)
    try:
        columns = ", ".join(quote_identifier(column) for column in frame.columns)
        return create_aggregate(con, name, f"SELECT {columns} FROM _eda_metrics_frame", signature, manifest)
    finally:
        con.unregister("_eda_metrics_frame")


def load_aggregate_frame(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    schema = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {quote_identifier(name)}").fetchall()]
    projection = ", ".join(quote_identifier(column) for column in schema)
    return con.execute(f"SELECT {projection} FROM {quote_identifier(name)}").df()


def display_label(value: Any) -> str:
    text = str(value)
    return DISPLAY_LABELS.get(text, text.replace("_", " ").title())


def build_fnd01_metrics(metrics: dict[str, Any]) -> pd.DataFrame:
    coverage = pd.DataFrame(metrics.get("coverage_summary", []))
    columns = ["label", "coverage_pct", "numerator", "denominator", "status", "details"]
    if coverage.empty:
        return pd.DataFrame(columns=columns)
    selected = coverage.loc[coverage.population.isin(DISPLAY_LABELS)].copy()
    selected["label"] = selected.population.map(DISPLAY_LABELS)
    selected = selected[columns]
    schema = pd.DataFrame(metrics.get("schema_validation", []))
    if schema.empty:
        return selected
    parity = schema.groupby("dataset", as_index=False).agg(
        numerator=("schema_status", lambda values: int((values == "PRESENT").sum())),
        denominator=("schema_status", "size"))
    parity["label"] = "Schema documented · " + parity.dataset.str.replace("_", " ").str.title()
    parity["coverage_pct"] = 100 * parity.numerator / parity.denominator.clip(lower=1)
    parity["status"] = "SCHEMA_PARITY"
    parity["details"] = "Source fields present in StructureTable.xlsx."
    return pd.concat([selected, parity[columns]], ignore_index=True)


def build_fnd03_weight_metrics(metrics: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(metrics.get("weight_audit", []))
    if frame.empty:
        return pd.DataFrame(columns=["lead_source_raw", "lead_product_code", "lead_product_original_code", "sample_weight", "source_rows", "raw_weight_sensitivity_sum_qa_only"])
    return frame.groupby(["lead_source_raw", "lead_product_code", "lead_product_original_code", "sample_weight"], dropna=False, as_index=False).agg(
        source_rows=("source_rows", "sum"), raw_weight_sensitivity_sum_qa_only=("raw_weight_sensitivity_sum_qa_only", "sum"))


def build_insights(aggregates: dict[str, pd.DataFrame], metrics: dict[str, Any]) -> str:
    coverage = aggregates["fnd01_coverage"].set_index("label")
    dateq, uuid = aggregates["fnd02_date_quality"], aggregates["fnd03_uuid_variation"].iloc[0]
    weights, primary = aggregates["fnd03_weights"], aggregates["fnd04_primary_summary"].iloc[0]
    conversion = aggregates["fnd04_conversion_channels"]
    crosswalk = aggregates["fnd05_crosswalk"]
    lag_bins = aggregates["fnd04_lag_bins"]
    behavior = aggregates["fnd06_shop_behavior"].set_index("master_matched_flag")
    roles = aggregates["fnd07_r2_segment_product_role"].groupby("event_role").agg(
        events=("raw_event_rows", "sum"), eligible=("segment_eligible_event_rows", "sum"))
    employee, dpd = aggregates["fnd08_employee_interval_states"], aggregates["fnd09_dpd_availability"]
    status = pd.DataFrame(metrics.get("contract_status_mapping", []))
    outcomes = status.groupby("business_outcome").source_rows.sum() if not status.empty else pd.Series(dtype=float)
    rejected, cancelled, written_off = (int(outcomes.get(key, 0)) for key in ("REJECTED", "CANCELLED", "WRITTEN_OFF"))
    total_contracts = int(status.source_rows.sum()) if not status.empty else 0
    funded_share = 100 * float(metrics.get("funded_shares", {}).get("STATUS_MAP") or 0)
    nonprimary = {row["attribution"]: int(row["nonprimary_pairs"]) for row in metrics.get("nonprimary_pair_uuid_attribution", [])}
    invalid_dates = int(dateq.loc[dateq.date_state.isin(["INVALID", "MISSING", "SENTINEL_OPEN_ENDED"]), "source_rows"].sum())
    high_weights = weights.loc[weights.sample_weight > 1].sort_values("source_rows", ascending=False)
    high_codes = " / ".join(high_weights.lead_product_original_code.astype(str).head(3)) or "none"
    contract_cov = coverage.loc[DISPLAY_LABELS["CONTRACT_TO_CURRENT_SHOP"]] if DISPLAY_LABELS["CONTRACT_TO_CURRENT_SHOP"] in coverage.index else None
    lead_cov = coverage.loc[DISPLAY_LABELS["LEAD_TO_CURRENT_SHOP"]] if DISPLAY_LABELS["LEAD_TO_CURRENT_SHOP"] in coverage.index else None
    matched = behavior.loc[True] if True in behavior.index else None
    unmatched = behavior.loc[False] if False in behavior.index else None
    contract_role = roles.loc["CONTRACT_APPLICATION"] if "CONTRACT_APPLICATION" in roles.index else None
    lead_role = roles.loc["LEAD_ORIGIN"] if "LEAD_ORIGIN" in roles.index else None
    dpd_fields = [column for column in dpd.columns if column.endswith("_nonnull_rows")]
    dpd_values = "; ".join(f"{display_label(column)} {int(dpd[column].sum()):,}" for column in dpd_fields)
    def pct(numerator: Any, denominator: Any) -> str:
        return "n/a" if denominator is None or not denominator else f"{100*float(numerator)/float(denominator):.1f}%"
    def section(fid: str, insight: str, evidence: str, implication: str, limitations: str) -> str:
        return (f"## {fid}\n\n![{fid}]({fid.lower()}.png)\n\n**Insight:** {insight}\n\n"
                f"**Evidence:** {evidence}\n\n**Implication:** {implication}\n\n**Limitations:** {limitations}")
    sections = [
        section("FND_01", "Shop attribution is incomplete; configured product and date rules yield confirmed primary attribution.",
                f"Current-master coverage: contracts {pct(contract_cov.numerator,contract_cov.denominator) if contract_cov is not None else 'n/a'}; leads {pct(lead_cov.numerator,lead_cov.denominator) if lead_cov is not None else 'n/a'}. Confirmed pairs {int(primary.confirmed_pairs):,}; primary matches {int(primary.primary_matches):,}.",
                "Keep unmatched shop IDs visible and state denominators for every comparison.", "Current master is a snapshot; exact product mappings are competition assumptions."),
        section("FND_02", "Contract and lead event windows differ, and sentinel dates are not valid event dates.",
                f"{invalid_dates:,} date-field values are missing, invalid or sentinel. Round 2 common cutoff: {metrics.get('round2_cutoffs',{}).get('common_cutoff')}.",
                "Use complete observed periods and keep gaps distinct from zero activity.", "Date validity does not establish outcome maturity."),
        section("FND_03", "Repeated UUIDs and the concentrated weight cell affect lead-row interpretation.",
                f"{int(uuid.repeated_uuid_groups):,} repeated UUID groups span {int(uuid.repeated_uuid_event_rows):,} rows. {int(high_weights.source_rows.sum()) if not high_weights.empty else 0:,} rows have weight >1, concentrated in {high_codes}; weights remain QA-only.",
                "Report raw events and unique UUIDs separately; do not interpret weights as population totals.", "UUID version semantics and the weight estimator remain unresolved."),
        section("FND_04", "Primary attribution credits each confirmed contract once; excess pairs mostly link distinct UUIDs.",
                f"{int(primary.confirmed_pairs):,} confirmed pairs; {int(primary.primary_matches):,} primary matches; {int(primary.confirmed_pairs-primary.primary_matches):,} nonprimary pairs ({nonprimary.get('SAME_UUID_REPEAT',0):,} same UUID, {nonprimary.get('DIFFERENT_LEAD_UUID',0):,} different UUID). Lag buckets: {'; '.join(f'{row.lag_bucket} {int(row.candidate_pairs):,}' for row in lag_bins.itertuples(index=False))}.",
                "Conversion denominators need a declared lead event/UUID grain, not candidate-pair counts; matched credit amounts remain raw application amounts.", "Repeated UUID rows remain undeduplicated because their event/version meaning is unknown."),
        section("FND_05", "TW, CL, CC and CD use configured exact-code mappings; REL remains unmapped.",
                f"Configured-compatible lead rows {int(crosswalk.loc[crosswalk.mapping_status=='APPROVED_COMPATIBLE','lead_rows'].sum()) if not crosswalk.empty else 0:,}; contract detail rows {int(metrics.get('join_reconciliation',{}).get('contract_product_detail_rows',0)):,}.",
                "Show product codes and map scope in product comparisons.", "These four mappings are competition assumptions, not owner-validated compatibility."),
        section("FND_06", "The shop behavior profile includes fact shops with and without master attributes.",
                f"Matched shops {int(matched.shops) if matched is not None else 0:,}; unmatched {int(unmatched.shops) if unmatched is not None else 0:,}. Median contracts/month: {float(matched.median_contracts_per_observed_month) if matched is not None else 0:.2f} vs {float(unmatched.median_contracts_per_observed_month) if unmatched is not None else 0:.2f}.",
                "Use these as descriptive peer context, not causal capacity or future potential.", "Unmatched attributes remain unknown; current master is not historical."),
        section("FND_07", "Round 2 Customer Profile labels cover a subset of post-cutoff events.",
                f"Contract events eligible {int(contract_role.eligible):,}/{int(contract_role.events):,} ({pct(contract_role.eligible,contract_role.events)}); leads {int(lead_role.eligible):,}/{int(lead_role.events):,} ({pct(lead_role.eligible,lead_role.events)}); cutoff {metrics.get('round2_cutoffs',{}).get('common_cutoff')}.",
                "Report event and distinct-customer denominators separately.", "Feature timestamp lineage and representativeness remain unverified."),
        section("FND_08", "Code A contributes a provisional active-assignment proxy.",
                f"Configured active-status assignment rows {int(employee.approved_active_status_rows.sum()):,}; overlapping intervals {int(employee.overlap_rows.sum()):,}.",
                "Treat assignments as administrative coverage, not FTE or selling capacity.", "Code A is provisional and interval overlaps remain visible."),
        section("FND_09", "DPD fields are populated, but checkpoint maturity is unknown.",
                f"Dated applications {int(dpd.application_rows.sum()):,}; non-null checkpoint values: {dpd_values}. Status snapshot: funded-origin {funded_share:.2f}%, rejected {pct(rejected,total_contracts)}, cancelled {pct(cancelled,total_contracts)}, written off {pct(written_off,total_contracts)} of all contracts.",
                "Do not interpret field presence as a default rate or matured outcome.", "Checkpoint timing, extract date and follow-up duration are undocumented."),
    ]
    return "# BI10 Round 3 — Phase 2 EDA\n\n" + "\n\n".join(sections)


def validate_layout(fig: plt.Figure, fid: str) -> list[dict[str, Any]]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.bbox.width, fig.bbox.height
    artists = list(fig.texts)
    for ax in fig.axes:
        artists.extend(ax.texts)
        artists.extend([item for item in ax.get_xticklabels() + ax.get_yticklabels() if item.get_visible()])
        artists.extend([ax.xaxis.label, ax.yaxis.label])
    boxes = []
    seen = set()
    for artist in artists:
        if id(artist) in seen:
            continue
        seen.add(id(artist))
        text = getattr(artist, "get_text", lambda: "")()
        if not text or not text.strip():
            continue
        try:
            box = artist.get_window_extent(renderer)
        except Exception:
            continue
        if box.width > 1 and box.height > 1:
            boxes.append((text, box))
    issues = []
    for text, box in boxes:
        x0, y0, x1, y1 = box.x0 / width, box.y0 / height, box.x1 / width, box.y1 / height
        if x0 < -0.001 or y0 < -0.001 or x1 > 1.001 or y1 > 1.001:
            issues.append({"figure": fid, "kind": "out_of_page", "text": text[:80],
                           "bbox": [round(value, 4) for value in (x0, y0, x1, y1)]})
    for index, (text_a, box_a) in enumerate(boxes):
        for text_b, box_b in boxes[index + 1:]:
            overlap_w = min(box_a.x1, box_b.x1) - max(box_a.x0, box_b.x0)
            overlap_h = min(box_a.y1, box_b.y1) - max(box_a.y0, box_b.y0)
            smaller = min(box_a.width * box_a.height, box_b.width * box_b.height)
            if overlap_w > 1 and overlap_h > 1 and smaller > 0 and overlap_w * overlap_h / smaller > 0.18:
                issues.append({"figure": fid, "kind": "text_overlap", "text": f"{text_a[:38]!r} / {text_b[:38]!r}"})
    LAYOUT_WARNINGS.extend(issues)
    return issues


def save_figure(fig: plt.Figure, figure_id: str, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{figure_id.lower()}.png"
    fig.savefig(path, format="png", dpi=150, facecolor=COLORS["white"], edgecolor=COLORS["white"], transparent=False)
    plt.close(fig)
    return path


def _compact_chart(figure_id: str, aggregates: dict[str, pd.DataFrame]):
    title = DISPLAY_LABELS[f"TITLE:{figure_id}"]
    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=150, facecolor=COLORS["white"])
    axes = [ax]
    primary, secondary, risk = COLORS["primary"], COLORS["secondary"], COLORS["risk"]
    if figure_id == "FND_01":
        data = aggregates["fnd01_coverage"].query("status != 'SCHEMA_PARITY'").sort_values("coverage_pct")
        labels = data.label.map(display_label).tolist()
        values = data.coverage_pct.fillna(0).to_numpy(dtype=float)
        bars = ax.barh(labels, values, color=[risk if value == 0 else primary for value in values])
        ax.set_xlim(0, 125)
        ax.set_xlabel("Share of stated denominator")
        ax.bar_label(bars, labels=[f"{value:.1f}% ({int(n):,}/{int(d):,})" for value, n, d in zip(values, data.numerator, data.denominator)], padding=3, fontsize=7)
    elif figure_id == "FND_02":
        data = aggregates["fnd02_monthly"].copy()
        data["month_start"] = pd.to_datetime(data.month_start)
        ax.plot(data.month_start, data.contract_application_rows, color=primary, linewidth=1.8, label="Contract applications")
        ax.plot(data.month_start, data.lead_assignment_rows, color=secondary, linewidth=1.8, label="Lead assignments")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.yaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
        ax.set_ylabel("Observed event rows")
        ax.legend(frameon=False, fontsize=8)
    elif figure_id == "FND_03":
        data = aggregates["fnd03_weights"].query("sample_weight > 1").sort_values("source_rows")
        labels = data.lead_product_original_code.map(display_label).tolist()
        values = data.source_rows.to_numpy(dtype=float)
        bars = ax.barh(labels, values, color=risk)
        ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel("Lead rows in unvalidated weight cells")
        ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=3, fontsize=8)
    elif figure_id == "FND_04":
        data = aggregates["fnd04_candidate_quality"].groupby("match_status", as_index=False).candidate_pairs.sum().sort_values("candidate_pairs")
        labels = data.match_status.map(display_label).tolist()
        values = data.candidate_pairs.to_numpy(dtype=float)
        bars = ax.barh(labels, values, color=[primary if label == "MATCHED" else risk for label in data.match_status])
        ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel("Criterion-qualified candidate pairs")
        ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=3, fontsize=8)
    elif figure_id == "FND_05":
        data = aggregates["fnd05_crosswalk"].sort_values("lead_rows")
        labels = data.lead_product_code.map(display_label).tolist()
        values = data.lead_rows.to_numpy(dtype=float)
        bars = ax.barh(labels, values, color=[primary if status == "APPROVED_COMPATIBLE" else risk for status in data.mapping_status])
        ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel("Observed lead rows")
        ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=3, fontsize=8)
    elif figure_id == "FND_06":
        data = aggregates["fnd06_shop_behavior"].sort_values("master_matched_flag")
        labels = ["Unmatched master" if not value else "Master matched" for value in data.master_matched_flag]
        x = np.arange(len(data))
        width = 0.34
        a1 = ax.bar(x - width/2, data.median_contracts_per_observed_month, width, color=primary, label="Median contracts/month")
        a2 = ax.bar(x + width/2, data.median_lead_volume, width, color=secondary, label="Median lead rows")
        ax.set_xticks(x, labels)
        ax.set_ylabel("Median observed volume")
        ax.legend(frameon=False, fontsize=8)
        ax.bar_label(a1, fmt="%.1f", padding=2, fontsize=7)
        ax.bar_label(a2, fmt="%.1f", padding=2, fontsize=7)
    elif figure_id == "FND_07":
        data = aggregates["fnd07_r2_segment_product_role"].groupby("event_role", as_index=False).agg(
            events=("raw_event_rows", "sum"), eligible=("segment_eligible_event_rows", "sum"))
        labels = data.event_role.map(display_label).tolist()
        values = 100 * data.eligible.to_numpy(dtype=float) / np.maximum(data.events.to_numpy(dtype=float), 1)
        bars = ax.barh(labels, values, color=[primary, secondary][:len(values)])
        ax.set_xlim(0, 100)
        ax.xaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_xlabel("Profile-eligible share of post-cutoff events")
        ax.bar_label(bars, labels=[f"{value:.1f}%" for value in values], padding=3, fontsize=8)
    elif figure_id == "FND_08":
        data = aggregates["fnd08_employee_interval_states"].groupby("code_status_raw", as_index=False).assignment_rows.sum().sort_values("assignment_rows")
        labels = data.code_status_raw.map(display_label).tolist()
        values = data.assignment_rows.to_numpy(dtype=float)
        bars = ax.barh(labels, values, color=[primary, risk][:len(values)])
        ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel("Assignment rows by raw status code")
        ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=3, fontsize=8)
    else:
        data = aggregates["fnd09_dpd_availability"]
        fields = ["dpd_1pd_nonnull_rows", "dpd_2pd_nonnull_rows", "dpd_3pd_nonnull_rows", "dpd_4pd_nonnull_rows"]
        total = max(float(data.application_rows.sum()), 1.0)
        values = np.array([100 * float(data[field].sum()) / total for field in fields])
        labels = [display_label(field) for field in fields]
        bars = ax.barh(labels, values, color=[primary, secondary, COLORS["mid"], COLORS["muted"]])
        ax.set_xlim(0, 100)
        ax.xaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_xlabel("Applications with non-null checkpoint field")
        ax.bar_label(bars, labels=[f"{value:.1f}%" for value in values], padding=3, fontsize=8)
    for axis in axes:
        axis.set_title(title, loc="left", color=COLORS["primary"], fontsize=11, fontweight="bold")
        axis.set_axisbelow(True)
        axis.grid(axis="x" if figure_id not in {"FND_02", "FND_06"} else "y", color=COLORS["grid"], linewidth=0.5)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(length=0, labelsize=8)
    fig.tight_layout()
    validate_layout(fig, figure_id)
    return fig, title


def validate_aggregate_totals(aggregates: dict[str,pd.DataFrame], metrics: dict[str,Any]) -> list[dict[str,Any]]:
    reconciliation=metrics.get("join_reconciliation",{})
    published=metrics.get("published_parquet_row_counts",{})
    internal=metrics.get("internal_audit_table_row_counts",{})
    inventory={row.get("dataset"):row.get("source_rows") for row in metrics.get("raw_inventory",[])}
    checks=[]
    def compare(name: str, observed: Any, expected: Any) -> None:
        observed=int(observed or 0); expected=int(expected or 0)
        checks.append({"check":name,"status":"PASS" if observed==expected else "FAIL",
                       "observed_rows":observed,"expected_rows":expected,"delta":observed-expected})
    monthly=aggregates["fnd02_monthly"]
    compare("contract_month_events_reconcile",monthly.contract_application_rows.sum(),reconciliation.get("contract_month_event_rows"))
    compare("lead_month_events_reconcile",monthly.lead_assignment_rows.sum(),reconciliation.get("lead_month_event_rows"))
    compare("lead_state_rows_reconcile",aggregates["fnd04_lead_states"].lead_rows.sum(),published.get("leads_clean"))
    compare("candidate_pairs_reconcile",aggregates["fnd04_candidate_quality"].candidate_pairs.sum(),published.get("lead_contract_candidates"))
    compare("contract_product_details_reconcile",aggregates["fnd05_contract_details"].detail_rows.sum(),reconciliation.get("contract_product_detail_rows"))
    shop=aggregates["fnd06_shop_month_by_shop"]
    compare("shop_month_contract_rows_reconcile",shop.contract_application_rows.sum(),reconciliation.get("foundation_contract_event_rows"))
    compare("shop_month_lead_rows_reconcile",shop.lead_assignment_rows.sum(),reconciliation.get("foundation_lead_event_rows"))
    compare("employee_interval_rows_reconcile",aggregates["fnd08_employee_interval_states"].assignment_rows.sum(),inventory.get("employee_assignment"))
    compare("dpd_vintage_rows_reconcile",aggregates["fnd09_dpd_availability"].application_rows.sum(),reconciliation.get("dated_contract_fact_rows"))
    compare("uuid_multiplicity_events_reconcile",aggregates["fnd03_uuid_multiplicity"].lead_event_rows.sum(),published.get("leads_clean"))
    compare("phase1_internal_lead_summary_reconcile",internal.get("lead_match_summary"),published.get("leads_clean"))
    if "fnd04_primary_summary" in aggregates:
        primary = aggregates["fnd04_primary_summary"].iloc[0]
        compare("primary_matches_reconcile",primary.primary_matches,metrics.get("primary_lead_contract_matches"))
        compare("confirmed_pairs_reconcile",primary.confirmed_pairs,metrics.get("confirmed_lead_contract_pairs"))
    if "fnd04_conversion_channels" in aggregates:
        compare("conversion_primary_matches_reconcile",aggregates["fnd04_conversion_channels"].primary_matched_contracts.sum(),metrics.get("primary_lead_contract_matches"))
    if "fnd06_shop_behavior" in aggregates:
        compare("shop_behavior_profile_rows_reconcile",aggregates["fnd06_shop_behavior"].shops.sum(),published.get("shop_behavior_profile"))
    return checks
def clean_eda_outputs(aggregate_names: set[str]) -> None:
    allowed_root = {"eda_insights.md", "eda_summary.json", *(f"{figure_id.lower()}.png" for figure_id in FIGURE_IDS), "cache"}
    for path in OUTPUT_DIR.iterdir():
        if path.name in allowed_root:
            continue
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    allowed_cache = {"cache_manifest.json", *(f"{name}.parquet" for name in aggregate_names)}
    for path in CACHE_DIR.iterdir():
        if path.name in allowed_cache:
            continue
        shutil.rmtree(path) if path.is_dir() else path.unlink()

def main() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    metrics = read_json(PHASE1_METRICS)
    phase1_validation = read_json(PHASE1_VALIDATION)
    if phase1_validation.get("execution_status") != "SUCCESS" or phase1_validation.get("fatal_failures"):
        raise RuntimeError("Phase 1 validation status is not SUCCESS; stopping before EDA.")
    fingerprints = input_fingerprints()
    manifest_path = CACHE_DIR / "cache_manifest.json"
    try:
        previous_manifest = read_json(manifest_path)
    except (OSError, json.JSONDecodeError):
        previous_manifest = {}
    cache_manifest = json.loads(json.dumps(previous_manifest))
    con = initialize_connection()
    try:
        register_source_views(con)
        metrics_frames = {
            "fnd01_coverage": build_fnd01_metrics(metrics),
            "fnd03_weights": build_fnd03_weight_metrics(metrics),
            "fnd05_crosswalk": pd.DataFrame(metrics.get("product_crosswalk", [])),
        }
        for name, frame in metrics_frames.items():
            frame_hash = hashlib.sha256(frame.to_json(orient="records", date_format="iso").encode("utf-8")).hexdigest()
            signature = aggregate_signature(name, {}, set(), frame_hash)
            cache_dataframe(con, name, frame, signature, cache_manifest)
        for name, query in AGGREGATION_SQL.items():
            dependencies = SQL_AGGREGATE_DEPENDENCIES[name]
            signature = aggregate_signature(name, fingerprints, dependencies, sql_hash(query))
            legacy = reusable_legacy_aggregate_signature(name, query, fingerprints, dependencies, previous_manifest)
            create_aggregate(con, name, query, signature, cache_manifest, legacy_signature=legacy)
        aggregate_names = set(metrics_frames) | set(AGGREGATION_SQL)
        aggregate_data = {name: load_aggregate_frame(con, name) for name in sorted(aggregate_names)}
        aggregate_validation = validate_aggregate_totals(aggregate_data, metrics)
        LAYOUT_WARNINGS.clear()
        figures = []
        for figure_id in FIGURE_IDS:
            fig, title = _compact_chart(figure_id, aggregate_data)
            png = save_figure(fig, figure_id)
            figures.append({"figure_id": figure_id, "title": title, "file": png.name})
        (OUTPUT_DIR / "eda_insights.md").write_text(build_insights(aggregate_data, metrics) + "\n", encoding="utf-8")
        reconciliation = metrics.get("join_reconciliation", {})
        amount_deltas = [float(value or 0) for key, value in reconciliation.items() if key.endswith("_delta")]
        cutoff = metrics.get("round2_cutoffs", {}).get("common_cutoff")
        checks = {
            "phase1_amount_deltas_zero": all(value == 0 for value in amount_deltas),
            "source_event_rows_match_phase1": (reconciliation.get("contract_raw_rows") == metrics.get("published_parquet_row_counts", {}).get("contract_fact")
                                                and reconciliation.get("lead_raw_rows") == metrics.get("published_parquet_row_counts", {}).get("leads_clean")),
            "aggregate_totals_match_phase1": all(item["status"] == "PASS" for item in aggregate_validation),
            "r2_cutoff_present": bool(cutoff),
            "all_nine_fnd_figures_present": len(figures) == 9 and all((OUTPUT_DIR / item["file"]).is_file() for item in figures),
            "figure_layout_clean": not LAYOUT_WARNINGS,
        }
        failed = [name for name, passed in checks.items() if not passed]
        failed.extend(item["check"] for item in aggregate_validation if item["status"] != "PASS")
        source_rows = {row.get("dataset"): row.get("source_rows") for row in metrics.get("raw_inventory", [])}
        summary = {
            "phase": "Phase 2 — Exploratory Data Analysis only",
            "execution_status": "SUCCESS" if not failed else "VALIDATION_WARNING",
            "figure_count": len(figures), "figures": figures,
            "validation": {"reconciliation": checks, "aggregate_checks": aggregate_validation, "failed_checks": failed},
            "warnings": [
                "TW/CL/CC/CD product links and status-based funded outcomes are configured assumptions, not owner approvals.",
                "Employee code A is a provisional assignment-status proxy; it is not FTE or validated selling capacity.",
                "sample_weight is QA-only and is not used as a population estimator.",
                "DPD fields are not matured delinquency outcomes; shop/seller attributes are current snapshots.",
            ],
            "number_traceability": {
                "phase1_run_id": metrics.get("run_id"), "phase1_source_row_counts": source_rows,
                "phase1_published_table_rows": metrics.get("published_parquet_row_counts", {}),
                "aggregate_row_counts": {name: int(len(frame)) for name, frame in aggregate_data.items()},
                "confirmed_pairs": metrics.get("confirmed_lead_contract_pairs"),
                "primary_matches": metrics.get("primary_lead_contract_matches"),
                "nonprimary_pair_uuid_attribution": metrics.get("nonprimary_pair_uuid_attribution", []),
                "funded_shares": metrics.get("funded_shares", {}),
            },
            "input_fingerprints": fingerprints,
            "figure_layout_warnings": LAYOUT_WARNINGS,
        }
        write_json(OUTPUT_DIR / "eda_summary.json", summary)
        clean_eda_outputs(aggregate_names)
        cache_manifest["transformation_version"] = TRANSFORMATION_VERSION
        cache_manifest["base_signature"] = cache_signature(fingerprints, TRANSFORMATION_VERSION)
        cache_manifest["inputs"] = fingerprints
        cache_manifest["aggregates"] = {name: cache_manifest.get("aggregates", {})[name] for name in sorted(aggregate_names)}
        write_json(manifest_path, cache_manifest)
        return summary
    finally:
        con.close()


if __name__ == "__main__":
    result = main()
    failed_count = len(result["validation"]["failed_checks"])
    print(f"{result['execution_status']} | figures={result['figure_count']} | failed_checks={failed_count}")
