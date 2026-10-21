# %% [markdown]
# # 1. Data processing — Phase 1 Foundation
#
# Read-only ingestion and auditable transformation of Round 3 source files. This
# stage inventories and profiles inputs, preserves source rows, normalizes keys
# and dates, builds one-to-one/one-to-many bridges without fact inflation, and
# writes the compact cleaned tables and audit metadata under `Data_clean/`, with
# Round 2-derived segment outputs isolated in `Data_clean/R2/`.
#
# Business definitions are explicit configuration assumptions; unresolved status
# and sample-weight semantics remain visible. This stage stops before EDA,
# forecasting, prioritization, recommendations, and figures.

# %%
from __future__ import annotations

from contextlib import contextmanager
import ast
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow.parquet as pq

try:
    import psutil
except ImportError:  # Optional; stage RSS is null when unavailable.
    psutil = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Code.config import config as C  # noqa: E402
from Code.config.utils import (  # noqa: E402
    csv_scan_sql,
    ensure_dirs,
    get_con,
    normalize_key_sql,
    quote_identifier,
    save_json,
    sql_literal,
    timestamp_sql_expression,
)



class StageProfiler:
    """Measure wall time and sampled process RSS for major ETL stages."""

    def __init__(self, sample_interval_seconds: float = 0.25):
        self.sample_interval_seconds = max(0.01, float(sample_interval_seconds))
        self.records: list[dict[str, Any]] = []
        self._process = psutil.Process(os.getpid()) if psutil is not None else None

    def _rss_bytes(self) -> int | None:
        if self._process is None:
            return None
        try:
            return int(self._process.memory_info().rss)
        except (OSError, psutil.Error):
            return None

    @contextmanager
    def measure(self, stage: str):
        started = time.perf_counter()
        rss_start = self._rss_bytes()
        sampled_peak = rss_start
        samples = 0
        stop = threading.Event()

        def sample_memory() -> None:
            nonlocal sampled_peak, samples
            while not stop.wait(self.sample_interval_seconds):
                current = self._rss_bytes()
                if current is not None:
                    sampled_peak = current if sampled_peak is None else max(sampled_peak, current)
                    samples += 1

        sampler = threading.Thread(target=sample_memory, name=f"rss-{stage}", daemon=True)
        if self._process is not None:
            sampler.start()
        try:
            yield
        finally:
            stop.set()
            if self._process is not None:
                sampler.join(timeout=max(0.05, self.sample_interval_seconds * 2))
            rss_end = self._rss_bytes()
            if rss_end is not None:
                sampled_peak = rss_end if sampled_peak is None else max(sampled_peak, rss_end)
            self.records.append({
                "stage": stage,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "rss_start_bytes": rss_start,
                "rss_sampled_peak_bytes": sampled_peak,
                "rss_end_bytes": rss_end,
                "rss_peak_delta_bytes": None if rss_start is None or sampled_peak is None else max(0, sampled_peak - rss_start),
                "rss_samples": samples,
                "memory_measurement": "psutil_sampled_rss" if self._process is not None else "unavailable",
            })


def measure_call(profiler: StageProfiler, stage: str, operation, *args, **kwargs):
    with profiler.measure(stage):
        return operation(*args, **kwargs)

RAW_TABLE_BY_DATASET = {
    "contract": "raw_contract",
    "leads": "raw_leads",
    "contract_product": "raw_contract_product",
    "employee_assignment": "raw_employee_assignment",
    "shop": "raw_shop",
    "seller": "raw_seller",
    "lead_reason": "raw_lead_reason",
}
SOURCE_FILE_BY_DATASET = {**C.CSV_INPUTS, **C.XLSX_INPUTS}
KEY_AUDIT_SPEC = {
    "contract": ["skp_credit_case"],
    "leads": ["id_uuid"],
    "contract_product": [],  # skp_credit_case is a case grouping key, not a row-unique key; multiple details per case are valid.
    "employee_assignment": ["role", "skp_salesroom", "skp_employee", "dtime_valid_from", "dtime_valid_to", "code_status"],
    "shop": ["SKP_SALESROOM"],
    "seller": ["SKP_SELLER"],
    "lead_reason": ["ID_SOURCE", "DATE_EFFECTIVE", "CODE_SOURCE_SYSTEM"],
}
NUMERIC_PROFILE_FIELDS = {
    "price", "init_pay", "credit_amount", "ins_amount", "payment_num", "amt_billing_1st",
    "amt_billing_2nd", "amt_billing_3rd", "dpd_1pd", "dpd_2pd", "dpd_3pd", "dpd_4pd",
    "amt_loan_limit", "result", "sample_weight", "text_tenor",
}
TABLE_GRAINS = {
    "raw_inventory": "One row per supplied source file.",
    "column_profile": "One row per source dataset column.",
    "schema_validation": "One row per documented or observed source field.",
    "key_integrity": "One row per source dataset key/fingerprint audit.",
    "contract_event_version": "One row per contract source record, including exact duplicates and conflicting versions.",
    "contract_fact": "One row per valid credit-case ID; malformed missing-key rows remain individually traceable.",
    "contract_status_mapping": "One row per observed raw contract status; business outcome remains unmapped unless configured.",
    "contract_product_bridge": "One row per contract-product source detail row, including duplicates and unmatched cases.",
    "contract_product_summary": "One row per non-null credit-case ID in contract_product.csv.",
    "lead_reason_dimension": "One row per source lead-finish-reason record.",
    "lead_event_version": "One row per lead source record/version; UUID repeats and exact duplicates are retained.",
    "product_crosswalk": "One row per observed normalized lead product code and candidate contract product mapping.",
    "seller_master": "One row per seller ID or invalid-key source row; conflicts are flagged, not resolved arbitrarily.",
    "shop_master": "One row per salesroom ID or invalid-key source row; current-snapshot attributes only.",
    "shop_bridge": "One row per shop-master record, with at most one seller summary row.",
    "employee_shop_bridge": "One row per employee-salesroom assignment version; invalid intervals and overlaps are flagged.",
    "contract_shop_bridge": "One row per contract_fact row with booking-shop attributes left-joined.",
    "lead_shop_bridge": "One row per lead event with lead-origin-shop attributes left-joined.",
    "lead_contract_bridge": "One row per lead × candidate contract, plus one null-candidate row for every unmatched lead.",
    "lead_conversion_shop_month": "Origin shop × booking shop × application month × normalized product, based on primary lead matches.",
    "shop_behavior_profile": "One row per shop in the combined fact universe with observed contract/lead behavior and coverage.",
    "lead_match_summary": "One row per lead source record; candidate counts prevent downstream many-to-many inflation.",
    "r2_customer_segment": "One row per Round 2 customer score key across FHS/CES full outer join.",
    "contract_customer_segment_bridge": "One row per contract fact, left-joined to the unique Round 2 segment row.",
    "lead_customer_segment_bridge": "One row per lead event, left-joined to the unique Round 2 segment row.",
    "contract_shop_month": "Shop × month × configured business outcome or UNMAPPED.",
    "contract_shop_month_total": "Salesroom-key × month application totals across outcomes; customer distincts are computed over all cases.",
    "contract_shop_month_status": "Contract shop × application month × raw status and mapped outcome.",
    "lead_shop_month_product": "Lead-origin shop × assignment month × normalized lead product; primary matched-contract counts are additive.",
    "lead_conversion_shop_month": "Lead origin × booking shop × application month × normalized product.",
    "employee_shop_month": "Shop × month in observed event window; raw assignment coverage only unless active codes are approved.",
    "customer_segment_shop_product_month": "Shop × month × product × Round 2 segment × event role, strictly post-common-score cutoff.",
    "shop_month_foundation": "Current shop universe plus observed fact-shop IDs × observed source months; no-event rows are not interpreted as zero demand.",
    "r2_link_coverage": "One row per Round 2 score/event population and temporal window.",
    "coverage_summary": "One row per source-to-master, detail, candidate, score, or weight coverage measure.",
    "weight_audit": "Observed raw lead sample_weight distribution by source and product; QA sensitivity only.",
    "validation_checks": "One row per automated invariant or business-definition gate.",
}
TABLE_DESCRIPTIONS = {
    "contract_event_version": "Lossless normalized contract event/version record; date sentinels are nulled and flagged.",
    "contract_fact": "Canonical one-row-per-case view; conflicting source versions have ambiguous attributes nulled and remain in event_version.",
    "lead_event_version": "Lossless lead event/version record; sample_weight is preserved but never applied as a population estimator.",
    "lead_contract_bridge": "Candidate bridge using customer/product/time evidence and direct case-key validation, without crediting unapproved mappings.",
    "r2_customer_segment": "Round 2 FHS/CES score export join; both production outputs use SNAPSHOT_DATE; validation cutoffs are recorded separately.",
    "shop_month_foundation": "Fact counts and raw amounts at shop-month grain with explicit coverage and semantic approval flags.",
}
TABLE_SOURCE_DATASET = {
    "contract_event_version": "contract", "contract_fact": "contract", "contract_status_mapping": "contract",
    "contract_product_bridge": "contract_product", "contract_product_summary": "contract_product",
    "lead_event_version": "leads", "lead_reason_dimension": "lead_reason", "lead_reason_lookup": "lead_reason",
    "shop_master": "shop", "shop_bridge": "shop", "seller_master": "seller",
    "employee_shop_bridge": "employee_assignment",
}
SOURCE_FIELD_ALIASES = {
    "contract_event_version": {"skp_salesroom_id": "skp_salesroom", "skp_credit_case_id": "skp_credit_case",
        "skp_emp_pre_process_id": "skp_emp_pre_process", "skp_product_id": "skp_product", "skp_client_id": "skp_client",
        "product_raw": "product", "contract_status_raw": "name_status", "price_raw": "price", "init_pay_raw": "init_pay",
        "credit_amount_raw": "credit_amount", "ins_amount_raw": "ins_amount", "payment_num_raw": "payment_num",
        "date_sign_raw": "date_sign", "date_apply_raw": "date_apply"},
    "contract_fact": {"skp_salesroom_id": "skp_salesroom", "skp_credit_case_id": "skp_credit_case",
        "skp_client_id": "skp_client", "product_raw": "product", "contract_status_raw": "name_status",
        "credit_amount_raw": "credit_amount"},
    "lead_event_version": {"lead_uuid": "id_uuid", "skp_client_id": "skp_client", "skp_salesroom_id": "skp_salesroom",
        "lead_source_raw": "id_lead_source", "lead_product_code": "code_product_type",
        "lead_product_original_code": "code_product_type_original", "lead_status_code_raw": "code_lead_status",
        "sample_weight_raw": "sample_weight", "date_assigned_raw": "date_assigned", "dtime_created_raw": "dtime_created"},
    "shop_master": {"salesroom_category": "salesroom_category", "salesroom_model": "salesroom_model",
        "salesroom_product": "salesroom_product", "salesroom_status": "salesroom_status",
        "salesroom_town": "salesroom_town", "salesroom_province": "salesroom_province", "salesroom_area": "salesroom_area"},
    "seller_master": {"seller_model": "seller_model", "seller_status": "seller_status", "seller_type": "seller_type",
        "seller_product": "seller_product", "seller_province": "seller_province", "seller_area": "seller_area"},
}
TABLE_GRAINS["leads_clean"] = "One row per lead source record/version with match counts/state included."
TABLE_GRAINS["lead_contract_candidates"] = "One row per actual lead × candidate contract pair; unmatched leads stay in leads_clean."
TABLE_DESCRIPTIONS.update({
    "leads_clean": "Lead events plus one-row-per-lead match summary; unmatched and repeated UUIDs remain visible.",
    "lead_contract_candidates": "Candidate pairs only; does not include null placeholder rows for unmatched leads.",
})
TABLE_SOURCE_DATASET["leads_clean"] = "leads"
SOURCE_FIELD_ALIASES["leads_clean"] = SOURCE_FIELD_ALIASES["lead_event_version"]
PUBLISHED_PARQUET_PATHS = {
    "contract_fact": "contract_clean.parquet",
    "leads_clean": "leads_clean.parquet",
    "contract_product_bridge": "contract_product_clean.parquet",
    "shop_bridge": "shop_clean.parquet",
    "seller_master": "seller_clean.parquet",
    "employee_shop_bridge": "employee_shop_clean.parquet",
    "lead_contract_candidates": "lead_contract_candidates.parquet",
    "shop_month_foundation": "shop_month_foundation.parquet",
    "lead_shop_month_product": "lead_shop_month_product.parquet",
    "lead_conversion_shop_month": "lead_conversion_shop_month.parquet",
    "shop_behavior_profile": "shop_behavior_profile.parquet",
    "r2_customer_segment": "R2/r2_customer_segment.parquet",
}
COLUMN_DESCRIPTIONS = {
    "date_sign_was_sentinel": "True if the source encoded an open-ended/non-date sign timestamp with a configured sentinel year.",
    "after_common_r2_cutoff": "True only for events strictly after the Round 2 production score snapshot; same-day events are excluded conservatively.",
    "business_outcome": "UNMAPPED unless an explicit owner-approved status mapping is configured.",
    "credit_amount_raw": "Source credit_amount parsed as numeric; not validated as funded volume.",
    "sample_weight": "Typed source lead weight preserved as numeric; semantics and target population are unapproved.",
    "sample_weight_raw": "Original source representation of sample_weight, retained before numeric parsing.",
    "weight_status": "UNAPPROVED_QA_ONLY; do not interpret weighted sums as population estimates.",
    "active_headcount_proxy": "Assignment-count proxy using configured active status codes; not FTE or confirmed headcount.",
    "shop_attribute_vintage": "Current salesroom/seller master snapshot; not historical as-of attributes.",
    "match_status": "Predicate result; exact-code compatibility uses the configured competition assumption.",
    "is_funded": "Funded proxy selected by FUNDED_DEFINITION; STATUS_MAP uses configured funded outcome categories.",
    "is_funded_sign_date": "True when date_sign parsed as a non-sentinel date.",
    "is_funded_billing": "True when amt_billing_1st is non-null.",
    "is_funded_status": "True when mapped business_outcome is in FUNDED_STATUS_OUTCOMES; NULL when status map is empty.",
}

# %% [markdown]
# ## Paths, input discovery, schema extraction, and safe staging
#
# The raw Round 3 directory and Round 2 score files are inputs only. All
# generated artifacts are staged under Round 3 before successful publication.

# %%
def discover_inputs() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for dataset, filename in SOURCE_FILE_BY_DATASET.items():
        path = C.RAW_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required Round 3 source file not found: {path.name}")
        found[dataset] = path
    schema = C.RAW_DIR / C.SCHEMA_WORKBOOK
    if not schema.is_file():
        raise FileNotFoundError(f"Required schema workbook not found: {schema.name}")
    found["schema_workbook"] = schema
    for kind, path in C.ROUND2_SCORE_FILES.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required read-only Round 2 {kind.upper()} score Parquet not found: {path}")
        found[f"r2_{kind}"] = path
    if not C.ROUND2_CONFIG.is_file():
        raise FileNotFoundError("Round 2 config.py is required to read the declared score cutoffs.")
    return found


def read_schema_documentation(path: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, str], str]]:
    """Read workbook field names/types/descriptions without assuming it is complete."""
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    rows: list[dict[str, Any]] = []
    descriptions: dict[tuple[str, str], str] = {}
    for dataset, sheet_name in C.SCHEMA_SHEETS.items():
        frame = sheets.get(sheet_name)
        if frame is None:
            continue
        header_positions = [
            (r, c)
            for r in range(frame.shape[0])
            for c in range(frame.shape[1])
            if str(frame.iat[r, c]).strip() == "Column Name"
        ]
        if not header_positions:
            rows.append({"dataset": dataset, "field": None, "expected_type": None, "description": None,
                         "schema_status": "SHEET_HAS_NO_COLUMN_NAME_HEADER"})
            continue
        header_row, column_col = header_positions[0]
        for index in range(header_row + 1, frame.shape[0]):
            field = frame.iat[index, column_col] if column_col < frame.shape[1] else None
            if pd.isna(field) or not str(field).strip():
                continue
            expected = frame.iat[index, column_col + 1] if column_col + 1 < frame.shape[1] else None
            description = frame.iat[index, column_col + 2] if column_col + 2 < frame.shape[1] else None
            field_name = str(field).strip()
            type_name = None if pd.isna(expected) else str(expected).strip()
            field_description = "" if pd.isna(description) else str(description).replace("\n", " | ").strip()
            rows.append({"dataset": dataset, "field": field_name, "expected_type": type_name,
                         "description": field_description, "schema_status": "DOCUMENTED"})
            descriptions[(dataset, field_name.casefold())] = field_description
    return rows, descriptions


def get_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {quote_identifier(table)}").fetchall()]


def source_column(table: str, name: str, aliases: dict[str, dict[str, str]]) -> str:
    actual = aliases[table].get(name.casefold())
    if actual is None:
        raise KeyError(f"Expected source column {name!r} was not found in {table}.")
    # Keep the resolved, quoted field name unqualified so it also works inside CTEs.
    return quote_identifier(actual)


def row_hash_expression(columns: list[str], table_alias: str | None = None) -> str:
    parts = []
    for name in columns:
        value = f"{table_alias}.{quote_identifier(name)}" if table_alias else quote_identifier(name)
        parts.append(f"coalesce(cast({value} AS VARCHAR), chr(0))")
    return f"md5(concat_ws(chr(31), {', '.join(parts)}))"


def load_raw_sources(con: duckdb.DuckDBPyConnection, files: dict[str, Path]) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    aliases: dict[str, dict[str, str]] = {}
    inventory: list[dict[str, Any]] = []
    for dataset, filename in SOURCE_FILE_BY_DATASET.items():
        table = RAW_TABLE_BY_DATASET[dataset]
        path = files[dataset]
        if dataset in C.CSV_INPUTS:
            con.execute(
                f"CREATE TEMP VIEW {quote_identifier(table)} AS "
                f"SELECT * FROM {csv_scan_sql(path)}"
            )
        else:
            frame = pd.read_excel(path, sheet_name=0, dtype=object)
            frame.columns = [str(column).strip() for column in frame.columns]
            registered = f"_staging_{dataset}"
            con.register(registered, frame)
            con.execute(f"CREATE TEMP TABLE {quote_identifier(table)} AS SELECT * FROM {quote_identifier(registered)}")
            con.unregister(registered)
        columns = get_columns(con, table)
        aliases[table] = {column.casefold(): column for column in columns}
        row_count = int(con.execute(f"SELECT count(*) FROM {quote_identifier(table)}").fetchone()[0]) if dataset not in C.CSV_INPUTS else None
        inventory.append({
            "dataset": dataset,
            "file_name": filename,
            "source_format": path.suffix.lower().lstrip("."),
            "source_bytes": path.stat().st_size,
            "source_rows": row_count,
            "source_columns": len(columns),
            "ingestion_policy": "DuckDB VARCHAR-preserving CSV scan" if dataset in C.CSV_INPUTS else "pandas/openpyxl source values",
        })
    # Schema workbook is documented as metadata, not an analytical table.
    path = files["schema_workbook"]
    inventory.append({"dataset": "schema_workbook", "file_name": path.name, "source_format": "xlsx",
                      "source_bytes": path.stat().st_size, "source_rows": None, "source_columns": None,
                      "ingestion_policy": "Read-only schema metadata"})
    for kind in ("r2_fhs", "r2_ces"):
        score_path = files[kind]
        parquet_meta = pq.ParquetFile(score_path)
        inventory.append({"dataset": kind, "file_name": f"{C.ROUND2_DIR.name}/{score_path.relative_to(C.ROUND2_DIR).as_posix()}",
                          "source_format": "parquet", "source_bytes": score_path.stat().st_size,
                          "source_rows": parquet_meta.metadata.num_rows, "source_columns": len(parquet_meta.schema_arrow),
                          "ingestion_policy": "Read-only Round 2 score output; key uniqueness validated in score bridge"})
    return aliases, inventory


def build_schema_validation(
    con: duckdb.DuckDBPyConnection,
    schema_rows: list[dict[str, Any]],
    aliases: dict[str, dict[str, str]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    expected_by_dataset: dict[str, dict[str, dict[str, Any]]] = {}
    for row in schema_rows:
        if row.get("field"):
            expected_by_dataset.setdefault(row["dataset"], {})[row["field"].casefold()] = row
    for dataset, table in RAW_TABLE_BY_DATASET.items():
        actual_schema = con.execute(f"DESCRIBE SELECT * FROM {quote_identifier(table)}").fetchall()
        actual_types = {str(row[0]).casefold(): str(row[1]) for row in actual_schema}
        actual_by_key = {str(row[0]).casefold(): str(row[0]) for row in actual_schema}
        expected = expected_by_dataset.get(dataset, {})
        if not expected:
            for key, actual in actual_by_key.items():
                records.append({"dataset": dataset, "field": actual, "expected_type": None,
                                "observed_type": actual_types[key],
                                "observed_ingest_type": "VARCHAR-preserved" if dataset in C.CSV_INPUTS else "XLSX-inferred",
                                "type_review_state": "SOURCE_TABLE_NOT_DOCUMENTED",
                                "schema_status": "SOURCE_TABLE_NOT_DOCUMENTED",
                                "description": "No corresponding StructureTable.xlsx schema sheet."})
            continue
        for field_key, row in expected.items():
            actual = actual_by_key.get(field_key)
            records.append({
                "dataset": dataset, "field": row["field"], "expected_type": row["expected_type"],
                "observed_type": actual_types.get(field_key),
                "observed_ingest_type": "VARCHAR-preserved" if dataset in C.CSV_INPUTS else "XLSX-inferred",
                "type_review_state": "RAW_TEXT_PRESERVED; CHECK_TYPED_DERIVATIVES" if dataset in C.CSV_INPUTS else "XLSX_TYPE_RECORDED",
                "schema_status": "PRESENT" if actual else "MISSING_FROM_SOURCE",
                "description": row["description"],
            })
        for field_key, actual in actual_by_key.items():
            if field_key not in expected:
                records.append({"dataset": dataset, "field": actual, "expected_type": None,
                                "observed_type": actual_types[field_key],
                                "observed_ingest_type": "VARCHAR-preserved" if dataset in C.CSV_INPUTS else "XLSX-inferred",
                                "type_review_state": "NOT_DOCUMENTED_IN_SCHEMA",
                                "schema_status": "NOT_IN_SCHEMA", "description": "Observed in the supplied source but absent from StructureTable.xlsx."})
    # contract_product.csv is intentionally audited even though no schema sheet exists.
    return pd.DataFrame(records)

# %% [markdown]
# ## Full-file inventory, missingness, and primary-key audits
#
# All CSV columns are staged as VARCHAR first to preserve source IDs and codes
# (for example POS codes with leading zeros). Typed derivatives are added only
# after source strings are retained. Empty strings and documented placeholders
# are counted separately; no row is removed during profiling.

# %%
def profile_source_columns(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    placeholders = ("XNA", "#NAME?", "NONE", "NULL", "N/A", "NA")
    for dataset, table in RAW_TABLE_BY_DATASET.items():
        columns = get_columns(con, table)
        expressions = ["count(*) AS source_rows"]
        for index, column in enumerate(columns):
            quoted = quote_identifier(column)
            value = f"cast({quoted} AS VARCHAR)"
            expressions.extend([
                f"count(*) FILTER (WHERE {quoted} IS NULL) AS null_{index}",
                f"count(*) FILTER (WHERE {quoted} IS NOT NULL AND trim({value}) = '') AS blank_{index}",
                f"count(*) FILTER (WHERE upper(trim({value})) IN ({', '.join(sql_literal(item) for item in placeholders)})) AS placeholder_{index}",
            ])
            if column.casefold() in NUMERIC_PROFILE_FIELDS:
                numeric = f"try_cast(nullif(trim({value}), '') AS DOUBLE)"
                expressions.append(f"count(*) FILTER (WHERE {numeric} = 0) AS zero_{index}")
                expressions.append(f"sum({numeric}) AS numeric_sum_{index}")
        profile = con.execute(f"SELECT {', '.join(expressions)} FROM {quote_identifier(table)}").fetchone()
        source_rows = int(profile[0])
        offset = 1
        for index, column in enumerate(columns):
            nulls, blanks, placeholder_count = (int(profile[offset + j]) for j in range(3))
            offset += 3
            if column.casefold() in NUMERIC_PROFILE_FIELDS:
                zero_count, numeric_sum = profile[offset], profile[offset + 1]
                zero_count = int(zero_count or 0)
                offset += 2
            else:
                zero_count, numeric_sum = None, None
            records.append({
                "dataset": dataset, "column": column,
                "ingest_type": "VARCHAR-preserved" if dataset in C.CSV_INPUTS else "XLSX-inferred",
                "source_rows": source_rows, "null_count": nulls, "blank_count": blanks,
                "null_or_blank_count": nulls + blanks,
                "null_or_blank_pct": round(100 * (nulls + blanks) / max(source_rows, 1), 4),
                "placeholder_count": placeholder_count,
                "zero_count_if_numeric": zero_count,
                "numeric_sum_if_numeric": numeric_sum,
            })
    return pd.DataFrame(records)


def build_key_integrity(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]], profile_df: pd.DataFrame) -> pd.DataFrame:
    records = []
    source_counts = profile_df.groupby("dataset")["source_rows"].first().to_dict()
    for dataset, table in RAW_TABLE_BY_DATASET.items():
        key_names = KEY_AUDIT_SPEC.get(dataset, [])
        row_count = int(source_counts[dataset])
        qtable = quote_identifier(table)
        if not key_names:
            records.append({
                "dataset": dataset, "declared_key_fields": None, "source_rows": row_count,
                "distinct_key_count": None, "null_key_rows": None, "duplicate_key_groups": None,
                "duplicate_rows_beyond_first": None, "exact_duplicate_rows": None,
                "audit_state": "NO_DECLARED_PRIMARY_KEY; ROW_FINGERPRINT_AUDIT_PENDING",
            })
            continue
        missing = [key for key in key_names if key.casefold() not in aliases[table]]
        if missing:
            records.append({"dataset": dataset, "declared_key_fields": ",".join(key_names), "source_rows": row_count,
                            "distinct_key_count": None, "null_key_rows": None, "duplicate_key_groups": None,
                            "duplicate_rows_beyond_first": None, "exact_duplicate_rows": None,
                            "audit_state": "KEY_FIELD_MISSING_FROM_SOURCE"})
            continue
        actual = [aliases[table][key.casefold()] for key in key_names]
        key_expr = "concat_ws(chr(31), " + ", ".join(
            f"coalesce(cast({quote_identifier(key)} AS VARCHAR), '<NULL_KEY_PART>')" for key in actual
        ) + ")"
        null_expr = " OR ".join(
            f"{quote_identifier(key)} IS NULL OR trim(cast({quote_identifier(key)} AS VARCHAR)) = ''" for key in actual
        )
        stats = con.execute(f"""
            WITH grouped_keys AS (
                SELECT {key_expr} AS key_value, ({null_expr}) AS is_null_key, count(*) AS n
                FROM {qtable}
                GROUP BY 1, 2
            )
            SELECT coalesce(sum(n), 0),
                   count(*) FILTER (WHERE NOT is_null_key),
                   coalesce(sum(n) FILTER (WHERE is_null_key), 0),
                   count(*) FILTER (WHERE NOT is_null_key AND n > 1),
                   coalesce(sum(n - 1) FILTER (WHERE NOT is_null_key AND n > 1), 0)
            FROM grouped_keys
        """).fetchone()
        records.append({
            "dataset": dataset, "declared_key_fields": ",".join(key_names), "source_rows": row_count,
            "distinct_key_count": int(stats[1]), "null_key_rows": int(stats[2]),
            "duplicate_key_groups": int(stats[3]), "duplicate_rows_beyond_first": int(stats[4]),
            "exact_duplicate_rows": None,
            "audit_state": "KEY_GROUP_AUDITED; EXACT_ROW_HASH_AUDIT_PENDING",
        })
    return pd.DataFrame(records)


def update_exact_duplicate_audits(con: duckdb.DuckDBPyConnection) -> None:
    versions = {
        "contract": "contract_event_version", "contract_product": "contract_product_bridge",
        "employee_assignment": "employee_shop_bridge", "shop": "shop_master_versions",
        "seller": "seller_master_versions", "lead_reason": "lead_reason_dimension",
    }
    for dataset, table in versions.items():
        duplicate_rows = int(con.execute(
            f"SELECT count(*) - count(DISTINCT source_row_hash) FROM {quote_identifier(table)}"
        ).fetchone()[0])
        key_stats = con.execute(
            "SELECT duplicate_key_groups FROM key_integrity WHERE dataset = ?", [dataset]
        ).fetchone()
        duplicate_key_groups = key_stats[0] if key_stats else None
        if dataset == "contract_product":
            state = "NO_DECLARED_PRIMARY_KEY; ROW_FINGERPRINT_AUDITED"
        else:
            state = "AUDITED; DUPLICATES_RETAINED_AND_FLAGGED" if (duplicate_key_groups or 0) or duplicate_rows else "AUDITED_UNIQUE"
        con.execute(
            "UPDATE key_integrity SET exact_duplicate_rows = ?, audit_state = ? WHERE dataset = ?",
            [duplicate_rows, state, dataset],
        )

# %% [markdown]
# ## Shared source typing and sentinel treatment
#
# IDs are normalized to nullable BIGINT fields while raw IDs remain in the
# source columns. All source timestamps are parsed with ISO/day-first support.
# Sentinel years 2999/3000 become NULL plus explicit state flags.

# %%
def raw_text(table: str, name: str, aliases: dict[str, dict[str, str]]) -> str:
    return source_column(table, name, aliases)


def safe_min(expr: str, alias: str) -> str:
    """Collapse only identical values; conflicting versions yield NULL."""
    return (
        f"CASE WHEN count(DISTINCT coalesce(cast({expr} AS VARCHAR), '__NULL_SENTINEL__')) <= 1 "
        f"THEN min({expr}) END AS {quote_identifier(alias)}"
    )


def sentinel_year_sql() -> str:
    years = ", ".join(str(year) for year in sorted(C.SENTINEL_YEARS))
    return years or "NULL"


def post_score_date_predicate(timestamp_expression: str, cutoff: str | None) -> str:
    if not cutoff:
        return "NULL::BOOLEAN"
    operator = C.POST_SCORE_DATE_OPERATOR
    if operator not in (">", ">="):
        raise ValueError(f"Unsupported post-score date operator: {operator!r}")
    return f"CAST({timestamp_expression} AS DATE) {operator} DATE {sql_literal(cutoff)}"


def date_state_sql(raw_expr: str, parsed_expr: str, flag_name: str) -> str:
    sentinels = sentinel_year_sql()
    return (
        f"CASE WHEN {raw_expr} IS NULL OR trim(cast({raw_expr} AS VARCHAR)) = '' THEN 'MISSING' "
        f"WHEN {parsed_expr} IS NULL THEN 'INVALID' "
        f"WHEN year({parsed_expr}) IN ({sentinels}) THEN 'SENTINEL_OPEN_ENDED' ELSE 'PARSED' END AS {quote_identifier(flag_name)}"
    )


def parsed_date_sql(parsed_expr: str) -> str:
    return f"CASE WHEN {parsed_expr} IS NULL OR year({parsed_expr}) IN ({sentinel_year_sql()}) THEN NULL ELSE {parsed_expr} END"


def create_contract_event_versions(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]], common_cutoff: str | None) -> None:
    table = "raw_contract"
    columns = get_columns(con, table)
    q = lambda field: raw_text(table, field, aliases)
    hash_expr = row_hash_expression(columns)
    sign_parse = timestamp_sql_expression(q("date_sign"))
    apply_parse = timestamp_sql_expression(q("date_apply"))
    cutoff_expr = post_score_date_predicate("date_apply_ts", common_cutoff)
    con.execute(f"""
        CREATE TEMP TABLE contract_event_version AS
        WITH hashed AS (
            SELECT *, {hash_expr} AS source_row_hash FROM raw_contract
        ), numbered AS (
            SELECT *, count(*) OVER (PARTITION BY source_row_hash) AS exact_duplicate_group_size,
                   row_number() OVER (PARTITION BY source_row_hash ORDER BY source_row_hash) AS exact_duplicate_ordinal
            FROM hashed
        ), parsed AS (
            SELECT *, {sign_parse} AS _date_sign_parsed, {apply_parse} AS _date_apply_parsed
            FROM numbered
        )
        SELECT numbered.* EXCLUDE (_date_sign_parsed, _date_apply_parsed),
               concat(source_row_hash, ':', cast(exact_duplicate_ordinal AS VARCHAR)) AS contract_row_id,
               {normalize_key_sql(q('skp_salesroom'))} AS skp_salesroom_id,
               {normalize_key_sql(q('skp_credit_case'))} AS skp_credit_case_id,
               {normalize_key_sql(q('skp_emp_pre_process'))} AS skp_emp_pre_process_id,
               {normalize_key_sql(q('skp_product'))} AS skp_product_id,
               {normalize_key_sql(q('skp_client'))} AS skp_client_id,
               nullif(trim(cast({q('product')} AS VARCHAR)), '') AS product_raw,
               nullif(trim(cast({q('name_status')} AS VARCHAR)), '') AS contract_status_raw,
               try_cast(nullif(trim(cast({q('price')} AS VARCHAR)), '') AS DOUBLE) AS price_raw,
               try_cast(nullif(trim(cast({q('init_pay')} AS VARCHAR)), '') AS DOUBLE) AS init_pay_raw,
               try_cast(nullif(trim(cast({q('credit_amount')} AS VARCHAR)), '') AS DOUBLE) AS credit_amount_raw,
               try_cast(nullif(trim(cast({q('ins_amount')} AS VARCHAR)), '') AS DOUBLE) AS ins_amount_raw,
               try_cast(nullif(trim(cast({q('payment_num')} AS VARCHAR)), '') AS DOUBLE) AS payment_num_raw,
               try_cast(nullif(trim(cast({q('amt_billing_1st')} AS VARCHAR)), '') AS DOUBLE) AS amt_billing_1st_raw,
               try_cast(nullif(trim(cast({q('amt_billing_2nd')} AS VARCHAR)), '') AS DOUBLE) AS amt_billing_2nd_raw,
               try_cast(nullif(trim(cast({q('amt_billing_3rd')} AS VARCHAR)), '') AS DOUBLE) AS amt_billing_3rd_raw,
               try_cast(nullif(trim(cast({q('dpd_1pd')} AS VARCHAR)), '') AS DOUBLE) AS dpd_1pd_raw,
               try_cast(nullif(trim(cast({q('dpd_2pd')} AS VARCHAR)), '') AS DOUBLE) AS dpd_2pd_raw,
               try_cast(nullif(trim(cast({q('dpd_3pd')} AS VARCHAR)), '') AS DOUBLE) AS dpd_3pd_raw,
               try_cast(nullif(trim(cast({q('dpd_4pd')} AS VARCHAR)), '') AS DOUBLE) AS dpd_4pd_raw,
               cast({q('date_sign')} AS VARCHAR) AS date_sign_raw,
               {parsed_date_sql('numbered._date_sign_parsed')} AS date_sign_ts,
               {date_state_sql(q('date_sign'), 'numbered._date_sign_parsed', 'date_sign_state')},
               (year(numbered._date_sign_parsed) IN ({sentinel_year_sql()})) AS date_sign_was_sentinel,
               cast({q('date_apply')} AS VARCHAR) AS date_apply_raw,
               {parsed_date_sql('numbered._date_apply_parsed')} AS date_apply_ts,
               {date_state_sql(q('date_apply'), 'numbered._date_apply_parsed', 'date_apply_state')},
               {cutoff_expr} AS after_common_r2_cutoff,
               'RAW_APPLICATION_EVENT; FUNDED_SEMANTICS_UNAPPROVED' AS amount_semantics_state
        FROM parsed AS numbered
    """)


def create_contract_product_tables(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]]) -> None:
    table = "raw_contract_product"
    columns = get_columns(con, table)
    h = row_hash_expression(columns)
    case_expr = normalize_key_sql(raw_text(table, "skp_credit_case", aliases))
    con.execute(f"""
        CREATE TEMP TABLE contract_product_bridge AS
        WITH hashed AS (SELECT *, {h} AS source_row_hash FROM raw_contract_product),
        numbered AS (
            SELECT *, count(*) OVER (PARTITION BY source_row_hash) AS exact_duplicate_group_size,
                   row_number() OVER (PARTITION BY source_row_hash ORDER BY source_row_hash) AS exact_duplicate_ordinal
            FROM hashed
        )
        SELECT numbered.*,
               concat(source_row_hash, ':', cast(exact_duplicate_ordinal AS VARCHAR)) AS contract_product_row_id,
               {case_expr} AS skp_credit_case_id,
               nullif(trim(cast({raw_text(table, 'name_producer', aliases)} AS VARCHAR)), '') AS producer_raw,
               nullif(trim(cast({raw_text(table, 'name_goods_category', aliases)} AS VARCHAR)), '') AS goods_category_raw,
               nullif(trim(cast({raw_text(table, 'name_goods_type', aliases)} AS VARCHAR)), '') AS goods_type_raw,
               nullif(trim(cast({raw_text(table, 'goods_group', aliases)} AS VARCHAR)), '') AS goods_group_raw
        FROM numbered
    """)
    con.execute("""
        CREATE TEMP TABLE contract_product_summary AS
        SELECT skp_credit_case_id,
               count(*) AS detail_source_rows,
               count(DISTINCT source_row_hash) AS distinct_detail_versions,
               count(*) - count(DISTINCT source_row_hash) AS exact_duplicate_detail_rows,
               count(DISTINCT producer_raw) FILTER (WHERE producer_raw IS NOT NULL) AS producer_count,
               count(DISTINCT goods_category_raw) FILTER (WHERE goods_category_raw IS NOT NULL) AS goods_category_count,
               count(DISTINCT goods_type_raw) FILTER (WHERE goods_type_raw IS NOT NULL) AS goods_type_count,
               string_agg(DISTINCT producer_raw, ' | ' ORDER BY producer_raw) FILTER (WHERE producer_raw IS NOT NULL) AS producers,
               string_agg(DISTINCT goods_category_raw, ' | ' ORDER BY goods_category_raw) FILTER (WHERE goods_category_raw IS NOT NULL) AS goods_categories,
               string_agg(DISTINCT goods_type_raw, ' | ' ORDER BY goods_type_raw) FILTER (WHERE goods_type_raw IS NOT NULL) AS goods_types,
               string_agg(DISTINCT goods_group_raw, ' | ' ORDER BY goods_group_raw) FILTER (WHERE goods_group_raw IS NOT NULL) AS goods_groups
        FROM contract_product_bridge
        WHERE skp_credit_case_id IS NOT NULL
        GROUP BY skp_credit_case_id
    """)


def create_contract_fact(con: duckdb.DuckDBPyConnection, common_cutoff: str | None) -> None:
    funded_definition = str(C.FUNDED_DEFINITION).upper()
    if funded_definition not in {"SIGN_DATE", "STATUS_MAP", "BILLING"}:
        raise ValueError("FUNDED_DEFINITION must be SIGN_DATE, STATUS_MAP, or BILLING")
    funded_status_values = sorted(str(value).upper() for value in C.FUNDED_STATUS_OUTCOMES)
    status_funded_sql = (
        "NULL::BOOLEAN" if not C.APPROVED_CONTRACT_OUTCOME_MAP
        else "FALSE" if not funded_status_values
        else f"upper(coalesce(s.business_outcome, '')) IN ({', '.join(sql_literal(value) for value in funded_status_values)})"
    )
    valid_case_rows, distinct_case_ids = con.execute("""
        SELECT count(*) FILTER (WHERE skp_credit_case_id IS NOT NULL),
               count(DISTINCT skp_credit_case_id)
        FROM contract_event_version
    """).fetchone()
    duplicate_case_rows = int(valid_case_rows - distinct_case_ids)
    if duplicate_case_rows:
        raise RuntimeError(
            f"{duplicate_case_rows:,} duplicate normalized credit-case rows found. "
            "All versions remain in contract_event_version; the canonical one-row-per-case fact is blocked "
            "until a duplicate/version resolution rule is approved."
        )
    con.execute(f"""
        CREATE TEMP TABLE contract_fact AS
        SELECT CASE WHEN c.skp_credit_case_id IS NULL THEN concat('ROW:', c.contract_row_id)
                    ELSE concat('CASE:', cast(c.skp_credit_case_id AS VARCHAR)) END AS contract_fact_id,
               c.contract_row_id AS representative_source_row_id,
               c.source_row_hash, c.exact_duplicate_group_size, c.exact_duplicate_ordinal,
               1::BIGINT AS source_row_count,
               1::BIGINT AS distinct_source_versions,
               0::BIGINT AS exact_duplicate_rows_collapsed,
               c.skp_salesroom_id, c.skp_credit_case_id, c.skp_emp_pre_process_id, c.skp_product_id, c.skp_client_id,
               c.product_raw, c.contract_status_raw,
               c.price_raw, c.init_pay_raw, c.credit_amount_raw, c.ins_amount_raw, c.payment_num_raw,
               c.amt_billing_1st_raw, c.amt_billing_2nd_raw, c.amt_billing_3rd_raw,
               c.dpd_1pd_raw, c.dpd_2pd_raw, c.dpd_3pd_raw, c.dpd_4pd_raw,
               c.date_sign_raw, c.date_sign_ts, c.date_sign_state, c.date_sign_was_sentinel,
               (c.date_sign_ts IS NOT NULL) AS is_funded_sign_date,
               (c.amt_billing_1st_raw IS NOT NULL) AS is_funded_billing,
               {status_funded_sql} AS is_funded_status,
               CASE '{funded_definition}' WHEN 'SIGN_DATE' THEN (c.date_sign_ts IS NOT NULL)
                    WHEN 'BILLING' THEN (c.amt_billing_1st_raw IS NOT NULL)
                    ELSE {status_funded_sql} END AS is_funded,
               c.date_apply_raw, c.date_apply_ts, c.date_apply_state, c.after_common_r2_cutoff,
               CASE WHEN c.skp_credit_case_id IS NULL THEN 'MISSING_PRIMARY_KEY_ROW_RETAINED'
                    ELSE 'ONE_SOURCE_VERSION' END AS contract_version_state,
               coalesce(s.business_outcome, 'UNMAPPED') AS business_outcome,
               coalesce(p.detail_source_rows, 0) AS product_detail_rows,
               coalesce(p.distinct_detail_versions, 0) AS product_detail_versions,
               p.goods_categories, p.goods_types, p.goods_groups, p.producers,
               'UNVALIDATED_SOURCE_CREDIT_AMOUNT' AS credit_amount_semantics
        FROM contract_event_version c
        LEFT JOIN contract_status_mapping s ON c.contract_status_raw = s.contract_status_raw
        LEFT JOIN contract_product_summary p ON c.skp_credit_case_id = p.skp_credit_case_id
    """)



# %% [markdown]
# ## Shop, seller, employee, lead-reason, and product integrations
#
# Dimensions are collapsed only when values agree. Conflicts remain flagged and
# conflicting attributes become NULL rather than choosing a convenient row.
# Shop/seller attributes are current snapshots; employee code semantics are not
# inferred from a raw status letter.

# %%
def create_dimension_tables(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]]) -> None:
    # Shop master versions; raw columns are retained alongside typed keys/dates.
    for dataset, table, id_col, row_id, parsed_dates in [
        ("shop", "raw_shop", "SKP_SALESROOM", "shop_master_row_id", {"SALESROOM_START": "salesroom_start_ts", "SALESROOM_END": "salesroom_end_ts"}),
        ("seller", "raw_seller", "SKP_SELLER", "seller_master_row_id", {"SELLER_ACTIVE_DATE": "seller_active_date_ts"}),
    ]:
        columns = get_columns(con, table)
        hash_expr = row_hash_expression(columns)
        id_expr = normalize_key_sql(raw_text(table, id_col, aliases))
        date_selects = []
        for source_name, target_name in parsed_dates.items():
            raw_expr = raw_text(table, source_name, aliases)
            parsed_expr = timestamp_sql_expression(raw_expr)
            date_selects.append(f"{parsed_expr} AS _{target_name}_parsed")
        base = f"""
            CREATE TEMP TABLE {table.replace('raw_', '')}_master_versions AS
            WITH hashed AS (SELECT *, {hash_expr} AS source_row_hash FROM {quote_identifier(table)}),
            numbered AS (
                SELECT *, count(*) OVER (PARTITION BY source_row_hash) AS exact_duplicate_group_size,
                       row_number() OVER (PARTITION BY source_row_hash ORDER BY source_row_hash) AS exact_duplicate_ordinal
                FROM hashed
            ), parsed AS (SELECT *, {', '.join(date_selects)} FROM numbered)
            SELECT parsed.*,
                   concat(source_row_hash, ':', cast(exact_duplicate_ordinal AS VARCHAR)) AS {quote_identifier(row_id)},
                   {id_expr} AS {id_col.casefold()}_id
        """
        for source_name, target_name in parsed_dates.items():
            raw_expr = raw_text(table, source_name, aliases)
            parsed = f"parsed._{target_name}_parsed"
            base += f", cast({raw_expr} AS VARCHAR) AS {target_name}_raw, {parsed_date_sql(parsed)} AS {target_name}, {date_state_sql(raw_expr, parsed, target_name + '_state')}"
        base += f" FROM parsed"
        con.execute(base)

    def create_one_row_master(version_table: str, output_table: str, key_field: str, id_field: str, source_attrs: list[tuple[str, str]]) -> None:
        group_key = f"CASE WHEN {quote_identifier(id_field)} IS NULL THEN concat('ROW:', {quote_identifier(key_field)}) ELSE concat('KEY:', cast({quote_identifier(id_field)} AS VARCHAR)) END"
        projections = [safe_min(quote_identifier(id_field), id_field)]
        for source_field, output_field in source_attrs:
            if source_field in get_columns(con, version_table):
                projections.append(safe_min(quote_identifier(source_field), output_field))
        date_fields = [
            name for name in get_columns(con, version_table)
            if name.endswith("_ts") or name.endswith("_state") or name.endswith("_raw")
        ]
        for field in date_fields:
            if field not in {out for _, out in source_attrs} and field != id_field:
                projections.append(safe_min(quote_identifier(field), field))
        con.execute(f"""
            CREATE TEMP TABLE {quote_identifier(output_table)} AS
            SELECT {group_key} AS master_record_id,
                   count(*) AS source_row_count,
                   count(DISTINCT source_row_hash) AS distinct_source_versions,
                   count(*) - count(DISTINCT source_row_hash) AS exact_duplicate_rows,
                   {', '.join(projections)},
                   CASE WHEN count(DISTINCT source_row_hash) > 1 THEN 'CONFLICTING_MASTER_VERSIONS'
                        WHEN count(*) > 1 THEN 'EXACT_DUPLICATE_MASTER_ROWS'
                        ELSE 'UNIQUE_MASTER_ROW' END AS master_version_state,
                   'CURRENT_SNAPSHOT_ONLY' AS attribute_vintage
            FROM {quote_identifier(version_table)}
            GROUP BY 1
        """)

    create_one_row_master(
        "shop_master_versions", "shop_master", "shop_master_row_id", "skp_salesroom_id",
        [("SALESROOM_CATEGORY", "salesroom_category"), ("SALESROOM_MODEL", "salesroom_model"),
         ("SALESROOM_PRODUCT", "salesroom_product"), ("SALESROOM_STATUS", "salesroom_status"),
         ("SALESROOM_TOWN", "salesroom_town"), ("SALESROOM_DISTRICT", "salesroom_district"),
         ("SALESROOM_PROVINCE", "salesroom_province"), ("SALESROOM_AREA", "salesroom_area"),
         ("SKP_SELLER", "skp_seller_raw"), ("SKP_EMP_MANAGE", "skp_emp_manage_raw"),
         ("salesroom_start_ts", "salesroom_start_ts"), ("salesroom_end_ts", "salesroom_end_ts")],
    )
    create_one_row_master(
        "seller_master_versions", "seller_master", "seller_master_row_id", "skp_seller_id",
        [("SELLER_MODEL", "seller_model"), ("SELLER_STATUS", "seller_status"),
         ("SELLER_TYPE", "seller_type"), ("SELLER_PRODUCT", "seller_product"),
         ("SELLER_PROVINCE", "seller_province"), ("SELLER_AREA", "seller_area"),
         ("seller_active_date_ts", "seller_active_date_ts")],
    )
    # Link normalized seller ID, never the raw float representation.
    con.execute("""
        CREATE TEMP TABLE shop_bridge AS
        SELECT s.*, se.master_record_id AS seller_master_record_id,
               se.seller_status, se.seller_model, se.seller_type, se.seller_product,
               se.seller_province, se.seller_area, se.seller_active_date_ts,
               CASE WHEN s.skp_seller_raw IS NULL THEN 'MISSING_SELLER_KEY'
                    WHEN se.master_record_id IS NULL THEN 'UNMATCHED_SELLER'
                    ELSE 'SELLER_MASTER_MATCHED' END AS seller_match_state
        FROM shop_master s
        LEFT JOIN seller_master se
          ON try_cast(try_cast(s.skp_seller_raw AS DOUBLE) AS BIGINT) = se.skp_seller_id
    """)

    # Employee assignment versions with open-ended sentinel treatment and overlap diagnostics.
    table = "raw_employee_assignment"
    columns = get_columns(con, table)
    h = row_hash_expression(columns)
    from_expr = timestamp_sql_expression(raw_text(table, "dtime_valid_from", aliases))
    to_expr = timestamp_sql_expression(raw_text(table, "dtime_valid_to", aliases))
    con.execute(f"""
        CREATE TEMP TABLE employee_shop_bridge AS
        WITH hashed AS (SELECT *, {h} AS source_row_hash FROM raw_employee_assignment),
        numbered AS (
            SELECT *, count(*) OVER (PARTITION BY source_row_hash) AS exact_duplicate_group_size,
                   row_number() OVER (PARTITION BY source_row_hash ORDER BY source_row_hash) AS exact_duplicate_ordinal
            FROM hashed
        ), parsed AS (SELECT *, {from_expr} AS _valid_from_parsed, {to_expr} AS _valid_to_parsed FROM numbered),
        typed AS (
            SELECT *,
                concat(source_row_hash, ':', cast(exact_duplicate_ordinal AS VARCHAR)) AS employee_assignment_id,
                {normalize_key_sql(raw_text(table, 'skp_salesroom', aliases))} AS skp_salesroom_id,
                {normalize_key_sql(raw_text(table, 'skp_employee', aliases))} AS skp_employee_id,
                cast({raw_text(table, 'role', aliases)} AS VARCHAR) AS role_raw,
                cast({raw_text(table, 'code_status', aliases)} AS VARCHAR) AS code_status_raw,
                {parsed_date_sql('numbered._valid_from_parsed')} AS valid_from_ts,
                {parsed_date_sql('numbered._valid_to_parsed')} AS valid_to_ts,
                {date_state_sql(raw_text(table, 'dtime_valid_from', aliases), 'numbered._valid_from_parsed', 'valid_from_state')},
                {date_state_sql(raw_text(table, 'dtime_valid_to', aliases), 'numbered._valid_to_parsed', 'valid_to_state')},
                (year(numbered._valid_to_parsed) IN ({sentinel_year_sql()})) AS valid_to_was_sentinel
            FROM parsed AS numbered
        ), interval_rows AS (
            SELECT *,
                   max(CASE WHEN valid_from_ts IS NOT NULL
                                    AND valid_to_state IN ('PARSED','SENTINEL_OPEN_ENDED')
                                    AND (valid_to_ts IS NULL OR valid_to_ts >= valid_from_ts)
                               THEN coalesce(valid_to_ts, TIMESTAMP '9999-12-31 00:00:00') END) OVER (
                       PARTITION BY skp_salesroom_id, skp_employee_id
                       ORDER BY valid_from_ts NULLS FIRST, employee_assignment_id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                   ) AS previous_max_end
            FROM typed
        )
        SELECT i.*,
               CASE WHEN valid_from_ts IS NULL THEN 'START_MISSING_OR_INVALID'
                    WHEN valid_to_state = 'INVALID' THEN 'END_INVALID'
                    WHEN valid_to_state = 'MISSING' THEN 'END_MISSING'
                    WHEN valid_to_ts < valid_from_ts THEN 'END_BEFORE_START'
                    WHEN valid_to_was_sentinel THEN 'VALID_OPEN_ENDED_SENTINEL'
                    ELSE 'VALID_BOUNDED_INTERVAL' END AS assignment_interval_state,
               (valid_from_ts IS NOT NULL AND previous_max_end IS NOT NULL AND valid_from_ts <= previous_max_end) AS overlaps_prior_interval,
               {status_active_sql('code_status_raw')} AS status_is_approved_active,
               CASE WHEN shop.master_record_id IS NULL THEN 'UNMATCHED_CURRENT_SHOP_MASTER' ELSE 'CURRENT_SHOP_MASTER_MATCHED' END AS shop_match_state
        FROM interval_rows i
        LEFT JOIN shop_master shop ON i.skp_salesroom_id = shop.skp_salesroom_id
    """)

    # Lead reason lookup is source metadata only; it does not define signed conversion.
    table = "raw_lead_reason"
    columns = get_columns(con, table)
    h = row_hash_expression(columns)
    source_id = normalize_key_sql(raw_text(table, "ID_SOURCE", aliases))
    effective = timestamp_sql_expression(raw_text(table, "DATE_EFFECTIVE", aliases))
    con.execute(f"""
        CREATE TEMP TABLE lead_reason_dimension AS
        WITH hashed AS (SELECT *, {h} AS source_row_hash FROM raw_lead_reason),
        numbered AS (
            SELECT *, count(*) OVER (PARTITION BY source_row_hash) AS exact_duplicate_group_size,
                   row_number() OVER (PARTITION BY source_row_hash ORDER BY source_row_hash) AS exact_duplicate_ordinal
            FROM hashed
        )
        SELECT numbered.*,
               concat(source_row_hash, ':', cast(exact_duplicate_ordinal AS VARCHAR)) AS lead_reason_row_id,
               {source_id} AS id_source_normalized,
               {effective} AS date_effective_ts,
               upper(trim(cast({raw_text(table, 'FLAG_DELETED', aliases)} AS VARCHAR))) = 'N' AS is_not_deleted_per_source_note
        FROM numbered
    """)
    con.execute("""
        CREATE TEMP TABLE lead_reason_lookup AS
        SELECT id_source_normalized,
               count(*) AS mapping_source_rows,
               count(*) FILTER (WHERE is_not_deleted_per_source_note) AS nondeleted_rows,
               count(DISTINCT CODE_FINISH) FILTER (WHERE is_not_deleted_per_source_note) AS distinct_active_finish_codes,
               CASE WHEN count(*) FILTER (WHERE is_not_deleted_per_source_note) = 1
                    THEN min(CODE_FINISH) FILTER (WHERE is_not_deleted_per_source_note) END AS code_finish,
               CASE WHEN count(*) FILTER (WHERE is_not_deleted_per_source_note) = 1
                    THEN min(DESC_DESCRIPTION) FILTER (WHERE is_not_deleted_per_source_note) END AS description,
               CASE WHEN count(*) FILTER (WHERE is_not_deleted_per_source_note) = 1 THEN 'UNIQUE_NONDELETED_SOURCE_MAPPING'
                    WHEN count(*) FILTER (WHERE is_not_deleted_per_source_note) = 0 THEN 'NO_NONDELETED_MAPPING'
                    ELSE 'AMBIGUOUS_SOURCE_MAPPING' END AS lookup_state
        FROM lead_reason_dimension
        GROUP BY id_source_normalized
    """)


def status_active_sql(raw_status_expression: str) -> str:
    statuses = sorted(str(x) for x in C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES)
    if not statuses:
        return "NULL::BOOLEAN"
    values = ", ".join(sql_literal(x) for x in statuses)
    return f"upper(trim(cast({raw_status_expression} AS VARCHAR))) IN ({values})"




def create_lead_events(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]], common_cutoff: str | None) -> None:
    table = "raw_leads"
    created = timestamp_sql_expression(raw_text(table, "dtime_created", aliases))
    assigned = timestamp_sql_expression(raw_text(table, "date_assigned", aliases))
    invalid_case_keys = C.OPTIONAL_KEY_PLACEHOLDERS.get("leads.skp_credit_case", frozenset())
    invalid_sql = ", ".join(sql_literal(v) for v in sorted(invalid_case_keys))
    case_expr = normalize_key_sql(raw_text(table, "skp_credit_case", aliases))
    case_expr = f"CASE WHEN trim(cast({raw_text(table, 'skp_credit_case', aliases)} AS VARCHAR)) IN ({invalid_sql}) THEN NULL ELSE {case_expr} END" if invalid_sql else case_expr
    cutoff_expr = post_score_date_predicate("date_assigned_ts", common_cutoff)
    status_value = f"try_cast(nullif(trim(cast({raw_text(table, 'code_lead_status', aliases)} AS VARCHAR)), '') AS BIGINT)"
    con.execute(f"""
        CREATE TEMP TABLE lead_event_version AS
        WITH numbered AS (
            SELECT *, row_number() OVER () AS source_row_number,
                   count(*) OVER (PARTITION BY id_uuid) AS uuid_source_row_count
            FROM raw_leads
        ), parsed AS (SELECT *, {created} AS _created_parsed, {assigned} AS _assigned_parsed FROM numbered)
        SELECT numbered.* EXCLUDE (_created_parsed, _assigned_parsed, sample_weight),
               concat('LEAD-ROW:', cast(source_row_number AS VARCHAR)) AS lead_row_id,
               {normalize_key_sql(raw_text(table, 'skp_client', aliases))} AS skp_client_id,
               {normalize_key_sql(raw_text(table, 'skp_salesroom', aliases))} AS skp_salesroom_id,
               {normalize_key_sql(raw_text(table, 'skp_employee', aliases))} AS skp_employee_id,
               {case_expr} AS skp_credit_case_id,
               cast({raw_text(table, 'id_uuid', aliases)} AS VARCHAR) AS lead_uuid,
               nullif(trim(cast({raw_text(table, 'id_lead_source', aliases)} AS VARCHAR)), '') AS lead_source_raw,
               nullif(trim(cast({raw_text(table, 'code_product_type', aliases)} AS VARCHAR)), '') AS lead_product_code,
               nullif(trim(cast({raw_text(table, 'code_product_type_original', aliases)} AS VARCHAR)), '') AS lead_product_original_code,
               nullif(trim(cast({raw_text(table, 'code_lead_status', aliases)} AS VARCHAR)), '') AS lead_status_code_raw,
               {status_value} AS lead_status_id,
               reason.code_finish AS lead_finish_code,
               reason.description AS lead_finish_description,
               coalesce(reason.lookup_state, 'NO_SOURCE_MAPPING') AS lead_reason_mapping_state,
               cast({raw_text(table, 'dtime_created', aliases)} AS VARCHAR) AS dtime_created_raw,
               {parsed_date_sql('numbered._created_parsed')} AS dtime_created_ts,
               {date_state_sql(raw_text(table, 'dtime_created', aliases), 'numbered._created_parsed', 'dtime_created_state')},
               cast({raw_text(table, 'date_assigned', aliases)} AS VARCHAR) AS date_assigned_raw,
               {parsed_date_sql('numbered._assigned_parsed')} AS date_assigned_ts,
               {date_state_sql(raw_text(table, 'date_assigned', aliases), 'numbered._assigned_parsed', 'date_assigned_state')},
               (year(numbered._created_parsed) IN ({sentinel_year_sql()})) AS dtime_created_was_sentinel,
               (year(numbered._assigned_parsed) IN ({sentinel_year_sql()})) AS date_assigned_was_sentinel,
               try_cast(nullif(trim(cast({raw_text(table, 'amt_loan_limit', aliases)} AS VARCHAR)), '') AS DOUBLE) AS amt_loan_limit_raw,
               try_cast(nullif(trim(cast({raw_text(table, 'result', aliases)} AS VARCHAR)), '') AS DOUBLE) AS result_raw,
               cast({raw_text(table, 'sample_weight', aliases)} AS VARCHAR) AS sample_weight_raw,
               try_cast(nullif(trim(cast({raw_text(table, 'sample_weight', aliases)} AS VARCHAR)), '') AS DOUBLE) AS sample_weight,
               (try_cast(nullif(trim(cast({raw_text(table, 'sample_weight', aliases)} AS VARCHAR)), '') AS DOUBLE) > 0) AS sample_weight_positive,
               cast({raw_text(table, 'code_pos', aliases)} AS VARCHAR) AS code_pos_raw,
               cast({raw_text(table, 'text_accepted_by', aliases)} AS VARCHAR) AS accepted_by_raw,
               cast({raw_text(table, 'text_contract_number', aliases)} AS VARCHAR) AS contract_number_raw,
               cast({raw_text(table, 'text_tenor', aliases)} AS VARCHAR) AS tenor_raw,
               cast({raw_text(table, 'code_sa', aliases)} AS VARCHAR) AS code_sa_raw,
               {cutoff_expr} AS after_common_r2_cutoff,
               'UNAPPROVED_QA_ONLY' AS weight_status
        FROM parsed AS numbered
        LEFT JOIN lead_reason_lookup reason ON reason.id_source_normalized = {status_value}
    """)

# %% [markdown]
# ## Round 2 score bridge and cutoff provenance
#
# Cutoffs are parsed from Round 2's own config rather than guessed from Round 3.
# The paired FHS/CES segment is safe for subsequent outcomes only after the
# later of its two feature cutoffs. The common cutoff is strict (`event date >
# cutoff date`) because event timestamps are not tied to the score-generation
# instant. This stage attaches historical labels; it does not recalculate scores.

# %%
def read_round2_cutoffs(config_path: Path) -> dict[str, Any]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    score_variables = set(C.ROUND2_CUTOFF_VARIABLES.values())
    validation_variables = set(C.ROUND2_VALIDATION_CUTOFF_VARIABLES.values())
    wanted = score_variables | validation_variables
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, str):
                        values[target.id] = value
    result: dict[str, Any] = {key: values.get(variable) for key, variable in C.ROUND2_CUTOFF_VARIABLES.items()}
    result.update({f"{key}_validation_asof": values.get(variable)
                   for key, variable in C.ROUND2_VALIDATION_CUTOFF_VARIABLES.items()})
    score_dates = [result.get(key) for key in C.ROUND2_CUTOFF_VARIABLES]
    parsed = [date.fromisoformat(value) for value in score_dates if value]
    result["common_cutoff"] = max(parsed).isoformat() if len(parsed) == len(C.ROUND2_CUTOFF_VARIABLES) else None
    result["cutoff_provenance_state"] = (
        "PRODUCTION_SCORE_SNAPSHOT_DECLARED_IN_ROUND2_CONFIG; FEATURE-LEVEL TIMESTAMP AUDIT STILL REQUIRED"
        if result["common_cutoff"] else "ROUND2_SCORE_CUTOFF_UNAVAILABLE; POST-SCORE LINKAGE DISABLED"
    )
    return result


def compare_with_previous_compact_run(output_dir: Path, current_run_id: str, current_counts: dict[str, int], current_reconciliation: dict[str, Any]) -> dict[str, Any]:
    legacy_path = Path(output_dir) / "foundation" / "validation_report.json"
    if not legacy_path.exists():
        return {"legacy_run_id": None, "current_run_id": current_run_id,
                "previous_38_file_run_comparison": {}, "row_count_differences": {},
                "amount_differences": {}, "checks": [{"check": "legacy_run_available", "status": "WARNING",
                "details": "Prior 38-Parquet run removed before its metrics were retained."}],
                "baseline_metrics_present": False}
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    old_counts = legacy.get("table_row_counts", {})
    keys = {"contract_fact": "contract_fact", "lead_event_version": "lead_event_version",
            "contract_product_bridge": "contract_product_bridge", "shop_bridge": "shop_bridge",
            "seller_master": "seller_master", "employee_shop_bridge": "employee_shop_bridge",
            "lead_match_summary": "lead_match_summary", "shop_month_foundation": "shop_month_foundation",
            "lead_shop_month_product": "lead_shop_month_product", "r2_customer_segment": "r2_customer_segment"}
    count_differences = {}
    actual = {}
    for table, legacy_key in keys.items():
        if legacy_key not in old_counts or table not in current_counts:
            continue
        previous, current = int(old_counts[legacy_key]), int(current_counts[table])
        actual[table] = {"legacy_rows": previous, "current_rows": current}
        if previous != current:
            count_differences[table] = {"legacy": previous, "current": current}
    amount_differences = {}
    old_reconciliation = legacy.get("join_reconciliation", {})
    for key in ("contract_raw_amount_sum", "contract_fact_amount_sum", "contract_month_amount_sum"):
        old, new = old_reconciliation.get(key), current_reconciliation.get(key)
        if old is not None and new is not None and abs(float(old) - float(new)) > max(0.01, abs(float(old)) * 1e-9):
            amount_differences[key] = {"legacy": old, "current": new}
    checks = [
        {"check": "legacy_run_available", "status": "PASS", "details": legacy.get("run_id")},
        {"check": "compared_canonical_entity_counts_unchanged", "status": "PASS" if not count_differences else "FAIL", "details": actual},
        {"check": "amount_reconciliation_unchanged", "status": "PASS" if not amount_differences else "FAIL", "details": amount_differences},
    ]
    return {"legacy_run_id": legacy.get("run_id"), "current_run_id": current_run_id,
            "previous_38_file_run_comparison": actual, "row_count_differences": count_differences,
            "amount_differences": amount_differences, "checks": checks, "baseline_metrics_present": True}


def create_r2_customer_segment(con: duckdb.DuckDBPyConnection, files: dict[str, Path], cutoffs: dict[str, Any]) -> None:
    for kind in ("fhs", "ces"):
        path = files[f"r2_{kind}"].as_posix()
        con.execute(f"CREATE OR REPLACE TEMP VIEW raw_r2_{kind} AS SELECT * FROM read_parquet({sql_literal(path)})")
    con.execute("""
        CREATE TEMP TABLE _r2_fhs AS
        SELECT try_cast(SKP_CLIENT AS BIGINT) AS skp_client_id,
               count(*) AS fhs_source_rows,
               count(DISTINCT Financial_Health_Score) AS fhs_distinct_scores,
               count(DISTINCT fh_short) AS fhs_distinct_short_tiers,
               CASE WHEN count(DISTINCT Financial_Health_Score) <= 1 THEN min(Financial_Health_Score) END AS financial_health_score,
               CASE WHEN count(DISTINCT Financial_Health_Tier) <= 1 THEN min(Financial_Health_Tier) END AS financial_health_tier,
               CASE WHEN count(DISTINCT fh_short) <= 1 THEN min(fh_short) END AS fh_short,
               CASE WHEN count(DISTINCT fh_segment) <= 1 THEN min(fh_segment) END AS fh_segment,
               CASE WHEN count(DISTINCT fh_thin_file) <= 1 THEN min(fh_thin_file) END AS fh_thin_file
        FROM raw_r2_fhs GROUP BY 1
    """)
    con.execute("""
        CREATE TEMP TABLE _r2_ces AS
        SELECT try_cast(SKP_CLIENT AS BIGINT) AS skp_client_id,
               count(*) AS ces_source_rows,
               count(DISTINCT Engagement_Score) AS ces_distinct_scores,
               count(DISTINCT eng_short) AS ces_distinct_short_tiers,
               CASE WHEN count(DISTINCT Engagement_Score) <= 1 THEN min(Engagement_Score) END AS engagement_score,
               CASE WHEN count(DISTINCT Engagement_Tier) <= 1 THEN min(Engagement_Tier) END AS engagement_tier,
               CASE WHEN count(DISTINCT eng_short) <= 1 THEN min(eng_short) END AS eng_short
        FROM raw_r2_ces GROUP BY 1
    """)
    fhs_asof = cutoffs.get("fhs")
    ces_asof = cutoffs.get("ces")
    common = cutoffs.get("common_cutoff")
    con.execute(f"""
        CREATE TEMP TABLE r2_customer_segment AS
        SELECT coalesce(f.skp_client_id, e.skp_client_id) AS skp_client_id,
               f.financial_health_score, f.financial_health_tier, f.fh_short, f.fh_segment, f.fh_thin_file,
               e.engagement_score, e.engagement_tier, e.eng_short,
               coalesce(f.fhs_source_rows, 0) AS fhs_source_rows,
               coalesce(e.ces_source_rows, 0) AS ces_source_rows,
               coalesce(f.fhs_distinct_scores, 0) AS fhs_distinct_scores,
               coalesce(f.fhs_distinct_short_tiers, 0) AS fhs_distinct_short_tiers,
               coalesce(e.ces_distinct_scores, 0) AS ces_distinct_scores,
               coalesce(e.ces_distinct_short_tiers, 0) AS ces_distinct_short_tiers,
               CASE WHEN f.skp_client_id IS NULL THEN 'CES_ONLY'
                    WHEN e.skp_client_id IS NULL THEN 'FHS_ONLY'
                    WHEN f.fhs_distinct_scores > 1 OR e.ces_distinct_scores > 1
                      OR f.fhs_distinct_short_tiers > 1 OR e.ces_distinct_short_tiers > 1 THEN 'AMBIGUOUS_SCORE_VERSION'
                    ELSE 'FHS_CES_KEY_MATCHED' END AS score_join_state,
               CASE WHEN f.fh_short IN ('High','Medium','Low') AND e.eng_short IN ('High','Medium','Low')
                    THEN concat(f.fh_short, '_', e.eng_short) ELSE 'SEGMENT_UNAVAILABLE' END AS customer_segment,
               {sql_literal(fhs_asof or '')} AS fhs_as_of_date,
               {sql_literal(ces_asof or '')} AS ces_as_of_date,
               {sql_literal(cutoffs.get('fhs_validation_asof') or '')} AS fhs_validation_as_of_date,
               {sql_literal(cutoffs.get('ces_validation_asof') or '')} AS ces_validation_as_of_date,
               {sql_literal(common or '')} AS common_segment_outcome_cutoff,
               {sql_literal(cutoffs['cutoff_provenance_state'])} AS cutoff_provenance_state,
               (f.skp_client_id IS NOT NULL AND e.skp_client_id IS NOT NULL
                AND coalesce(f.fhs_distinct_scores, 0) <= 1 AND coalesce(e.ces_distinct_scores, 0) <= 1
                AND coalesce(f.fhs_distinct_short_tiers, 0) <= 1 AND coalesce(e.ces_distinct_short_tiers, 0) <= 1
                AND f.fh_short IN ('High','Medium','Low') AND e.eng_short IN ('High','Medium','Low')) AS segment_join_eligible
        FROM _r2_fhs f FULL OUTER JOIN _r2_ces e ON f.skp_client_id = e.skp_client_id
    """)

# %% [markdown]
# ## Product crosswalk, lead-event versions, and lead-contract candidates
#
# The leads source includes a normalized product field and an original code.
# Literal equality to a contract product is an auditable candidate only. The
# default crosswalk is empty until approved; direct credit-case keys remain
# validation evidence and do not override client/product/time predicates.

# %%
def create_product_crosswalk(con: duckdb.DuckDBPyConnection, aliases: dict[str, dict[str, str]]) -> None:
    lead_codes = con.execute("""
        SELECT lead_product_code, count(*) AS lead_rows,
               string_agg(DISTINCT lead_product_original_code, ' | ' ORDER BY lead_product_original_code)
                    FILTER (WHERE lead_product_original_code IS NOT NULL) AS original_codes
        FROM lead_event_version
        GROUP BY lead_product_code
    """).fetchall()
    contract_codes = con.execute("SELECT product_raw, count(*) AS contract_rows FROM contract_fact GROUP BY product_raw").fetchall()
    contract_by_normalized = {str(code).strip().upper(): (code, int(rows)) for code, rows in contract_codes if code is not None}
    rows: list[dict[str, Any]] = []
    approved = {(str(a).strip().upper(), str(b).strip().upper()): value for (a, b), value in C.APPROVED_PRODUCT_CROSSWALK.items()}
    for lead_code, lead_rows, originals in lead_codes:
        normalized = None if lead_code is None else str(lead_code).strip().upper()
        match = contract_by_normalized.get(normalized) if normalized is not None else None
        approved_entry = None
        if normalized is not None:
            for (a, b), value in approved.items():
                if a == normalized and (match is None or b == str(match[0]).strip().upper()):
                    approved_entry = (b, value)
                    break
        if approved_entry:
            contract_code, mapped_value = approved_entry
            rows.append({"lead_product_code": lead_code, "lead_product_original_codes": originals,
                         "contract_product_code": contract_code, "normalized_product": mapped_value,
                         "mapping_status": "APPROVED_COMPATIBLE", "approval_state": "OWNER_APPROVED_CONFIG",
                         "mapping_evidence": "Explicit configuration entry", "lead_rows": int(lead_rows),
                         "contract_rows": contract_by_normalized.get(str(contract_code).upper(), (None, 0))[1]})
        elif match:
            rows.append({"lead_product_code": lead_code, "lead_product_original_codes": originals,
                         "contract_product_code": match[0], "normalized_product": None,
                         "mapping_status": "EXACT_CODE_CANDIDATE", "approval_state": "NEEDS_OWNER_APPROVAL",
                         "mapping_evidence": "Normalized source code equals contract product text; not a validated crosswalk",
                         "lead_rows": int(lead_rows), "contract_rows": match[1]})
        else:
            rows.append({"lead_product_code": lead_code, "lead_product_original_codes": originals,
                         "contract_product_code": None, "normalized_product": None,
                         "mapping_status": "NO_APPROVED_MAP", "approval_state": "NEEDS_OWNER_APPROVAL",
                         "mapping_evidence": "No literal candidate found; original code retained",
                         "lead_rows": int(lead_rows), "contract_rows": 0})
    frame = pd.DataFrame(rows)
    con.execute("""
        CREATE TEMP TABLE product_crosswalk (
            lead_product_code VARCHAR, lead_product_original_codes VARCHAR,
            contract_product_code VARCHAR, normalized_product VARCHAR,
            mapping_status VARCHAR, approval_state VARCHAR, mapping_evidence VARCHAR,
            lead_rows BIGINT, contract_rows BIGINT
        )
    """)
    if not frame.empty:
        con.register("_product_crosswalk_df", frame)
        con.execute("INSERT INTO product_crosswalk SELECT * FROM _product_crosswalk_df")
        con.unregister("_product_crosswalk_df")
    con.execute("CREATE TEMP TABLE approved_product_crosswalk (lead_code VARCHAR, contract_code VARCHAR, normalized_product VARCHAR)")
    approved_rows = [{"lead_code": a, "contract_code": b, "normalized_product": value}
                     for (a, b), value in C.APPROVED_PRODUCT_CROSSWALK.items()]
    if approved_rows:
        approved_frame = pd.DataFrame(approved_rows)
        con.register("_approved_product_df", approved_frame)
        con.execute("INSERT INTO approved_product_crosswalk SELECT * FROM _approved_product_df")
        con.unregister("_approved_product_df")


def create_lead_contract_bridge(con: duckdb.DuckDBPyConnection) -> None:
    """Build criterion-qualified pairs and deterministically assign each contract once."""
    con.execute("""
        CREATE TEMP TABLE _lead_contract_candidate_pairs AS
        WITH compatible_pairs AS (
            SELECT l.lead_row_id, c.contract_fact_id, l.skp_credit_case_id,
                   c.skp_credit_case_id AS candidate_case_id
            FROM lead_event_version l
            JOIN contract_fact c ON l.skp_client_id = c.skp_client_id
            WHERE l.skp_client_id IS NOT NULL
              AND l.lead_product_code IS NOT NULL AND c.product_raw IS NOT NULL
              AND (upper(trim(l.lead_product_code)) = upper(trim(c.product_raw))
                   OR EXISTS (SELECT 1 FROM approved_product_crosswalk x
                              WHERE upper(trim(x.lead_code)) = upper(trim(l.lead_product_code))
                                AND upper(trim(x.contract_code)) = upper(trim(c.product_raw))))
              AND l.date_assigned_ts IS NOT NULL AND c.date_apply_ts IS NOT NULL
              AND l.date_assigned_ts <= c.date_apply_ts
        )
        SELECT lead_row_id, contract_fact_id,
               bool_or(skp_credit_case_id IS NOT NULL AND skp_credit_case_id = candidate_case_id) AS via_direct_case_key,
               TRUE AS via_client_product,
               CASE WHEN bool_or(skp_credit_case_id IS NOT NULL AND skp_credit_case_id = candidate_case_id)
                    THEN 'DIRECT_CASE_KEY_VALIDATED_BY_CLIENT_PRODUCT_TIME'
                    ELSE 'SAME_CLIENT_PRODUCT_TIME_CANDIDATE' END AS candidate_evidence
        FROM compatible_pairs GROUP BY lead_row_id, contract_fact_id
    """)
    con.execute("""
        CREATE TEMP TABLE _lead_temporal_rejections AS
        WITH compatible_pairs AS (
            SELECT l.lead_row_id, c.contract_fact_id
            FROM lead_event_version l JOIN contract_fact c ON l.skp_client_id = c.skp_client_id
            WHERE l.skp_client_id IS NOT NULL AND l.lead_product_code IS NOT NULL AND c.product_raw IS NOT NULL
              AND (upper(trim(l.lead_product_code)) = upper(trim(c.product_raw))
                   OR EXISTS (SELECT 1 FROM approved_product_crosswalk x
                              WHERE upper(trim(x.lead_code)) = upper(trim(l.lead_product_code))
                                AND upper(trim(x.contract_code)) = upper(trim(c.product_raw))))
              AND l.date_assigned_ts IS NOT NULL AND c.date_apply_ts IS NOT NULL
              AND l.date_assigned_ts > c.date_apply_ts
        )
        SELECT lead_row_id, count(DISTINCT contract_fact_id) AS temporal_fail_candidate_count
        FROM compatible_pairs GROUP BY lead_row_id
    """)
    con.execute("""
        CREATE TEMP TABLE _lead_temporal_unknowns AS
        WITH compatible_pairs AS (
            SELECT l.lead_row_id, c.contract_fact_id
            FROM lead_event_version l JOIN contract_fact c ON l.skp_client_id = c.skp_client_id
            WHERE l.skp_client_id IS NOT NULL AND l.lead_product_code IS NOT NULL AND c.product_raw IS NOT NULL
              AND (upper(trim(l.lead_product_code)) = upper(trim(c.product_raw))
                   OR EXISTS (SELECT 1 FROM approved_product_crosswalk x
                              WHERE upper(trim(x.lead_code)) = upper(trim(l.lead_product_code))
                                AND upper(trim(x.contract_code)) = upper(trim(c.product_raw))))
              AND (l.date_assigned_ts IS NULL OR c.date_apply_ts IS NULL)
        )
        SELECT lead_row_id, count(DISTINCT contract_fact_id) AS temporal_unknown_candidate_count
        FROM compatible_pairs GROUP BY lead_row_id
    """)
    con.execute("""
        CREATE TEMP TABLE lead_contract_bridge AS
        WITH expanded AS (
            SELECT l.lead_row_id, c.contract_fact_id, c.skp_credit_case_id AS candidate_skp_credit_case_id,
                   c.skp_client_id AS candidate_skp_client_id, c.skp_salesroom_id AS booking_shop_id,
                   c.product_raw AS contract_product_raw, c.contract_status_raw,
                   c.date_apply_ts AS contract_apply_ts, c.credit_amount_raw AS candidate_credit_amount_raw,
                   c.is_funded, p.via_direct_case_key, p.via_client_product, p.candidate_evidence,
                   l.skp_client_id AS lead_skp_client_id, l.skp_credit_case_id AS lead_skp_credit_case_id,
                   l.skp_salesroom_id AS lead_origin_shop_id, l.lead_product_code, l.lead_product_original_code,
                   l.date_assigned_ts, l.lead_row_id AS lead_id, l.lead_uuid
            FROM _lead_contract_candidate_pairs p
            JOIN lead_event_version l USING (lead_row_id)
            JOIN contract_fact c USING (contract_fact_id)
        ), evaluated AS (
            SELECT *,
                   TRUE AS client_match, 'CLIENT_MATCH' AS client_match_state,
                   CASE WHEN EXISTS (SELECT 1 FROM approved_product_crosswalk x
                                     WHERE upper(trim(x.lead_code)) = upper(trim(lead_product_code))
                                       AND upper(trim(x.contract_code)) = upper(trim(contract_product_raw)))
                        THEN 'APPROVED_COMPATIBLE'
                        WHEN upper(trim(lead_product_code)) = upper(trim(contract_product_raw))
                        THEN 'EXACT_MATCH_UNAPPROVED' ELSE 'UNMAPPED_OR_INCOMPATIBLE' END AS product_compatibility_state,
                   'PASS' AS temporal_state
            FROM expanded
        ), ranked AS (
            SELECT *,
                   CASE WHEN product_compatibility_state = 'APPROVED_COMPATIBLE' THEN 'MATCHED'
                        WHEN product_compatibility_state = 'EXACT_MATCH_UNAPPROVED' THEN 'PRODUCT_MAPPING_UNAPPROVED'
                        ELSE 'PRODUCT_UNMAPPED_OR_INCOMPATIBLE' END AS match_status,
                   (product_compatibility_state = 'APPROVED_COMPATIBLE') AS is_confirmed_match,
                   row_number() OVER (PARTITION BY contract_fact_id
                     ORDER BY CASE WHEN product_compatibility_state = 'APPROVED_COMPATIBLE' THEN 0 ELSE 1 END,
                              date_assigned_ts DESC, lead_row_id) AS primary_rank
            FROM evaluated
        )
        SELECT *, (is_confirmed_match AND primary_rank = 1) AS is_primary_match,
               (is_confirmed_match AND primary_rank = 1
                AND lead_skp_credit_case_id IS NOT DISTINCT FROM candidate_skp_credit_case_id
                AND lead_skp_credit_case_id IS NOT NULL) AS direct_key_agrees_with_primary
        FROM ranked
    """)
    con.execute("""
        CREATE TEMP TABLE lead_match_summary AS
        WITH candidate_summary AS (
            SELECT lead_row_id, count(*) AS candidate_contract_count,
                   count(*) FILTER (WHERE via_direct_case_key) AS direct_case_candidate_count,
                   count(*) FILTER (WHERE via_client_product) AS same_client_product_candidate_count,
                   count(*) FILTER (WHERE is_confirmed_match) AS confirmed_match_count,
                   count(*) FILTER (WHERE match_status = 'PRODUCT_MAPPING_UNAPPROVED') AS unapproved_product_candidate_count
            FROM lead_contract_bridge GROUP BY lead_row_id
        ), summarized AS (
            SELECT l.lead_row_id, l.lead_uuid, l.skp_client_id,
                   coalesce(c.candidate_contract_count, 0) AS candidate_contract_count,
                   coalesce(c.direct_case_candidate_count, 0) AS direct_case_candidate_count,
                   coalesce(c.same_client_product_candidate_count, 0) AS same_client_product_candidate_count,
                   coalesce(c.confirmed_match_count, 0) AS confirmed_match_count,
                   coalesce(c.unapproved_product_candidate_count, 0) AS unapproved_product_candidate_count,
                   coalesce(r.temporal_fail_candidate_count, 0) AS temporal_fail_candidate_count,
                   coalesce(u.temporal_unknown_candidate_count, 0) AS temporal_unknown_candidate_count
            FROM lead_event_version l
            LEFT JOIN candidate_summary c USING (lead_row_id)
            LEFT JOIN _lead_temporal_rejections r USING (lead_row_id)
            LEFT JOIN _lead_temporal_unknowns u USING (lead_row_id)
        )
        SELECT *, (candidate_contract_count + temporal_fail_candidate_count + temporal_unknown_candidate_count > 1) AS is_ambiguous,
               CASE WHEN candidate_contract_count = 0 AND temporal_fail_candidate_count > 0 THEN 'TEMPORAL_FAIL'
                    WHEN candidate_contract_count = 0 AND temporal_unknown_candidate_count > 0 THEN 'TEMPORAL_UNKNOWN'
                    WHEN candidate_contract_count = 0 THEN 'UNMATCHED_NO_CANDIDATE'
                    WHEN confirmed_match_count = 1 THEN 'UNIQUE_CONFIRMED_MATCH'
                    WHEN confirmed_match_count > 1 THEN 'AMBIGUOUS_CONFIRMED_MATCHES'
                    WHEN unapproved_product_candidate_count > 0 THEN 'PRODUCT_MAPPING_UNAPPROVED'
                    ELSE 'CANDIDATE_REQUIRES_REVIEW' END AS lead_match_state
        FROM summarized
    """)

# %% [markdown]
# ## Canonical shop, employee, and customer-segment bridges
#
# Fact-to-dimension joins are left joins against pre-aggregated one-row-per-key
# dimensions. Repeated lead UUIDs, duplicate product details, unmapped shops,
# and unlinked R2 customers remain visible in bridge/audit outputs.

# %%
def create_fact_bridges(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TEMP TABLE contract_shop_bridge AS
        SELECT c.*, s.master_record_id AS shop_master_record_id,
               s.salesroom_category, s.salesroom_model, s.salesroom_product, s.salesroom_status,
               s.salesroom_town, s.salesroom_district, s.salesroom_province, s.salesroom_area,
               s.master_version_state AS shop_master_version_state,
               s.attribute_vintage AS shop_attribute_vintage,
               CASE WHEN c.skp_salesroom_id IS NULL THEN 'MISSING_FACT_SHOP_KEY'
                    WHEN s.master_record_id IS NULL THEN 'UNMATCHED_CURRENT_SHOP_MASTER'
                    ELSE 'CURRENT_SHOP_MASTER_MATCHED' END AS shop_match_state
        FROM contract_fact c
        LEFT JOIN shop_bridge s ON c.skp_salesroom_id = s.skp_salesroom_id
    """)
    con.execute("""
        CREATE TEMP TABLE lead_shop_bridge AS
        SELECT l.*, s.master_record_id AS shop_master_record_id,
               s.salesroom_category, s.salesroom_model, s.salesroom_product, s.salesroom_status,
               s.salesroom_town, s.salesroom_district, s.salesroom_province, s.salesroom_area,
               s.master_version_state AS shop_master_version_state,
               s.attribute_vintage AS shop_attribute_vintage,
               CASE WHEN l.skp_salesroom_id IS NULL THEN 'MISSING_FACT_SHOP_KEY'
                    WHEN s.master_record_id IS NULL THEN 'UNMATCHED_CURRENT_SHOP_MASTER'
                    ELSE 'CURRENT_SHOP_MASTER_MATCHED' END AS shop_match_state
        FROM lead_event_version l
        LEFT JOIN shop_bridge s ON l.skp_salesroom_id = s.skp_salesroom_id
    """)
    con.execute("""
        CREATE TEMP TABLE contract_customer_segment_bridge AS
        SELECT c.*, r.fh_short, r.eng_short, r.customer_segment, r.fh_thin_file,
               r.score_join_state, r.segment_join_eligible,
               CASE WHEN r.skp_client_id IS NULL THEN 'NO_R2_SCORE_KEY' ELSE r.score_join_state END AS r2_link_state,
               c.after_common_r2_cutoff AS post_score_event_date_eligible
        FROM contract_fact c
        LEFT JOIN r2_customer_segment r ON c.skp_client_id = r.skp_client_id
    """)
    con.execute("""
        CREATE TEMP TABLE lead_customer_segment_bridge AS
        SELECT l.*, r.fh_short, r.eng_short, r.customer_segment, r.fh_thin_file,
               r.score_join_state, r.segment_join_eligible,
               CASE WHEN r.skp_client_id IS NULL THEN 'NO_R2_SCORE_KEY' ELSE r.score_join_state END AS r2_link_state,
               l.after_common_r2_cutoff AS post_score_event_date_eligible
        FROM lead_event_version l
        LEFT JOIN r2_customer_segment r ON l.skp_client_id = r.skp_client_id
    """)


def create_status_dimensions(con: duckdb.DuckDBPyConnection) -> None:
    configured_rows = [{"contract_status_raw": str(raw), "business_outcome": str(outcome)}
                       for raw, outcome in C.APPROVED_CONTRACT_OUTCOME_MAP.items()]
    con.execute("CREATE TEMP TABLE _configured_contract_status (contract_status_raw VARCHAR, business_outcome VARCHAR)")
    if configured_rows:
        configured = pd.DataFrame(configured_rows)
        con.register("_configured_status_df", configured)
        con.execute("INSERT INTO _configured_contract_status SELECT * FROM _configured_status_df")
        con.unregister("_configured_status_df")
    con.execute("""
        CREATE TEMP TABLE contract_status_mapping AS
        WITH observed AS (
            SELECT contract_status_raw, count(*) AS source_rows
            FROM contract_event_version GROUP BY contract_status_raw
        )
        SELECT o.contract_status_raw, o.source_rows,
               coalesce(c.business_outcome, 'UNMAPPED') AS business_outcome,
               CASE WHEN c.business_outcome IS NULL THEN 'OWNER_APPROVAL_REQUIRED' ELSE 'OWNER_APPROVED_CONFIG' END AS definition_state,
               'Status preserved as supplied; funded/application semantics are not inferred.' AS definition_note
        FROM observed o LEFT JOIN _configured_contract_status c USING (contract_status_raw)
    """)


def create_monthly_tables(con: duckdb.DuckDBPyConnection, common_cutoff: str | None) -> None:
    con.execute("""
        CREATE TEMP TABLE contract_shop_month_status AS
        SELECT skp_salesroom_id, date_trunc('month', date_apply_ts)::DATE AS month_start,
               contract_status_raw AS raw_status, business_outcome,
               count(*) AS application_event_rows,
               count(DISTINCT skp_credit_case_id) AS distinct_credit_cases,
               count(DISTINCT skp_client_id) AS distinct_customers,
               sum(credit_amount_raw) AS credit_amount_raw_sum,
               count(credit_amount_raw) AS credit_amount_nonnull_rows,
               'UNVALIDATED_SOURCE_CREDIT_AMOUNT' AS amount_semantics_state
        FROM contract_fact
        WHERE date_apply_ts IS NOT NULL
        GROUP BY 1, 2, 3, 4
    """)
    con.execute("""
        CREATE TEMP TABLE contract_shop_month AS
        SELECT skp_salesroom_id, date_trunc('month', date_apply_ts)::DATE AS month_start,
               business_outcome,
               count(*) AS application_event_rows,
               count(DISTINCT skp_credit_case_id) AS distinct_credit_cases,
               count(DISTINCT skp_client_id) AS distinct_customers,
               sum(credit_amount_raw) AS credit_amount_raw_sum,
               count(credit_amount_raw) AS credit_amount_nonnull_rows,
               CASE WHEN business_outcome = 'UNMAPPED' THEN 'OWNER_APPROVAL_REQUIRED' ELSE 'OWNER_APPROVED_CONFIG' END AS outcome_definition_state,
               'UNVALIDATED_SOURCE_CREDIT_AMOUNT' AS amount_semantics_state
        FROM contract_fact
        WHERE date_apply_ts IS NOT NULL
        GROUP BY 1, 2, 3
    """)
    con.execute("""
        CREATE TEMP TABLE contract_shop_month_total AS
        SELECT skp_salesroom_id, date_trunc('month', date_apply_ts)::DATE AS month_start,
               count(*) AS application_event_rows,
               count(DISTINCT skp_credit_case_id) AS distinct_credit_cases,
               count(DISTINCT skp_client_id) AS distinct_customers,
               sum(credit_amount_raw) AS credit_amount_raw_sum,
               count(*) FILTER (WHERE is_funded) AS funded_contract_count,
               sum(credit_amount_raw) FILTER (WHERE is_funded) AS funded_credit_amount_raw_sum,
               count(credit_amount_raw) AS credit_amount_nonnull_rows,
               'STATUS_DISTRIBUTION_SEPARATE; NO OUTCOME CLAIM' AS outcome_definition_state,
               'UNVALIDATED_SOURCE_CREDIT_AMOUNT' AS amount_semantics_state
        FROM contract_fact
        WHERE date_apply_ts IS NOT NULL
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE TEMP TABLE lead_shop_month_product AS
        WITH primary_by_lead AS (
            SELECT lead_row_id,
                   count(DISTINCT contract_fact_id) FILTER (WHERE is_primary_match) AS primary_matched_contracts,
                   count(DISTINCT contract_fact_id) FILTER (WHERE is_primary_match AND is_funded) AS funded_primary_matched_contracts
            FROM lead_contract_bridge GROUP BY lead_row_id
        )
        SELECT l.skp_salesroom_id AS lead_origin_shop_id,
               date_trunc('month', l.date_assigned_ts)::DATE AS month_start,
               l.lead_product_code,
               count(*) AS lead_event_rows,
               count(DISTINCT l.lead_uuid) AS distinct_lead_uuids,
               count(DISTINCT l.skp_client_id) AS distinct_customers,
               NULL::BIGINT AS exact_duplicate_event_rows,
               sum(l.sample_weight) AS raw_weight_sensitivity_sum_qa_only,
               count(*) FILTER (WHERE m.confirmed_match_count > 0) AS event_rows_with_confirmed_match,
               count(*) FILTER (WHERE m.lead_match_state = 'PRODUCT_MAPPING_UNAPPROVED') AS event_rows_product_mapping_unapproved,
               sum(coalesce(p.primary_matched_contracts,0)) AS primary_matched_contracts,
               sum(coalesce(p.funded_primary_matched_contracts,0)) AS funded_primary_matched_contracts,
               'UNAPPROVED_QA_ONLY; RAW EVENT ROWS ARE PRIMARY' AS weight_status
        FROM lead_event_version l
        LEFT JOIN lead_match_summary m USING (lead_row_id)
        LEFT JOIN primary_by_lead p USING (lead_row_id)
        WHERE l.date_assigned_ts IS NOT NULL
        GROUP BY 1, 2, 3
    """)
    con.execute("""
        CREATE TEMP TABLE lead_conversion_shop_month AS
        SELECT b.lead_origin_shop_id, b.booking_shop_id,
               date_trunc('month', b.contract_apply_ts)::DATE AS month_start,
               x.normalized_product,
               count(DISTINCT b.contract_fact_id) FILTER (WHERE b.is_primary_match) AS primary_matched_contracts,
               count(DISTINCT b.contract_fact_id) FILTER (WHERE b.is_primary_match AND b.is_funded) AS funded_primary_matched_contracts,
               sum(b.candidate_credit_amount_raw) FILTER (WHERE b.is_primary_match) AS matched_credit_amount_raw,
               origin.salesroom_category AS lead_origin_shop_category,
               booking.salesroom_category AS booking_shop_category,
               (b.lead_origin_shop_id IS NOT NULL AND b.booking_shop_id IS NOT NULL
                AND b.lead_origin_shop_id <> b.booking_shop_id) AS is_cross_shop,
               (origin.salesroom_category IS NOT NULL AND booking.salesroom_category IS NOT NULL
                AND origin.salesroom_category <> booking.salesroom_category) AS is_cross_category
        FROM lead_contract_bridge b
        JOIN approved_product_crosswalk x
          ON upper(trim(x.lead_code)) = upper(trim(b.lead_product_code))
         AND upper(trim(x.contract_code)) = upper(trim(b.contract_product_raw))
        LEFT JOIN shop_bridge origin ON b.lead_origin_shop_id = origin.skp_salesroom_id
        LEFT JOIN shop_bridge booking ON b.booking_shop_id = booking.skp_salesroom_id
        WHERE b.is_primary_match AND b.is_confirmed_match AND b.contract_apply_ts IS NOT NULL
        GROUP BY 1, 2, 3, 4, 8, 9, 10, 11
    """)
    con.execute("""
        CREATE TEMP TABLE shop_behavior_profile AS
        WITH contract_month AS (
            SELECT skp_salesroom_id, date_trunc('month', date_apply_ts)::DATE AS month_start,
                   count(*) AS contracts, avg(CASE WHEN is_funded THEN 1.0 ELSE 0.0 END) AS funded_share
            FROM contract_fact WHERE date_apply_ts IS NOT NULL GROUP BY 1, 2
        ), lead_month AS (
            SELECT skp_salesroom_id, date_trunc('month', date_assigned_ts)::DATE AS month_start,
                   count(*) AS leads
            FROM lead_event_version WHERE date_assigned_ts IS NOT NULL GROUP BY 1, 2
        ), observed_month AS (
            SELECT skp_salesroom_id, month_start FROM contract_month
            UNION SELECT skp_salesroom_id, month_start FROM lead_month
        ), shop_metrics AS (
            SELECT o.skp_salesroom_id, count(*) AS observed_months,
                   min(o.month_start) AS first_observed_month, max(o.month_start) AS last_observed_month,
                   count(*) FILTER (WHERE coalesce(l.leads, 0) > 0)::DOUBLE / nullif(count(*), 0) AS share_of_months_with_leads
            FROM observed_month o LEFT JOIN lead_month l USING (skp_salesroom_id, month_start)
            GROUP BY o.skp_salesroom_id
        ), contract_metrics AS (
            SELECT skp_salesroom_id, count(*) AS observed_contract_months,
                   avg(contracts::DOUBLE) AS avg_contracts_per_observed_month,
                   avg(funded_share) AS avg_funded_share
            FROM contract_month GROUP BY skp_salesroom_id
        ), leads AS (
            SELECT skp_salesroom_id, count(*) AS lead_volume,
                   count(*) FILTER (WHERE upper(trim(coalesce(lead_product_code,''))) = 'TW')::DOUBLE / nullif(count(*),0) AS product_mix_share_tw,
                   count(*) FILTER (WHERE upper(trim(coalesce(lead_product_code,''))) = 'CL')::DOUBLE / nullif(count(*),0) AS product_mix_share_cl,
                   count(*) FILTER (WHERE upper(trim(coalesce(lead_product_code,''))) = 'CC')::DOUBLE / nullif(count(*),0) AS product_mix_share_cc,
                   count(*) FILTER (WHERE upper(trim(coalesce(lead_product_code,''))) = 'CD')::DOUBLE / nullif(count(*),0) AS product_mix_share_cd,
                   count(*) FILTER (WHERE upper(trim(coalesce(lead_product_code,''))) NOT IN ('TW','CL','CC','CD'))::DOUBLE / nullif(count(*),0) AS product_mix_share_other
            FROM lead_event_version GROUP BY skp_salesroom_id
        ), universe AS (
            SELECT skp_salesroom_id FROM contract_fact
            UNION SELECT skp_salesroom_id FROM lead_event_version
        )
        SELECT u.skp_salesroom_id, coalesce(c.observed_contract_months, 0) AS observed_contract_months,
               c.avg_contracts_per_observed_month, c.avg_funded_share, coalesce(l.lead_volume, 0) AS lead_volume,
               l.product_mix_share_tw, l.product_mix_share_cl, l.product_mix_share_cc,
               l.product_mix_share_cd, l.product_mix_share_other,
               m.share_of_months_with_leads, m.first_observed_month, m.last_observed_month,
               (s.master_record_id IS NOT NULL) AS master_matched_flag
        FROM universe u LEFT JOIN contract_metrics c USING (skp_salesroom_id)
        LEFT JOIN leads l USING (skp_salesroom_id)
        LEFT JOIN shop_metrics m USING (skp_salesroom_id)
        LEFT JOIN shop_bridge s ON u.skp_salesroom_id = s.skp_salesroom_id
    """)

    # Month range is derived only from observed source event timestamps.
    bounds = con.execute("""
        SELECT min(month_value), max(month_value) FROM (
            SELECT date_trunc('month', date_apply_ts)::DATE month_value FROM contract_fact WHERE date_apply_ts IS NOT NULL
            UNION ALL
            SELECT date_trunc('month', date_assigned_ts)::DATE FROM lead_event_version WHERE date_assigned_ts IS NOT NULL
        )
    """).fetchone()
    if bounds[0] is None:
        con.execute("CREATE TEMP TABLE _observed_months(month_start DATE)")
    else:
        con.execute(f"""
            CREATE TEMP TABLE _observed_months AS
            SELECT unnest(generate_series(DATE {sql_literal(bounds[0].isoformat())}, DATE {sql_literal(bounds[1].isoformat())}, INTERVAL '1 month'))::DATE AS month_start
        """)
    con.execute("""
        CREATE TEMP TABLE _shop_universe AS
        SELECT DISTINCT skp_salesroom_id FROM shop_bridge
        UNION
        SELECT DISTINCT skp_salesroom_id FROM contract_fact
        UNION
        SELECT DISTINCT skp_salesroom_id FROM lead_event_version
    """)
    con.execute("""
        CREATE TEMP TABLE _shop_month_calendar AS
        SELECT s.skp_salesroom_id, m.month_start,
               date_trunc('month', m.month_start)::DATE AS month_start_key
        FROM _shop_universe s CROSS JOIN _observed_months m
    """)
    con.execute(f"""
        CREATE TEMP TABLE employee_shop_month AS
        SELECT cal.skp_salesroom_id, cal.month_start,
               count(DISTINCT e.skp_employee_id) FILTER (
                   WHERE e.assignment_interval_state IN ('VALID_BOUNDED_INTERVAL','VALID_OPEN_ENDED_SENTINEL')
                     AND e.valid_from_ts < cal.month_start + INTERVAL '1 month'
                     AND (e.valid_to_ts IS NULL OR e.valid_to_ts >= cal.month_start)
               ) AS assigned_employee_count_raw,
               count(*) FILTER (
                   WHERE e.assignment_interval_state IN ('VALID_BOUNDED_INTERVAL','VALID_OPEN_ENDED_SENTINEL')
                     AND e.valid_from_ts < cal.month_start + INTERVAL '1 month'
                     AND (e.valid_to_ts IS NULL OR e.valid_to_ts >= cal.month_start)
               ) AS assignment_interval_rows,
               {active_headcount_expression()} AS active_headcount_proxy,
               CASE WHEN {sql_literal(','.join(sorted(C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES)))} = ''
                    THEN 'STATUS_CODES_UNAPPROVED' ELSE 'STATUS_CODES_CONFIGURED' END AS headcount_proxy_state
        FROM _shop_month_calendar cal
        LEFT JOIN employee_shop_bridge e ON cal.skp_salesroom_id = e.skp_salesroom_id
        GROUP BY cal.skp_salesroom_id, cal.month_start
    """)
    con.execute("""
        CREATE TEMP TABLE shop_month_foundation AS
        SELECT cal.skp_salesroom_id, cal.month_start,
               shop.master_record_id AS shop_master_record_id,
               shop.salesroom_category, shop.salesroom_model, shop.salesroom_product, shop.salesroom_status,
               shop.salesroom_province, shop.salesroom_area,
               coalesce(c.application_event_rows, 0) AS contract_application_event_rows,
               coalesce(c.distinct_credit_cases, 0) AS contract_distinct_credit_cases,
               coalesce(c.distinct_customers, 0) AS contract_distinct_customers,
               c.credit_amount_raw_sum AS contract_credit_amount_raw_sum,
               coalesce(c.funded_contract_count, 0) AS funded_contract_count,
               c.funded_credit_amount_raw_sum AS funded_credit_amount_raw_sum,
               coalesce(l.lead_event_rows, 0) AS lead_event_rows,
               coalesce(l.distinct_lead_uuids, 0) AS distinct_lead_uuids,
               coalesce(l.distinct_customers, 0) AS lead_distinct_customers,
               l.raw_weight_sensitivity_sum_qa_only,
               e.assigned_employee_count_raw, e.assignment_interval_rows, e.active_headcount_proxy, e.headcount_proxy_state,
               CASE WHEN c.application_event_rows IS NOT NULL OR l.lead_event_rows IS NOT NULL THEN 'OBSERVED_EVENT_ROWS'
                    ELSE 'NO_EVENT_OBSERVED_NOT_ZERO_ACTIVITY' END AS event_coverage_state,
               CASE WHEN shop.master_record_id IS NULL THEN 'UNMATCHED_CURRENT_SHOP_MASTER'
                    ELSE shop.master_version_state END AS shop_master_state,
               'CURRENT_MASTER_SNAPSHOT_NOT_HISTORICAL_ASOF' AS shop_attribute_vintage,
               coalesce(c.outcome_definition_state, 'NO_CONTRACT_EVENT_IN_MONTH') AS outcome_definition_state,
               coalesce(c.amount_semantics_state, 'NO_CONTRACT_AMOUNT_IN_MONTH') AS amount_semantics_state,
               coalesce(l.weight_status, 'NO_LEAD_EVENT_IN_MONTH') AS weight_status
        FROM _shop_month_calendar cal
        LEFT JOIN shop_bridge shop ON cal.skp_salesroom_id IS NOT NULL AND cal.skp_salesroom_id = shop.skp_salesroom_id
        LEFT JOIN contract_shop_month_total c ON cal.skp_salesroom_id IS NOT DISTINCT FROM c.skp_salesroom_id AND cal.month_start = c.month_start
        LEFT JOIN (
            SELECT skp_salesroom_id, date_trunc('month', date_assigned_ts)::DATE AS month_start,
                   count(*) AS lead_event_rows,
                   count(DISTINCT lead_uuid) AS distinct_lead_uuids,
                   count(DISTINCT skp_client_id) AS distinct_customers,
                   sum(sample_weight) AS raw_weight_sensitivity_sum_qa_only,
                   'UNAPPROVED_QA_ONLY; RAW EVENT ROWS ARE PRIMARY' AS weight_status
            FROM lead_event_version
            WHERE date_assigned_ts IS NOT NULL
            GROUP BY 1, 2
        ) l ON cal.skp_salesroom_id IS NOT DISTINCT FROM l.skp_salesroom_id AND cal.month_start = l.month_start
        LEFT JOIN employee_shop_month e ON cal.skp_salesroom_id IS NOT DISTINCT FROM e.skp_salesroom_id AND cal.month_start = e.month_start
    """)
    create_segment_event_aggregate(con, common_cutoff)


def active_headcount_expression() -> str:
    statuses = sorted(str(status).upper() for status in C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES)
    if not statuses:
        return "NULL::BIGINT"
    values = ", ".join(sql_literal(value) for value in statuses)
    return f"count(DISTINCT e.skp_employee_id) FILTER (WHERE upper(trim(e.code_status_raw)) IN ({values}) AND e.assignment_interval_state IN ('VALID_BOUNDED_INTERVAL','VALID_OPEN_ENDED_SENTINEL') AND e.valid_from_ts < cal.month_start + INTERVAL '1 month' AND (e.valid_to_ts IS NULL OR e.valid_to_ts >= cal.month_start))"


def create_segment_event_aggregate(con: duckdb.DuckDBPyConnection, common_cutoff: str | None) -> None:
    if common_cutoff:
        con.execute("""
            CREATE TEMP TABLE customer_segment_shop_product_month AS
            WITH events AS (
                SELECT c.skp_salesroom_id AS shop_id, date_trunc('month', c.date_apply_ts)::DATE AS month_start,
                       c.product_raw AS product_code, coalesce(c.customer_segment, 'NO_R2_SEGMENT') AS customer_segment,
                       'CONTRACT_APPLICATION' AS event_role, c.skp_client_id AS skp_client_id,
                       1::BIGINT AS event_rows, NULL::DOUBLE AS raw_weight_sensitivity_sum_qa_only
                FROM contract_customer_segment_bridge c
                WHERE c.date_apply_ts IS NOT NULL AND c.after_common_r2_cutoff
                UNION ALL
                SELECT l.skp_salesroom_id, date_trunc('month', l.date_assigned_ts)::DATE,
                       l.lead_product_code, coalesce(l.customer_segment, 'NO_R2_SEGMENT'),
                       'LEAD_ORIGIN', l.skp_client_id, 1::BIGINT, l.sample_weight
                FROM lead_customer_segment_bridge l
                WHERE l.date_assigned_ts IS NOT NULL AND l.after_common_r2_cutoff
            )
            SELECT shop_id, month_start, product_code, customer_segment, event_role,
                   sum(event_rows) AS raw_event_rows,
                   count(DISTINCT skp_client_id) AS distinct_customers,
                   sum(raw_weight_sensitivity_sum_qa_only) AS raw_weight_sensitivity_sum_qa_only,
                   'WEIGHTS_UNAPPROVED; DISTINCT_CUSTOMERS_NEVER_WEIGHTED' AS weight_status
            FROM events
            GROUP BY 1, 2, 3, 4, 5
        """)
    else:
        con.execute("""
            CREATE TEMP TABLE customer_segment_shop_product_month AS
            SELECT NULL::BIGINT AS shop_id, NULL::DATE AS month_start, NULL::VARCHAR AS product_code,
                   NULL::VARCHAR AS customer_segment, NULL::VARCHAR AS event_role,
                   0::BIGINT AS raw_event_rows, 0::BIGINT AS distinct_customers,
                   NULL::DOUBLE AS raw_weight_sensitivity_sum_qa_only,
                   'DISABLED_NO_VERIFIABLE_ROUND2_CUTOFF' AS weight_status
            WHERE FALSE
        """)

# %% [markdown]
# ## Coverage summaries, outcome definitions, and data-quality gates
#
# Unknown/current-only facts remain flagged. Raw event counts and amount sums
# are not renamed as funded sales. The machine-readable validation report
# separates fatal structural invariants from conditional business gates.

# %%
def table_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {quote_identifier(table)}").fetchone()[0])


def build_weight_audit(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TEMP TABLE weight_audit AS
        SELECT id_lead_source AS lead_source_raw, lead_product_code, lead_product_original_code,
               sample_weight, count(*) AS source_rows,
               sum(sample_weight) AS raw_weight_sensitivity_sum_qa_only,
               count(*) FILTER (WHERE sample_weight IS NULL) AS missing_weight_rows,
               count(*) FILTER (WHERE sample_weight IS NOT NULL AND sample_weight <= 0) AS nonpositive_weight_rows,
               'UNAPPROVED_QA_ONLY_NOT_A_POPULATION_ESTIMATE' AS interpretation_state
        FROM lead_event_version
        GROUP BY 1, 2, 3, 4
    """)


def build_r2_coverage(con: duckdb.DuckDBPyConnection, cutoff: str | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    score_stats = con.execute("""
        SELECT (SELECT count(*) FROM raw_r2_fhs) AS fhs_rows,
               (SELECT count(DISTINCT try_cast(SKP_CLIENT AS BIGINT)) FROM raw_r2_fhs) AS fhs_clients,
               (SELECT count(*) FROM raw_r2_ces) AS ces_rows,
               (SELECT count(DISTINCT try_cast(SKP_CLIENT AS BIGINT)) FROM raw_r2_ces) AS ces_clients,
               (SELECT count(*) FROM r2_customer_segment WHERE score_join_state = 'FHS_CES_KEY_MATCHED') AS paired_clients,
               (SELECT count(*) FROM r2_customer_segment WHERE score_join_state <> 'FHS_CES_KEY_MATCHED') AS unpaired_or_ambiguous_clients
    """).fetchone()
    rows.append({"population": "R2_SCORE_FILES", "temporal_window": "ALL", "source_rows": None,
                 "distinct_customers": None, "customers_with_segment": int(score_stats[4]),
                 "event_rows_with_segment": None, "coverage_pct": None,
                 "note": f"FHS {score_stats[0]:,} rows/{score_stats[1]:,} clients; CES {score_stats[2]:,}/{score_stats[3]:,}; {score_stats[5]:,} unpaired/ambiguous."})
    for kind, table, timestamp_field in [
        ("CONTRACT_APPLICATIONS", "contract_fact", "date_apply_ts"),
        ("LEAD_ASSIGNMENTS", "lead_event_version", "date_assigned_ts"),
    ]:
        for window in ("ALL", "STRICTLY_POST_COMMON_CUTOFF"):
            if window != "ALL" and not cutoff:
                rows.append({"population": kind, "temporal_window": window, "source_rows": None,
                             "distinct_customers": None, "customers_with_segment": None,
                             "event_rows_with_segment": None, "coverage_pct": None,
                             "note": "Disabled: Round 2 cutoff unavailable from source config."})
                continue
            predicate = "TRUE" if window == "ALL" else f"{timestamp_field} IS NOT NULL AND ({post_score_date_predicate(timestamp_field, cutoff)})"
            metrics = con.execute(f"""
                SELECT count(*) AS event_rows,
                       count(DISTINCT e.skp_client_id) AS distinct_customers,
                       count(*) FILTER (WHERE r.segment_join_eligible) AS segment_eligible_event_rows,
                       count(DISTINCT e.skp_client_id) FILTER (WHERE r.segment_join_eligible) AS segment_eligible_customers
                FROM {quote_identifier(table)} e
                LEFT JOIN r2_customer_segment r ON e.skp_client_id = r.skp_client_id
                WHERE {predicate}
            """).fetchone()
            rows.append({"population": kind, "temporal_window": window, "source_rows": int(metrics[0]),
                         "distinct_customers": int(metrics[1]), "customers_with_segment": int(metrics[3]),
                         "event_rows_with_segment": int(metrics[2]),
                         "coverage_pct": round(100 * metrics[3] / metrics[1], 4) if metrics[1] else None,
                         "note": "Distinct clients are unweighted; duplicated lead UUID/version rows remain event rows."})
    return pd.DataFrame(rows)


def build_coverage_summary(con: duckdb.DuckDBPyConnection, inventory: list[dict[str, Any]], r2_coverage: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for item in inventory:
        records.append({"coverage_area": "RAW_SOURCE", "population": item["dataset"], "numerator": item.get("source_rows"),
                        "denominator": item.get("source_rows"), "coverage_pct": 100.0 if item.get("source_rows") is not None else None,
                        "status": "INVENTORIED", "details": f"{item['file_name']}; {item['source_columns']} columns; {item['source_bytes']:,} bytes"})
    for label, table in [("CONTRACT_TO_CURRENT_SHOP", "contract_shop_bridge"), ("LEAD_TO_CURRENT_SHOP", "lead_shop_bridge")]:
        stats = con.execute(f"""
            SELECT count(*) n, count(*) FILTER (WHERE shop_match_state = 'CURRENT_SHOP_MASTER_MATCHED') matched_rows,
                   count(DISTINCT skp_salesroom_id) shops
            FROM {quote_identifier(table)}
        """).fetchone()
        records.append({"coverage_area": "CURRENT_SHOP_MASTER", "population": label, "numerator": int(stats[1]),
                        "denominator": int(stats[0]), "coverage_pct": round(100 * stats[1] / stats[0], 4) if stats[0] else None,
                        "status": "CURRENT_SNAPSHOT_ONLY", "details": f"{stats[2]:,} distinct fact shop IDs; unmatched IDs preserved."})
    product_stats = con.execute("""
        SELECT count(*) n, count(*) FILTER (WHERE mapping_status = 'APPROVED_COMPATIBLE') approved,
               count(*) FILTER (WHERE mapping_status = 'EXACT_CODE_CANDIDATE') exact_candidates
        FROM lead_event_version l
        LEFT JOIN product_crosswalk x ON upper(trim(l.lead_product_code)) = upper(trim(x.lead_product_code))
    """).fetchone()
    records.append({"coverage_area": "PRODUCT_CROSSWALK", "population": "LEAD_EVENT_ROWS", "numerator": int(product_stats[1]),
                    "denominator": int(product_stats[0]), "coverage_pct": round(100 * product_stats[1] / product_stats[0], 4) if product_stats[0] else None,
                    "status": "APPROVAL_REQUIRED" if not C.APPROVED_PRODUCT_CROSSWALK else "CONFIGURED",
                    "details": f"{product_stats[2]:,} event rows have literal candidate mappings; not approved by default."})
    match_counts = con.execute("SELECT match_status, count(*) FROM lead_contract_bridge GROUP BY 1 ORDER BY 1").fetchall()
    total_match = sum(count for _, count in match_counts)
    records.append({"coverage_area": "LEAD_CONTRACT_CANDIDATES", "population": "LEAD_CONTRACT_BRIDGE_ROWS",
                    "numerator": sum(count for status, count in match_counts if status == "MATCHED"),
                    "denominator": total_match,
                    "coverage_pct": round(100 * sum(count for status, count in match_counts if status == "MATCHED") / total_match, 4) if total_match else None,
                    "status": "CONDITIONAL_ON_APPROVED_PRODUCT_CROSSWALK",
                    "details": json.dumps({str(status): int(count) for status, count in match_counts}, ensure_ascii=True)})
    for row in r2_coverage.to_dict("records"):
        records.append({"coverage_area": "ROUND2_LINKAGE", "population": f"{row['population']}:{row['temporal_window']}",
                        "numerator": row.get("customers_with_segment"), "denominator": row.get("distinct_customers"),
                        "coverage_pct": row.get("coverage_pct"), "status": "CUTOFF_PROVENANCE_REVIEW_REQUIRED",
                        "details": row.get("note")})
    weights = con.execute("""
        SELECT count(*) source_rows, sum(sample_weight) sensitivity_sum,
               count(*) FILTER (WHERE sample_weight IS NULL) missing_weight_rows,
               count(*) FILTER (WHERE sample_weight <= 0) nonpositive_rows
        FROM lead_event_version
    """).fetchone()
    records.append({"coverage_area": "LEAD_WEIGHT", "population": "ALL_LEAD_SOURCE_ROWS", "numerator": weights[0],
                    "denominator": weights[0], "coverage_pct": 100.0 if not weights[2] else round(100 * (weights[0]-weights[2]) / weights[0], 4),
                    "status": "UNAPPROVED_QA_ONLY", "details": f"Observed weight sum {weights[1]}; missing {weights[2]:,}; nonpositive {weights[3]:,}. Not a lead count or population estimate."})
    return pd.DataFrame(records)


def build_validation_checks(
    con: duckdb.DuckDBPyConnection, cutoffs: dict[str, Any],
    source_counts: dict[str, int], raw_amount_sum: Any,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any, severity: str, note: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "severity": severity,
                       "observed": json.dumps(observed, ensure_ascii=True, default=str),
                       "expected": json.dumps(expected, ensure_ascii=True, default=str), "note": note})

    def amount_close(left: Any, right: Any) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        left_value, right_value = float(left), float(right)
        return abs(left_value - right_value) <= max(0.01, abs(left_value) * 1e-9)

    raw_contract = int(source_counts["contract"])
    contract_versions = table_count(con, "contract_event_version")
    raw_leads = int(source_counts["leads"])
    lead_versions = table_count(con, "lead_event_version")
    add("all_contract_source_rows_preserved", raw_contract == contract_versions, contract_versions, raw_contract, "FATAL",
        "Every contract source row remains in contract_event_version, including duplicates and conflicting case versions.")
    add("all_lead_source_rows_preserved", raw_leads == lead_versions, lead_versions, raw_leads, "FATAL",
        "Every lead source row remains in lead_event_version; repeated UUIDs are not deduplicated.")
    for name, source_dataset, bridge_table in [
        ("all_product_detail_rows_preserved", "contract_product", "contract_product_bridge"),
        ("all_employee_assignment_rows_preserved", "employee_assignment", "employee_shop_bridge"),
        ("all_lead_reason_rows_preserved", "lead_reason", "lead_reason_dimension"),
    ]:
        observed, expected = table_count(con, bridge_table), int(source_counts[source_dataset])
        add(name, observed == expected, observed, expected, "FATAL", "Source-level detail rows remain in their bridge table.")
    for name, table, key in [
        ("contract_fact_id_unique", "contract_fact", "contract_fact_id"),
        ("lead_row_id_unique", "lead_event_version", "lead_row_id"),
        ("shop_master_record_id_unique", "shop_master", "master_record_id"),
        ("seller_master_record_id_unique", "seller_master", "master_record_id"),
        ("r2_segment_client_key_unique", "r2_customer_segment", "skp_client_id"),
        ("lead_match_summary_one_row_per_lead", "lead_match_summary", "lead_row_id"),
        ("shop_behavior_profile_one_row_per_shop", "shop_behavior_profile", "skp_salesroom_id"),
    ]:
        duplicate_count = int(con.execute(
            f"SELECT count(*) FROM (SELECT {quote_identifier(key)} FROM {quote_identifier(table)} GROUP BY 1 HAVING count(*) > 1)"
        ).fetchone()[0])
        add(name, duplicate_count == 0, duplicate_count, 0, "FATAL", "Canonical bridge key must not fan out downstream joins.")
    for name, table, expected in [
        ("contract_shop_bridge_no_row_inflation", "contract_shop_bridge", table_count(con, "contract_fact")),
        ("lead_shop_bridge_no_row_inflation", "lead_shop_bridge", table_count(con, "lead_event_version")),
        ("contract_segment_bridge_no_row_inflation", "contract_customer_segment_bridge", table_count(con, "contract_fact")),
        ("lead_segment_bridge_no_row_inflation", "lead_customer_segment_bridge", table_count(con, "lead_event_version")),
        ("lead_match_summary_no_row_loss", "lead_match_summary", table_count(con, "lead_event_version")),
    ]:
        observed = table_count(con, table)
        add(name, observed == expected, observed, expected, "FATAL", "One-row-per-source-event bridge must preserve its source grain.")
    summary_duplicate = int(con.execute("SELECT count(*) FROM (SELECT skp_credit_case_id FROM contract_product_summary GROUP BY 1 HAVING count(*) > 1)").fetchone()[0])
    add("contract_product_summary_one_row_per_case", summary_duplicate == 0, summary_duplicate, 0, "FATAL",
        "Product details are aggregated before joining to contract_fact.")
    for table, keys in [
        ("contract_shop_month", "skp_salesroom_id, month_start, business_outcome"),
        ("contract_shop_month_total", "skp_salesroom_id, month_start"),
        ("lead_conversion_shop_month", "lead_origin_shop_id, booking_shop_id, month_start, normalized_product"),
    ]:
        duplicate_groups = int(con.execute(f"SELECT count(*) FROM (SELECT {keys} FROM {table} GROUP BY {keys} HAVING count(*) > 1)").fetchone()[0])
        add(f"{table}_grain_unique", duplicate_groups == 0, duplicate_groups, 0, "FATAL", "Declared aggregate grain is unique.")
    shop_month_duplicates = int(con.execute("""
        SELECT count(*) FROM (
            SELECT coalesce(cast(skp_salesroom_id AS VARCHAR), '<NULL>') shop_key, month_start
            FROM shop_month_foundation GROUP BY 1, 2 HAVING count(*) > 1
        )
    """).fetchone()[0])
    add("shop_month_foundation_grain_unique", shop_month_duplicates == 0, shop_month_duplicates, 0, "FATAL",
        "One row per shop identifier (including unknown) and month.")

    lead_dated_rows = int(con.execute("SELECT count(*) FROM lead_event_version WHERE date_assigned_ts IS NOT NULL").fetchone()[0])
    lead_product_month_rows = int(con.execute("SELECT coalesce(sum(lead_event_rows),0) FROM lead_shop_month_product").fetchone()[0])
    lead_shop_month_rows = int(con.execute("SELECT coalesce(sum(lead_event_rows),0) FROM shop_month_foundation").fetchone()[0])
    add("lead_product_month_event_rows_reconcile", lead_product_month_rows == lead_dated_rows, lead_product_month_rows, lead_dated_rows,
        "FATAL", "Product-month aggregates count raw lead events once; UUID/client counts remain separate." )
    add("lead_shop_month_event_rows_reconcile", lead_shop_month_rows == lead_dated_rows, lead_shop_month_rows, lead_dated_rows,
        "FATAL", "Shop-month lead event totals come directly from lead source events, not sums of product-level distinct counts.")
    dated_contract_rows = int(con.execute("SELECT count(*) FROM contract_fact WHERE date_apply_ts IS NOT NULL").fetchone()[0])
    month_contract_rows = int(con.execute("SELECT coalesce(sum(application_event_rows),0) FROM contract_shop_month_total").fetchone()[0])
    foundation_contract_rows = int(con.execute("SELECT coalesce(sum(contract_application_event_rows),0) FROM shop_month_foundation").fetchone()[0])
    add("contract_month_event_rows_reconcile", month_contract_rows == dated_contract_rows, month_contract_rows, dated_contract_rows,
        "FATAL", "Contract shop-month totals reconcile to date-valid canonical application events.")
    add("contract_foundation_event_rows_reconcile", foundation_contract_rows == dated_contract_rows, foundation_contract_rows, dated_contract_rows,
        "FATAL", "Shop-month foundation totals reconcile without dimension fanout.")

    amount_rows = con.execute("""
        SELECT
            (SELECT sum(credit_amount_raw) FROM contract_event_version),
            (SELECT sum(credit_amount_raw) FROM contract_fact),
            (SELECT sum(credit_amount_raw) FROM contract_shop_bridge),
            (SELECT sum(credit_amount_raw) FROM contract_customer_segment_bridge),
            (SELECT sum(credit_amount_raw) FROM contract_fact WHERE date_apply_ts IS NOT NULL),
            (SELECT sum(credit_amount_raw_sum) FROM contract_shop_month_total)
    """).fetchone()
    version_amount, fact_amount, shop_amount, segment_amount, dated_amount, monthly_amount = amount_rows
    raw_amount = raw_amount_sum
    add("raw_to_event_version_amount_reconcile", amount_close(raw_amount, version_amount), version_amount, raw_amount, "FATAL",
        "Casting to numeric must preserve the sum of parseable source credit_amount values.")
    add("contract_shop_bridge_amount_no_inflation", amount_close(fact_amount, shop_amount), shop_amount, fact_amount, "FATAL",
        "Left-joining current shop attributes must preserve canonical raw amounts.")
    add("contract_segment_bridge_amount_no_inflation", amount_close(fact_amount, segment_amount), segment_amount, fact_amount, "FATAL",
        "Left-joining Round 2 segments must preserve canonical raw amounts.")
    add("dated_contract_month_amount_reconcile", amount_close(dated_amount, monthly_amount), monthly_amount, dated_amount, "FATAL",
        "Raw amount sum in shop-month total must match date-valid canonical events; it is not labeled funded volume.")
    funded_rows = con.execute("""
        SELECT count(*) FILTER (WHERE is_funded), sum(credit_amount_raw) FILTER (WHERE is_funded)
        FROM contract_fact WHERE date_apply_ts IS NOT NULL
    """).fetchone()
    funded_month_rows, funded_month_amount = con.execute("""
        SELECT sum(funded_contract_count), sum(funded_credit_amount_raw_sum) FROM contract_shop_month_total
    """).fetchone()
    funded_foundation_rows, funded_foundation_amount = con.execute("""
        SELECT sum(funded_contract_count), sum(funded_credit_amount_raw_sum) FROM shop_month_foundation
    """).fetchone()
    add("funded_month_counts_reconcile", funded_rows[0] == funded_month_rows, funded_month_rows, funded_rows[0], "FATAL",
        "Selected funded flag counts reconcile over dated application months.")
    add("funded_month_amount_reconcile", amount_close(funded_rows[1], funded_month_amount), funded_month_amount, funded_rows[1], "FATAL",
        "Selected funded credit amount reconciles over dated application months.")
    add("funded_foundation_counts_reconcile", funded_rows[0] == funded_foundation_rows, funded_foundation_rows, funded_rows[0], "FATAL",
        "Foundation selected-funded count reconciles without fanout.")
    add("funded_foundation_amount_reconcile", amount_close(funded_rows[1], funded_foundation_amount), funded_foundation_amount, funded_rows[1], "FATAL",
        "Foundation selected-funded amount reconciles without fanout.")
    primary_table_count = int(con.execute("SELECT coalesce(sum(primary_matched_contracts),0) FROM lead_conversion_shop_month").fetchone()[0])
    primary_bridge_count = int(con.execute("SELECT count(*) FROM lead_contract_bridge WHERE is_primary_match").fetchone()[0])
    add("conversion_month_primary_matches_reconcile", primary_table_count == primary_bridge_count,
        primary_table_count, primary_bridge_count, "FATAL", "Shop-month conversion table accounts for each primary confirmed match once.")

    weight_types = {row[0]: row[1] for row in con.execute("DESCRIBE SELECT * FROM lead_event_version").fetchall()}
    weight_columns = [name for name in weight_types if name == "sample_weight"]
    weight_type_ok = len(weight_columns) == 1 and weight_types.get("sample_weight") in ("DOUBLE", "FLOAT") and weight_types.get("sample_weight_raw") == "VARCHAR"
    add("sample_weight_raw_and_typed_columns_are_distinct", weight_type_ok,
        {"sample_weight": weight_types.get("sample_weight"), "sample_weight_raw": weight_types.get("sample_weight_raw")},
        {"sample_weight": "DOUBLE", "sample_weight_raw": "VARCHAR"}, "FATAL",
        "Raw source representation and parsed QA-only sensitivity value must not collide or be mistaken for each other.")

    cutoff_ok = bool(cutoffs.get("fhs") and cutoffs.get("ces") and cutoffs.get("common_cutoff"))
    add("round2_production_score_cutoffs_read_from_source_config", cutoff_ok, cutoffs.get("common_cutoff"), "FHS and CES SNAPSHOT_DATE",
        "CONDITIONAL", "Production score snapshots are read from Round 2 config; feature-level timestamp lineage still requires review.")
    add("round2_feature_timestamp_lineage_audited", False, "REVIEW_REQUIRED", "Every score feature timestamp verified",
        "BUSINESS_GATE", "Code snapshot dates are known, but this pipeline does not certify every feature's point-in-time lineage.")
    product_approved = bool(C.APPROVED_PRODUCT_CROSSWALK)
    add("lead_product_crosswalk_approved", product_approved, len(C.APPROVED_PRODUCT_CROSSWALK), ">=1 configured team-assumption mappings",
        "BUSINESS_GATE", "Configured equality mappings are competition assumptions, not owner approvals.")
    outcome_approved = bool(C.APPROVED_CONTRACT_OUTCOME_MAP)
    add("contract_status_outcome_semantics_approved", outcome_approved, len(C.APPROVED_CONTRACT_OUTCOME_MAP), ">=1 explicit status mappings",
        "BUSINESS_GATE", "Current/final statuses are retained raw; funded outcome remains undefined unless approved.")
    add("lead_sample_weight_semantics_approved", False, "UNAPPROVED_QA_ONLY", "source-owner scope and estimator approval",
        "BUSINESS_GATE", "Weights are preserved and summarized for QA only; no weighted population claim is emitted.")
    employee_approved = bool(C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES)
    add("employee_active_status_codes_approved", employee_approved, len(C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES), ">=1 approved active status",
        "BUSINESS_GATE", "Raw assignment intervals remain available; active headcount proxy is null by default.")
    fatal_failures = [row["check"] for row in checks if row["severity"] == "FATAL" and row["status"] != "PASS"]
    business_gates_pending = [row["check"] for row in checks if row["severity"] in ("BUSINESS_GATE", "CONDITIONAL") and row["status"] != "PASS"]
    return pd.DataFrame(checks), {
        "execution_status": "SUCCESS" if not fatal_failures else "FAILED",
        "foundation_quality_gate": "PASS" if not business_gates_pending and not fatal_failures else "CONDITIONAL",
        "fatal_failures": fatal_failures,
        "business_gates_pending": business_gates_pending,
    }

# %% [markdown]
# ## Month-level, cutoff-aware analytical foundation
#
# Contract application counts are kept distinct from booking/signing/funding
# claims; lead counts are raw event rows with distinct UUID/client columns; the
# mechanical weight sum is an appendix/QA diagnostic only. Shop-month rows with
# no observed fact events are explicitly labeled as coverage gaps, not zero sales.

# %%
def create_date_exceptions(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TEMP TABLE contract_date_exceptions AS
        SELECT contract_row_id AS source_row_id, skp_credit_case_id, skp_client_id,
               date_apply_raw AS source_date_raw, date_apply_state AS date_state, 'CONTRACT_DATE_APPLY' AS field_name
        FROM contract_event_version WHERE date_apply_state <> 'PARSED'
        UNION ALL
        SELECT contract_row_id, skp_credit_case_id, skp_client_id, date_sign_raw, date_sign_state, 'CONTRACT_DATE_SIGN'
        FROM contract_event_version WHERE date_sign_state <> 'PARSED'
    """)
    con.execute("""
        CREATE TEMP TABLE lead_date_exceptions AS
        SELECT lead_row_id AS source_row_id, lead_uuid, skp_client_id,
               date_assigned_raw AS source_date_raw, date_assigned_state AS date_state, 'LEAD_DATE_ASSIGNED' AS field_name
        FROM lead_event_version WHERE date_assigned_state <> 'PARSED'
        UNION ALL
        SELECT lead_row_id, lead_uuid, skp_client_id, dtime_created_raw, dtime_created_state, 'LEAD_DTIME_CREATED'
        FROM lead_event_version WHERE dtime_created_state <> 'PARSED'
    """)


def create_r2_coverage_table(con: duckdb.DuckDBPyConnection, cutoff: str | None) -> None:
    coverage = build_r2_coverage(con, cutoff)
    con.register("_r2_coverage_df", coverage)
    con.execute("CREATE TEMP TABLE r2_link_coverage AS SELECT * FROM _r2_coverage_df")
    con.unregister("_r2_coverage_df")




def create_output_tables(con: duckdb.DuckDBPyConnection, cutoff: str | None, inventory_rows: list[dict[str, Any]]) -> None:
    # Add one-to-one shop and R2 bridges before building month and segment rollups.
    create_fact_bridges(con)
    create_lead_contract_bridge(con)
    con.execute("""
        CREATE TEMP VIEW leads_clean AS
        SELECT l.*, m.candidate_contract_count, m.direct_case_candidate_count,
               m.same_client_product_candidate_count, m.confirmed_match_count,
               m.unapproved_product_candidate_count, m.temporal_fail_candidate_count,
               m.temporal_unknown_candidate_count, m.is_ambiguous, m.lead_match_state
        FROM lead_event_version l
        LEFT JOIN lead_match_summary m USING (lead_row_id)
    """)
    con.execute("""
        CREATE TEMP VIEW lead_contract_candidates AS
        SELECT * FROM lead_contract_bridge WHERE contract_fact_id IS NOT NULL
    """)
    create_monthly_tables(con, cutoff)
    create_date_exceptions(con)
    create_r2_coverage_table(con, cutoff)
    build_weight_audit(con)
    coverage = build_coverage_summary(con, inventory_rows, con.execute("SELECT * FROM r2_link_coverage").df())
    con.register("_coverage_df", coverage)
    con.execute("CREATE TEMP TABLE coverage_summary AS SELECT * FROM _coverage_df")
    con.unregister("_coverage_df")


def build_data_dictionary(con: duckdb.DuckDBPyConnection, output_tables: list[str], schema_descriptions: dict[tuple[str, str], str]) -> pd.DataFrame:
    rows = []
    for table in output_tables:
        if not table_exists(con, table):
            continue
        desc = con.execute(f"DESCRIBE SELECT * FROM {quote_identifier(table)}").fetchall()
        grain = TABLE_GRAINS.get(table, "See table name and field definitions.")
        table_description = TABLE_DESCRIPTIONS.get(table, "")
        source_dataset = TABLE_SOURCE_DATASET.get(table)
        for field, data_type, *_ in desc:
            field_key = str(field).casefold()
            source_field = SOURCE_FIELD_ALIASES.get(table, {}).get(field_key, field_key)
            source_description = schema_descriptions.get((source_dataset, str(source_field).casefold()), "") if source_dataset else ""
            definition = COLUMN_DESCRIPTIONS.get(str(field), source_description or f"Derived field; see transformation and validation notes for `{table}`.")
            rows.append({"table_name": table, "parquet_file": PUBLISHED_PARQUET_PATHS.get(table, f"{table}.parquet"), "table_description": table_description,
                         "grain": grain, "column_name": field, "data_type": data_type, "definition": definition})
    return pd.DataFrame(rows)


def table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]).fetchone()[0])


def output_table_names() -> list[str]:
    """Only canonical cleaned entities and required downstream foundation tables are published as Parquet."""
    return list(PUBLISHED_PARQUET_PATHS)


def write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_input_path(path: Path) -> str:
    resolved = Path(path).resolve()
    for root, label in ((C.PROJECT_ROOT, C.PROJECT_ROOT.name), (C.ROUND2_DIR, C.ROUND2_DIR.name)):
        try:
            return f"{label}/{resolved.relative_to(root.resolve()).as_posix()}"
        except ValueError:
            continue
    return resolved.name


def fingerprint_inputs(files: dict[str, Path], additional_files: dict[str, Path] | None = None) -> dict[str, dict[str, Any]]:
    all_files = {**files, **(additional_files or {})}
    return {
        name: {
            "relative_path": display_input_path(path),
            "source_bytes": Path(path).stat().st_size,
            "mtime_ns": Path(path).stat().st_mtime_ns,
            "sha256": sha256_file(Path(path)),
        }
        for name, path in sorted(all_files.items())
    }


def build_r2_source_manifest(
    files: dict[str, Path], cutoffs: dict[str, Any], fingerprints: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    sources = {}
    for kind in ("fhs", "ces"):
        path = files[f"r2_{kind}"]
        metadata = pq.ParquetFile(path)
        sources[kind] = {
            **fingerprints[f"r2_{kind}"],
            "copied_into_round3": False,
            "rows": metadata.metadata.num_rows,
            "columns": metadata.schema_arrow.names,
            "production_score_snapshot": cutoffs.get(kind),
            "validation_asof_not_used_as_export_cutoff": cutoffs.get(f"{kind}_validation_asof"),
        }
    return {
        "description": "Original R2 scores remain read-only inputs and are not copied under Round 3.",
        "join_key": "SKP_CLIENT -> skp_client_id",
        "common_post_score_cutoff": cutoffs.get("common_cutoff"),
        "sources": sources,
    }


def previous_38_run_comparison(current_counts: dict[str, int], reconciliation: dict[str, Any]) -> dict[str, Any]:
    # Retained from verified run 20261021T120850Z; its generated output folder was replaced.
    baseline = {
        "contract_event_version": 3_775_371, "contract_fact": 3_775_371,
        "leads": 6_130_637, "contract_product_detail": 784_902,
        "employee_assignments": 275_856, "shop_master": 14_231,
        "seller_master": 11_639, "r2_customer_segment": 1_000_528,
        "lead_match_summary": 6_130_637, "lead_contract_bridge_with_unmatched_placeholders": 6_597_227,
        "shop_month_foundation": 715_528,
    }
    mapping = {
        "contract_fact": "contract_fact", "leads_clean": "leads",
        "contract_product_bridge": "contract_product_detail", "employee_shop_bridge": "employee_assignments",
        "seller_master": "seller_master", "shop_month_foundation": "shop_month_foundation",
        "r2_customer_segment": "r2_customer_segment",
    }
    comparisons = {}
    differences = {}
    for current_key, baseline_key in mapping.items():
        previous, current = baseline[baseline_key], current_counts[current_key]
        comparisons[current_key] = {"previous_rows": previous, "current_rows": current, "delta": current - previous}
        if current != previous:
            differences[current_key] = comparisons[current_key]
    baseline_amount = 70_604_962_581_146.0
    current_amount = reconciliation.get("contract_raw_amount_sum")
    amount_delta = None if current_amount is None else float(current_amount) - baseline_amount
    amount_checks = {key: reconciliation.get(key) for key in (
        "raw_to_event_version_amount_delta", "shop_bridge_amount_delta",
        "segment_bridge_amount_delta", "dated_month_amount_delta")}
    return {
        "baseline_run_id": "20261021T120850Z", "baseline_parquet_count": 38,
        "baseline_counts": baseline, "matched_grain_comparisons": comparisons,
        "row_count_differences": differences,
        "candidate_bridge_note": "Legacy count includes unmatched placeholder rows; current candidate Parquet excludes them by design.",
        "previous_38_run_contract_amount_sum": baseline_amount,
        "current_contract_amount_sum": current_amount,
        "contract_amount_sum_delta_vs_legacy": amount_delta,
        "amount_reconciliation_deltas_current": amount_checks,
        "amount_reconciliation_pass": amount_delta == 0 and all(value == 0 for value in amount_checks.values()),
        "comparison_state": "COMPARED; candidate bridge grain differs by design",
    }


def input_fingerprints_match(
    previous_metrics: dict[str, Any], input_fingerprints: dict[str, dict[str, Any]], pipeline_fingerprint: str
) -> bool:
    return (
        previous_metrics.get("pipeline_fingerprint") == pipeline_fingerprint
        and previous_metrics.get("input_fingerprints") == input_fingerprints
    )


def reusable_source_audit_datasets(
    previous_metrics: dict[str, Any], input_fingerprints: dict[str, dict[str, Any]],
    pipeline_fingerprint: str, datasets: set[str]
) -> set[str]:
    if previous_metrics.get("pipeline_fingerprint") != pipeline_fingerprint:
        return set()
    old_inputs = previous_metrics.get("input_fingerprints", {})
    profiled = {str(row.get("dataset")) for row in previous_metrics.get("missingness", [])}
    audited = {str(row.get("dataset")) for row in previous_metrics.get("key_integrity", [])}
    return {
        dataset for dataset in datasets
        if old_inputs.get(dataset) == input_fingerprints.get(dataset)
        and dataset in profiled and dataset in audited
    }


def write_markdown_table(frame: pd.DataFrame, limit: int | None = None) -> str:
    data = frame.head(limit) if limit else frame
    if data.empty:
        return "_No rows._"
    columns = [str(column) for column in data.columns]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in data.iterrows():
        values = []
        for value in row.tolist():
            if pd.isna(value):
                text = ""
            else:
                text = str(value).replace("|", "\\|").replace("\n", " ")
            values.append(text)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_quality_report(
    path: Path,
    inventory: pd.DataFrame,
    schema: pd.DataFrame,
    keys: pd.DataFrame,
    profiles: pd.DataFrame,
    coverage: pd.DataFrame,
    validations: pd.DataFrame,
    gate: dict[str, Any],
    cutoffs: dict[str, Any],
    counts: dict[str, int],
) -> None:
    schema_issues = schema[schema.schema_status.isin(["MISSING_FROM_SOURCE", "NOT_IN_SCHEMA", "SOURCE_TABLE_NOT_DOCUMENTED"])]
    missing_summary = profiles.sort_values(["null_or_blank_pct", "null_or_blank_count"], ascending=False).head(20)
    candidate_summary = coverage[coverage.coverage_area.isin(["CURRENT_SHOP_MASTER", "PRODUCT_CROSSWALK", "LEAD_CONTRACT_CANDIDATES", "ROUND2_LINKAGE", "LEAD_WEIGHT"])]
    lines = [
        "# BI10 Round 3 — Phase 1 Foundation Data Quality Report", "",
        f"- Run UTC: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Execution status: **{gate['execution_status']}**",
        f"- Foundation quality gate: **{gate['foundation_quality_gate']}**",
        "- Scope: source inventory, cleaning/version handling, bridges, cutoff-aware linkage, raw shop-month foundation, validation only.",
        "- No Phase 2 EDA, forecasting, growth potential, ranking, recommendations, or figures were produced.", "",
        "## Input inventory", "", write_markdown_table(inventory), "",
        "## Schema-to-source exceptions", "",
        "The source CSVs were staged as VARCHAR to preserve IDs/codes; this is not a claim that their business types are strings.",
        "`StructureTable.xlsx` now documents Contract Product fields. `skp_credit_case` is a case grouping key rather than a row-level unique key because cases may have multiple detail rows. Remaining schema differences are the district spelling mismatch, the undocumented lead weight/original-product fields, and the extra `SKP_EMP_MANAGE` source field.",
        "", write_markdown_table(schema_issues, 40), "",
        "## Key and duplicate audits", "", write_markdown_table(keys), "",
        "## Highest missing/blank rates", "", write_markdown_table(missing_summary), "",
        "## Coverage", "", write_markdown_table(candidate_summary), "",
        "## Core row counts", "", write_markdown_table(pd.DataFrame([{"table": key, "rows": value} for key, value in counts.items()])), "",
        "## Automated validations", "", write_markdown_table(validations), "",
        "## Cutoff and unresolved business definitions", "",
        f"- Round 2 production score snapshot: FHS `{cutoffs.get('fhs')}`; CES `{cutoffs.get('ces')}`; combined segment outcome cutoff `{cutoffs.get('common_cutoff')}`.",
        f"- Round 2 validation freezes (not used as export cutoffs): FH_ASOF `{cutoffs.get('fhs_validation_asof')}`; ENG_ASOF `{cutoffs.get('ces_validation_asof')}`.",
        "- The Round 2 production score-generation code uses SNAPSHOT_DATE for both exported populations; feature-level timestamp lineage remains a review gate.",
        f"- Cutoff status: {cutoffs.get('cutoff_provenance_state')}",
        "- Product compatibility uses a competition-run exact-code assumption for TW/CL/CC/CD only; REL remains unmapped and the assumption is not owner approval.",
        f"- `is_funded` uses `{C.FUNDED_DEFINITION}`; provisional status categories include FUNDED, PAID_OFF and WRITTEN_OFF.",
        "- `sample_weight` remains QA-only; it is not used as an estimator or applied to counts, conversions, customers, or amounts.",
        "- Employee active proxy uses configured provisional code A based on the status profile; confirm operational meaning before treating as headcount.",
        "- Shop/seller fields describe current master snapshots only; historical validity is not claimed.",
        "- Sentinel years 2999/3000 are converted to NULL in canonical timestamps and retained as source raw values plus explicit flags.",
        "- Contract/lead rows with missing or invalid event dates remain flagged in `contract_clean.parquet` / `leads_clean.parquet`; exception-row counts are recorded in `metrics_phase1.json` and such rows are excluded only from dated monthly aggregates.",
        "", "## Phase boundary", "",
        "This report and its Parquet outputs constitute Phase 1 only. Continue only after explicit approval and resolution of the relevant Foundation gates.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_validation_payload(
    gate: dict[str, Any], checks: pd.DataFrame, cutoffs: dict[str, Any], counts: dict[str, int],
    inventory: pd.DataFrame, coverage: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "phase": "Phase 1 — Data Processing / Foundation only",
        "execution_status": gate["execution_status"],
        "foundation_quality_gate": gate["foundation_quality_gate"],
        "fatal_failures": gate["fatal_failures"],
        "business_gates_pending": gate["business_gates_pending"],
        "round2_cutoffs": cutoffs,
        "table_row_counts": counts,
        "raw_inventory": inventory.to_dict("records"),
        "coverage_summary": coverage.to_dict("records"),
        "checks": checks.to_dict("records"),
        "unresolved_business_definitions": [
            "Contract status-to-outcome and funded amount definition",
            "Lead-to-contract product crosswalk approval",
            "Lead sample_weight scope, target population, estimator and normalization",
            "Employee active-status code semantics and headcount proxy",
            "Round 2 score feature-level cutoff provenance",
            "Historical validity of current shop/seller attributes",
        ],
    }


def export_parquet_tables(con: duckdb.DuckDBPyConnection, output_dir: Path, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        if not table_exists(con, table):
            continue
        relative_path = Path(PUBLISHED_PARQUET_PATHS[table])
        destination = output_dir / relative_path
        ensure_dirs(destination.parent)
        con.execute(
            f"COPY (SELECT * FROM {quote_identifier(table)}) TO {sql_literal(destination.as_posix())} "
            f"(FORMAT PARQUET, COMPRESSION {C.PARQUET_COMPRESSION}, ROW_GROUP_SIZE {int(C.PARQUET_ROW_GROUP_SIZE)})"
        )
        counts[table] = pq.ParquetFile(destination).metadata.num_rows
    return counts


def publish_phase1_report(source_path: Path, report_dir: Path) -> Path:
    """Atomically copy one Phase 1 report artifact to its delivery folder."""
    source_path = Path(source_path)
    report_dir = Path(report_dir)
    if not source_path.is_file():
        raise FileNotFoundError(f"Phase 1 report artifact was not generated: {source_path}")
    ensure_dirs(report_dir)
    destination = report_dir / source_path.name
    temporary = report_dir / f".{source_path.name}.{os.getpid()}.tmp"
    try:
        shutil.copy2(source_path, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def prune_redundant_report_artifacts(report_dir: Path) -> list[str]:
    """Remove only known generated sidecars duplicated in metrics/validation outputs."""
    redundant_names = (
        "README.md", "coverage_summary.csv", "data_dictionary.md", "join_reconciliation.json",
        "parquet_readability.json", "product_crosswalk.csv",
    )
    removed = []
    for name in redundant_names:
        path = Path(report_dir) / name
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


def organize_phase1_reports(data_dir: Path, report_dir: Path) -> list[Path]:
    """Move generated audit/report sidecars out of Data_clean into the report bundle."""
    names = (
        "data_dictionary.csv", "data_quality_report.md", "validation_report.json",
        "status_profile.csv", "employee_status_profile.csv", "assumptions.json",
    )
    moved = []
    for name in names:
        source = Path(data_dir) / name
        if source.is_file():
            destination = publish_phase1_report(source, report_dir)
            source.unlink()
            moved.append(destination)
    prune_redundant_report_artifacts(data_dir)
    prune_redundant_report_artifacts(report_dir)
    return moved


def verify_parquet_files(output_dir: Path, tables: list[str], expected_counts: dict[str, int]) -> list[dict[str, Any]]:
    checks = []
    for table in tables:
        relative_path = Path(PUBLISHED_PARQUET_PATHS[table])
        path = output_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Expected published Parquet is missing: {relative_path.as_posix()}")
        parquet_file = pq.ParquetFile(path)
        rows = parquet_file.metadata.num_rows
        schema_fields = len(parquet_file.schema_arrow)
        checks.append({"file": relative_path.as_posix(), "rows": rows, "columns": schema_fields,
                       "file_bytes": path.stat().st_size, "readable_by_pyarrow": True,
                       "expected_rows": expected_counts.get(table), "row_count_match": rows == expected_counts.get(table)})
        if rows != expected_counts.get(table):
            raise AssertionError(f"Parquet row-count mismatch: {relative_path.as_posix()}: {rows} != {expected_counts.get(table)}")
    return checks


def publish_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    ensure_dirs(output_dir)
    backup_dir = output_dir.parent / (
        f".{output_dir.name}_publish_backup_{os.getpid()}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    backed_up: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for staged_path in sorted(staging_dir.iterdir()):
            destination = output_dir / staged_path.name
            if destination.exists():
                backup_path = backup_dir / staged_path.name
                os.replace(destination, backup_path)
                backed_up.append((backup_path, destination))
            os.replace(staged_path, destination)
            installed.append(destination)
        staging_dir.rmdir()
    except BaseException as publish_error:
        try:
            for destination in reversed(installed):
                if destination.is_dir():
                    shutil.rmtree(destination)
                elif destination.exists():
                    destination.unlink()
            for backup_path, destination in reversed(backed_up):
                if destination.is_dir():
                    shutil.rmtree(destination)
                elif destination.exists():
                    destination.unlink()
                if backup_path.exists():
                    os.replace(backup_path, destination)
        except BaseException as rollback_error:
            raise RuntimeError(f"Publication failed ({publish_error!r}) and rollback was incomplete; preserve {backup_dir}") from rollback_error
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    try:
        shutil.rmtree(backup_dir)
    except OSError:
        pass

    # Remove only known outputs emitted by the prior compact generator version.
    readme = output_dir / "README.md"
    if readme.is_file() and "Generated by `Code/1. Data processing.py`" in readme.read_text(encoding="utf-8"):
        for relative in (
            "lead_reason_clean.parquet", "customer_segment_shop_product_month.parquet",
            "R2/r2_link_coverage.parquet", "R2/r2_source_manifest.json",
        ):
            stale = output_dir / relative
            if stale.is_file() and not stale.is_symlink():
                stale.unlink()
    legacy = output_dir / "foundation"
    marker = legacy / "README.md"
    known_old_outputs = {f"{table}.parquet" for table in TABLE_GRAINS} | {
        "contract_date_exceptions.parquet", "lead_date_exceptions.parquet", "lead_reason_lookup.parquet",
        "join_reconciliation.parquet", "README.md", "data_dictionary.csv", "data_dictionary.md",
        "data_quality_report.md", "coverage_summary.csv", "join_reconciliation.json",
        "parquet_readability.json", "validation_report.json",
    }
    if legacy.is_dir() and marker.is_file():
        try:
            marker_text = marker.read_text(encoding="utf-8")
            children = list(legacy.iterdir())
            if "Generated by `Code/1. Data processing.py`" in marker_text and all(
                child.is_file() and child.name in known_old_outputs for child in children
            ):
                shutil.rmtree(legacy)
        except OSError:
            pass

# %% [markdown]
# ## Run Phase 1 and publish atomically after validation
#
# A failed fatal invariant leaves the existing published folder untouched.
# DuckDB spill files and run staging are separate from published Parquet data.

# %%
def build_source_status_profiles(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read-only source distributions; no status meanings are inferred."""
    contract = con.execute("""
        SELECT name_status, count(*) AS row_count,
               avg(CASE WHEN try_cast(date_sign AS TIMESTAMP) IS NOT NULL
                              AND year(try_cast(date_sign AS TIMESTAMP)) NOT IN (2999, 3000)
                        THEN 1.0 ELSE 0.0 END) AS share_real_date_sign,
               avg(CASE WHEN try_cast(amt_billing_1st AS DOUBLE) IS NOT NULL
                        THEN 1.0 ELSE 0.0 END) AS share_nonnull_billing_1st
        FROM raw_contract GROUP BY name_status ORDER BY row_count DESC
    """).df()
    employee = con.execute("""
        SELECT code_status, count(*) AS row_count,
               avg(CASE WHEN try_cast(dtime_valid_to AS TIMESTAMP) IS NULL
                              OR year(try_cast(dtime_valid_to AS TIMESTAMP)) IN (2999, 3000)
                        THEN 1.0 ELSE 0.0 END) AS share_open_ended_valid_to
        FROM raw_employee_assignment GROUP BY code_status ORDER BY row_count DESC
    """).df()
    return contract, employee


def run() -> dict[str, Any]:
    overall_started = time.perf_counter()
    profiler = StageProfiler()
    files = discover_inputs()
    ensure_dirs(C.OUTPUT_DIR)
    previous_metrics_path = C.OUTPUT_DIR / "metrics_phase1.json"
    try:
        previous_metrics = json.loads(previous_metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous_metrics = {}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging_dir = C.OUTPUT_DIR / f"_staging_{run_id}"
    temp_dir = C.OUTPUT_DIR / f"_duckdb_tmp_{run_id}"
    ensure_dirs(staging_dir, temp_dir)
    con = get_con(temp_dir)
    succeeded = False
    try:
        fingerprint_files = {**files, "round2_config": C.ROUND2_CONFIG}
        fingerprint_files.update({
            "phase1_script": Path(__file__),
            "phase1_utils": PROJECT_ROOT / "Code" / "config" / "utils.py",
            "phase1_config": PROJECT_ROOT / "Code" / "config" / "config.py",
        })
        input_fingerprints = measure_call(profiler, "input_fingerprints_sha256", fingerprint_inputs, fingerprint_files)
        code_fingerprint = hashlib.sha256("".join(input_fingerprints[name]["sha256"] for name in (
            "phase1_script", "phase1_utils", "phase1_config", "round2_config"
        )).encode("ascii")).hexdigest()
        reuse_audits = reusable_source_audit_datasets(
            previous_metrics, input_fingerprints, code_fingerprint, set(RAW_TABLE_BY_DATASET)
        )
        cache_audit = len(reuse_audits) == len(RAW_TABLE_BY_DATASET)

        aliases, inventory_rows = measure_call(profiler, "source_view_and_dimension_ingestion", load_raw_sources, con, files)
        contract_status_profile, employee_status_profile = measure_call(
            profiler, "read_only_status_profile", build_source_status_profiles, con
        )
        schema_rows, schema_descriptions = read_schema_documentation(files["schema_workbook"])
        schema_df = build_schema_validation(con, schema_rows, aliases)
        con.register("_schema_df", schema_df)
        con.execute("CREATE TEMP TABLE schema_validation AS SELECT * FROM _schema_df")
        con.unregister("_schema_df")
        if cache_audit:
            profile_df = pd.DataFrame(previous_metrics["missingness"])
            key_df = pd.DataFrame(previous_metrics["key_integrity"])
        else:
            profile_df = measure_call(profiler, "source_profile_scan", profile_source_columns, con, aliases)
            key_df = measure_call(profiler, "primary_key_group_audits", build_key_integrity, con, aliases, profile_df)
        profile_counts = profile_df.groupby("dataset")["source_rows"].first().to_dict()
        for item in inventory_rows:
            if item["dataset"] in profile_counts:
                item["source_rows"] = int(profile_counts[item["dataset"]])
        inventory_df = pd.DataFrame(inventory_rows)
        source_counts = {item["dataset"]: int(item["source_rows"])
                         for item in inventory_rows if item.get("source_rows") is not None}
        amount_profile = profile_df[(profile_df.dataset == "contract") & (profile_df.column == "credit_amount")]
        raw_contract_amount_sum = amount_profile.iloc[0]["numeric_sum_if_numeric"] if not amount_profile.empty else None
        con.register("_inventory_df", inventory_df)
        con.execute("CREATE TEMP TABLE raw_inventory AS SELECT * FROM _inventory_df")
        con.unregister("_inventory_df")
        con.register("_profile_df", profile_df)
        con.execute("CREATE TEMP TABLE column_profile AS SELECT * FROM _profile_df")
        con.unregister("_profile_df")
        con.register("_key_df", key_df)
        con.execute("CREATE TEMP TABLE key_integrity AS SELECT * FROM _key_df")
        con.unregister("_key_df")

        cutoffs = read_round2_cutoffs(C.ROUND2_CONFIG)
        measure_call(profiler, "contract_versions_and_canonical_fact", create_contract_event_versions, con, aliases, cutoffs.get("common_cutoff"))
        measure_call(profiler, "contract_status_mapping", create_status_dimensions, con)
        measure_call(profiler, "contract_product_detail_and_case_summary", create_contract_product_tables, con, aliases)
        measure_call(profiler, "contract_fact", create_contract_fact, con, cutoffs.get("common_cutoff"))
        measure_call(profiler, "shop_seller_employee_dimensions", create_dimension_tables, con, aliases)
        measure_call(profiler, "lead_event_versions", create_lead_events, con, aliases, cutoffs.get("common_cutoff"))
        measure_call(profiler, "exact_duplicate_fingerprint_audits", update_exact_duplicate_audits, con)
        con.execute("UPDATE key_integrity SET audit_state = 'UUID_REPEAT_AUDITED; SOURCE_ROWS_PRESERVED; EXACT_ROW_FINGERPRINT_SKIPPED_PERFORMANCE' WHERE dataset = 'leads'")
        key_df = con.execute("SELECT * FROM key_integrity").df()
        measure_call(profiler, "r2_segment_join", create_r2_customer_segment, con, files, cutoffs)
        measure_call(profiler, "lead_product_crosswalk", create_product_crosswalk, con, aliases)
        measure_call(profiler, "matching_monthly_coverage_aggregates", create_output_tables, con, cutoffs.get("common_cutoff"), inventory_rows)
        nonprimary_attribution = con.execute("""
            WITH confirmed AS (
                SELECT contract_fact_id, lead_row_id, lead_uuid, is_primary_match
                FROM lead_contract_bridge WHERE is_confirmed_match
            ), chosen AS (
                SELECT contract_fact_id, lead_uuid AS primary_uuid
                FROM confirmed WHERE is_primary_match
            ), nonprimary AS (
                SELECT c.contract_fact_id, c.lead_uuid, p.primary_uuid,
                       CASE WHEN c.lead_uuid IS NULL OR p.primary_uuid IS NULL THEN 'UUID_UNKNOWN'
                            WHEN c.lead_uuid = p.primary_uuid THEN 'SAME_UUID_REPEAT'
                            ELSE 'DIFFERENT_LEAD_UUID' END AS attribution
                FROM confirmed c JOIN chosen p USING (contract_fact_id)
                WHERE NOT c.is_primary_match
            )
            SELECT attribution, count(*) AS nonprimary_pairs,
                   count(DISTINCT contract_fact_id) AS affected_contracts
            FROM nonprimary GROUP BY attribution ORDER BY attribution
        """).df().to_dict("records")
        write_csv(staging_dir / "status_profile.csv", contract_status_profile)
        write_csv(staging_dir / "employee_status_profile.csv", employee_status_profile)
        assumptions = {
            "product_mapping": {f"{lead}->{contract}": value for (lead, contract), value in C.APPROVED_PRODUCT_CROSSWALK.items()},
            "product_mapping_basis": "Team assumption of exact code equality; not owner approval. REL remains unmapped.",
            "funded_definition_chosen": C.FUNDED_DEFINITION,
            "funded_status_mapping": C.APPROVED_CONTRACT_OUTCOME_MAP,
            "funded_status_outcomes": sorted(C.FUNDED_STATUS_OUTCOMES),
            "funded_definition_options": {
                "SIGN_DATE": "valid parsed date_sign; sentinels are excluded",
                "STATUS_MAP": "business_outcome in configured FUNDED_STATUS_OUTCOMES; status map is a competition assumption",
                "BILLING": "amt_billing_1st is non-null",
            },
            "employee_active_status_codes": sorted(C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES),
            "employee_active_status_basis": "Status profile: a has 100% open-ended valid_to; n has 0%. A is provisionally treated as active per requested assumption.",
            "lead_primary_match_tie_break": "Latest date_assigned_ts <= date_apply_ts; tie-break lead_row_id ascending.",
            "direct_case_key": "Validation signal only; does not bypass client, product, or time criteria.",
            "nonprimary_pair_uuid_attribution": nonprimary_attribution,
            "round2_common_cutoff": cutoffs.get("common_cutoff"),
            "round2_cutoff_expected": "2025-06-05",
            "sample_weight": "QA-only, not used as an estimator or applied to counts/conversions/amounts.",
        }
        save_json(assumptions, staging_dir / "assumptions.json")

        # Reconciliation evidence: raw rows and amounts versus canonical facts and shop-month totals.
        reconciliation = con.execute("""
            SELECT
                (SELECT count(*) FROM contract_event_version) AS contract_version_rows,
                (SELECT count(*) FROM contract_fact) AS contract_fact_rows,
                (SELECT sum(credit_amount_raw) FROM contract_event_version) AS contract_version_amount_sum,
                (SELECT sum(credit_amount_raw) FROM contract_fact) AS contract_fact_amount_sum,
                (SELECT sum(credit_amount_raw) FROM contract_shop_bridge) AS contract_shop_bridge_amount_sum,
                (SELECT sum(credit_amount_raw) FROM contract_customer_segment_bridge) AS contract_segment_bridge_amount_sum,
                (SELECT count(*) FROM contract_fact WHERE date_apply_ts IS NOT NULL) AS dated_contract_fact_rows,
                (SELECT sum(credit_amount_raw) FROM contract_fact WHERE date_apply_ts IS NOT NULL) AS dated_contract_fact_amount_sum,
                (SELECT coalesce(sum(application_event_rows),0) FROM contract_shop_month_total) AS contract_month_event_rows,
                (SELECT sum(credit_amount_raw_sum) FROM contract_shop_month_total) AS contract_month_amount_sum,
                (SELECT count(*) FROM lead_event_version) AS lead_version_rows,
                (SELECT count(*) FROM lead_shop_bridge) AS lead_shop_bridge_rows,
                (SELECT count(*) FROM contract_shop_bridge) AS contract_shop_bridge_rows,
                (SELECT count(*) FROM contract_product_bridge) AS contract_product_detail_rows,
                (SELECT count(*) FROM contract_product_summary) AS contract_product_case_rows,
                (SELECT count(*) FROM lead_event_version WHERE date_assigned_ts IS NOT NULL) AS dated_lead_event_rows,
                (SELECT coalesce(sum(lead_event_rows),0) FROM lead_shop_month_product) AS lead_month_event_rows,
                (SELECT coalesce(sum(contract_application_event_rows),0) FROM shop_month_foundation) AS foundation_contract_event_rows,
                (SELECT coalesce(sum(lead_event_rows),0) FROM shop_month_foundation) AS foundation_lead_event_rows
        """).fetchone()
        reconciliation_columns = [
            "contract_version_rows", "contract_fact_rows", "contract_version_amount_sum", "contract_fact_amount_sum",
            "contract_shop_bridge_amount_sum", "contract_segment_bridge_amount_sum", "dated_contract_fact_rows",
            "dated_contract_fact_amount_sum", "contract_month_event_rows", "contract_month_amount_sum",
            "lead_version_rows", "lead_shop_bridge_rows", "contract_shop_bridge_rows", "contract_product_detail_rows",
            "contract_product_case_rows", "dated_lead_event_rows", "lead_month_event_rows",
            "foundation_contract_event_rows", "foundation_lead_event_rows",
        ]
        recon_payload = {name: reconciliation[i] for i, name in enumerate(reconciliation_columns)}
        recon_payload["contract_raw_rows"] = source_counts["contract"]
        recon_payload["contract_raw_amount_sum"] = raw_contract_amount_sum
        recon_payload["lead_raw_rows"] = source_counts["leads"]
        for left, right, delta_name in [
            ("contract_raw_amount_sum", "contract_version_amount_sum", "raw_to_event_version_amount_delta"),
            ("contract_fact_amount_sum", "contract_shop_bridge_amount_sum", "shop_bridge_amount_delta"),
            ("contract_fact_amount_sum", "contract_segment_bridge_amount_sum", "segment_bridge_amount_delta"),
            ("dated_contract_fact_amount_sum", "contract_month_amount_sum", "dated_month_amount_delta"),
        ]:
            a, b = recon_payload[left], recon_payload[right]
            recon_payload[delta_name] = None if a is None or b is None else float(b) - float(a)
        # The compact publication set keeps canonical entities and essential bridges only.
        tables = output_table_names()
        checks_df, gate = measure_call(profiler, "integrity_validation_and_row_reconciliation", build_validation_checks, con, cutoffs, source_counts, raw_contract_amount_sum)
        new_check_rows = []
        def record_new_check(name: str, passed: bool, observed: Any, expected: Any, severity: str, note: str) -> None:
            status = "PASS" if passed else ("WARNING" if severity == "WARNING" else "FAIL")
            new_check_rows.append({"check": name, "status": status, "severity": severity,
                                   "observed": json.dumps(observed, ensure_ascii=True, default=str),
                                   "expected": json.dumps(expected, ensure_ascii=True, default=str), "note": note})
        confirmed_pairs, primary_matches, primary_amount, all_contract_amount = con.execute("""
            SELECT count(*) FILTER (WHERE is_confirmed_match), count(*) FILTER (WHERE is_primary_match),
                   sum(candidate_credit_amount_raw) FILTER (WHERE is_primary_match),
                   (SELECT sum(credit_amount_raw) FROM contract_fact)
            FROM lead_contract_bridge
        """).fetchone()
        primary_per_contract = int(con.execute("""
            SELECT count(*) FROM (SELECT contract_fact_id FROM lead_contract_bridge
             WHERE is_primary_match GROUP BY 1 HAVING count(*) > 1)
        """).fetchone()[0])
        record_new_check("primary_matches_at_most_one_per_contract", primary_per_contract == 0,
                         primary_per_contract, 0, "FATAL", "At most one primary lead per contract.")
        amount_ok = primary_amount is None or all_contract_amount is None or float(primary_amount) <= float(all_contract_amount) + max(0.01, abs(float(all_contract_amount)) * 1e-9)
        record_new_check("primary_match_amount_not_above_all_contracts", amount_ok, primary_amount,
                         all_contract_amount, "FATAL", "Primary-match amount cannot exceed canonical contract amount.")
        record_new_check("confirmed_pairs_minimum_expected", int(confirmed_pairs or 0) >= 339000,
                         confirmed_pairs, ">=339000", "FATAL", "Expected approximately 339,529 criterion-qualified pairs.")
        if int(confirmed_pairs or 0) != 339529:
            new_check_rows.append({"check": "confirmed_pairs_vs_reference_warning", "status": "WARNING", "severity": "WARNING",
                                   "observed": json.dumps(confirmed_pairs), "expected": json.dumps(339529),
                                   "note": "Reference is approximate; investigate differences."})
        prior_counts = previous_metrics.get("published_parquet_row_counts", {})
        for table, previous_count in prior_counts.items():
            if table_exists(con, table):
                current_count = table_count(con, table)
                is_candidate_bridge = table == "lead_contract_candidates"
                record_new_check(f"existing_table_row_count_unchanged:{table}", current_count == int(previous_count),
                                 current_count, previous_count,
                                 "WARNING" if is_candidate_bridge else "FATAL",
                                 "Candidate count may change under strict client/product/known-date/time eligibility; all other legacy grains remain invariant." if is_candidate_bridge else "Existing published table count should remain stable.")
        previous_recon = previous_metrics.get("join_reconciliation", {})
        for key in ("contract_fact_amount_sum", "contract_month_amount_sum"):
            if key in previous_recon:
                current_value = recon_payload.get(key)
                unchanged = current_value is not None and abs(float(current_value)-float(previous_recon[key])) <= max(0.01,abs(float(previous_recon[key]))*1e-9)
                record_new_check(f"existing_amount_sum_unchanged:{key}", unchanged, current_value,
                                 previous_recon[key], "FATAL", "Existing canonical amount sum should remain stable.")
        checks_df = pd.concat([checks_df, pd.DataFrame(new_check_rows)], ignore_index=True)
        gate["fatal_failures"] = [row["check"] for row in checks_df.to_dict("records")
                                  if row["severity"] == "FATAL" and row["status"] != "PASS"]
        gate["execution_status"] = "SUCCESS" if not gate["fatal_failures"] else "FAILED"
        gate["foundation_quality_gate"] = "PASS" if not gate["business_gates_pending"] and not gate["fatal_failures"] else "CONDITIONAL"
        if gate["fatal_failures"]:
            raise AssertionError(f"Fatal Phase 1 validation failures: {gate['fatal_failures']}")

        dictionary = build_data_dictionary(con, tables, schema_descriptions)
        counts = measure_call(profiler, "parquet_exports_10_outputs", export_parquet_tables, con, staging_dir, tables)
        write_csv(staging_dir / "data_dictionary.csv", dictionary)
        r2_source_manifest = build_r2_source_manifest(files, cutoffs, input_fingerprints)

        parquet_checks = measure_call(profiler, "parquet_readability_verification", verify_parquet_files, staging_dir, tables, counts)
        coverage_df = con.execute("SELECT * FROM coverage_summary").df()
        status_df = con.execute("SELECT * FROM contract_status_mapping").df()
        weight_df = con.execute("SELECT * FROM weight_audit").df()
        funded_shares = con.execute("""
            SELECT avg(is_funded_sign_date::INT), avg(is_funded_status::INT), avg(is_funded_billing::INT)
            FROM contract_fact
        """).fetchone()
        product_crosswalk_df = con.execute("SELECT * FROM product_crosswalk").df()
        elapsed_before_final_publish = round(time.perf_counter() - overall_started, 4)
        file_sizes = {item["file"]: item["file_bytes"] for item in parquet_checks}
        comparison = previous_38_run_comparison(counts, recon_payload)
        metrics_payload = {
            "schema_version": "1.0",
            "run_id": run_id,
            "phase": "Phase 1 — Data Processing / Foundation only",
            "raw_inventory": inventory_df.to_dict("records"),
            "schema_validation": schema_df.to_dict("records"),
            "missingness": profile_df.to_dict("records"),
            "key_integrity": key_df.to_dict("records"),
            "contract_status_mapping": status_df.to_dict("records"),
            "product_crosswalk": product_crosswalk_df.to_dict("records"),
            "weight_audit": weight_df.to_dict("records"),
            "funded_definition": C.FUNDED_DEFINITION,
            "funded_shares": {"SIGN_DATE": funded_shares[0], "STATUS_MAP": funded_shares[1], "BILLING": funded_shares[2]},
            "confirmed_lead_contract_pairs": int(confirmed_pairs or 0),
            "primary_lead_contract_matches": int(primary_matches or 0),
            "nonprimary_pair_uuid_attribution": nonprimary_attribution,
            "employee_active_status_codes": sorted(C.APPROVED_EMPLOYEE_ACTIVE_STATUS_CODES),
            "published_parquet_row_counts": counts,
            "internal_audit_table_row_counts": {
                name: table_count(con, name) for name in (
                    "contract_product_summary", "lead_match_summary", "contract_shop_month_status",
                    "contract_shop_month_total", "contract_date_exceptions", "lead_date_exceptions",
                    "lead_reason_lookup", "lead_conversion_shop_month", "shop_behavior_profile",
                ) if table_exists(con, name)
            },
            "round2_cutoffs": cutoffs,
            "join_reconciliation": recon_payload,
            "report_path": "output/Data processing/data_quality_report.md",
            "report_bundle_dir": "output/Data processing",
            "validation_results": checks_df.to_dict("records"),
            "coverage_summary": coverage_df.to_dict("records"),
            "input_fingerprints": input_fingerprints,
            "pipeline_fingerprint": code_fingerprint,
            "incremental_cache": {
                "source_audits_reused": cache_audit,
                "reused_datasets": sorted(reuse_audits),
                "cache_source": "previous metrics fingerprint match" if cache_audit else "full refresh",
            },
            "stage_performance": profiler.records,
            "runtime_seconds_before_final_publish": elapsed_before_final_publish,
            "peak_rss_sampled_bytes": max((r["rss_sampled_peak_bytes"] or 0 for r in profiler.records), default=0),
            "duckdb_configuration": {"threads": C.DUCKDB_THREADS, "memory_limit": C.DUCKDB_MEMORY_LIMIT,
                                     "parquet_compression": C.PARQUET_COMPRESSION,
                                     "row_group_size": C.PARQUET_ROW_GROUP_SIZE},
            "parquet_file_sizes_bytes": file_sizes,
            "r2_source_manifest": r2_source_manifest,
            "parquet_output_paths": sorted(PUBLISHED_PARQUET_PATHS.values()),
            "superseded_generated_paths_removed_on_publish": [
                "lead_reason_clean.parquet", "customer_segment_shop_product_month.parquet",
                "R2/r2_link_coverage.parquet", "R2/r2_source_manifest.json"],
            "previous_38_parquet_run_comparison": comparison,
            "warnings": [
                "Peak RSS is a sampled process RSS high-water mark, not exact per-query memory.",
                "Lead rows use source ordinals and UUID-repeat counts rather than full-row hashing; exact lead-row duplicate counts are not computed.",
            ],
        }
        save_json(metrics_payload, staging_dir / "metrics_phase1.json")
        validation_payload = build_validation_payload(gate, checks_df, cutoffs, counts, inventory_df, coverage_df)
        validation_payload["join_reconciliation"] = recon_payload
        validation_payload["parquet_readback"] = parquet_checks
        validation_payload["metrics_file"] = "metrics_phase1.json"
        save_json(validation_payload, staging_dir / "validation_report.json")
        write_quality_report(staging_dir / "data_quality_report.md", inventory_df, schema_df, key_df,
                             profile_df, coverage_df, checks_df, gate, cutoffs, counts)
        publish_staged_outputs(staging_dir, C.OUTPUT_DIR)
        succeeded = True
        try:
            organize_phase1_reports(C.OUTPUT_DIR, C.REPORT_DIR)
            report_path = C.REPORT_DIR / "data_quality_report.md"
        except OSError:
            report_path = None
        return {"run_id": run_id, "output_dir": str(C.OUTPUT_DIR), "execution_status": gate["execution_status"],
                "report_path": str(report_path) if report_path else None,
                "foundation_quality_gate": gate["foundation_quality_gate"], "table_row_counts": counts,
                "fatal_failures": gate["fatal_failures"], "business_gates_pending": gate["business_gates_pending"],
                "parquet_files": len(parquet_checks)}
    finally:
        con.close()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if not succeeded and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)



# %%
if __name__ == "__main__":
    run()
