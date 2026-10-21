# BI10 Round 3 — Phase 1 Foundation Data Quality Report

- Run UTC: `2026-10-21T23:46:14.949357+00:00`
- Execution status: **SUCCESS**
- Foundation quality gate: **CONDITIONAL**
- Scope: source inventory, cleaning/version handling, bridges, cutoff-aware linkage, raw shop-month foundation, validation only.
- No Phase 2 EDA, forecasting, growth potential, ranking, recommendations, or figures were produced.

## Input inventory

| dataset | file_name | source_format | source_bytes | source_rows | source_columns | ingestion_policy |
|---|---|---|---|---|---|---|
| contract | contract.csv | csv | 573943563 | 3775371.0 | 21.0 | DuckDB VARCHAR-preserving CSV scan |
| leads | leads.csv | csv | 1068338893 | 6130637.0 | 19.0 | DuckDB VARCHAR-preserving CSV scan |
| contract_product | contract_product.csv | csv | 48520659 | 784902.0 | 5.0 | DuckDB VARCHAR-preserving CSV scan |
| employee_assignment | emp_2_salesroom.csv | csv | 17895356 | 275856.0 | 6.0 | DuckDB VARCHAR-preserving CSV scan |
| shop | salesroom.xlsx | xlsx | 1091472 | 14231.0 | 13.0 | pandas/openpyxl source values |
| seller | seller.xlsx | xlsx | 535791 | 11639.0 | 8.0 | pandas/openpyxl source values |
| lead_reason | cl_lead_fin_reason.xlsx | xlsx | 16924 | 12.0 | 9.0 | pandas/openpyxl source values |
| schema_workbook | StructureTable.xlsx | xlsx | 28840 |  |  | Read-only schema metadata |
| r2_fhs | BI10-Round2/output/Task1/scores/fh_scores.parquet | parquet | 51764752 | 1000528.0 | 47.0 | Read-only Round 2 score output; key uniqueness validated in score bridge |
| r2_ces | BI10-Round2/output/Task2/scores/eng_scores.parquet | parquet | 19137691 | 1000528.0 | 30.0 | Read-only Round 2 score output; key uniqueness validated in score bridge |

## Schema-to-source exceptions

The source CSVs were staged as VARCHAR to preserve IDs/codes; this is not a claim that their business types are strings.
`StructureTable.xlsx` now documents Contract Product fields. `skp_credit_case` is a case grouping key rather than a row-level unique key because cases may have multiple detail rows. Remaining schema differences are the district spelling mismatch, the undocumented lead weight/original-product fields, and the extra `SKP_EMP_MANAGE` source field.

| dataset | field | expected_type | observed_type | observed_ingest_type | type_review_state | schema_status | description |
|---|---|---|---|---|---|---|---|
| leads | sample_weight |  | VARCHAR | VARCHAR-preserved | NOT_DOCUMENTED_IN_SCHEMA | NOT_IN_SCHEMA | Observed in the supplied source but absent from StructureTable.xlsx. |
| leads | code_product_type_original |  | VARCHAR | VARCHAR-preserved | NOT_DOCUMENTED_IN_SCHEMA | NOT_IN_SCHEMA | Observed in the supplied source but absent from StructureTable.xlsx. |
| shop | SLAESROOM_DISTRICT | object |  | XLSX-inferred | XLSX_TYPE_RECORDED | MISSING_FROM_SOURCE | District where the salesroom is located ( '.' is a district following new Administrative boundary, others value is a district following old Administrative boundary - Resolution No. 202/2025/QH15) |
| shop | SALESROOM_DISTRICT |  | VARCHAR | XLSX-inferred | NOT_DOCUMENTED_IN_SCHEMA | NOT_IN_SCHEMA | Observed in the supplied source but absent from StructureTable.xlsx. |
| shop | SKP_EMP_MANAGE |  | INTEGER | XLSX-inferred | NOT_DOCUMENTED_IN_SCHEMA | NOT_IN_SCHEMA | Observed in the supplied source but absent from StructureTable.xlsx. |

## Key and duplicate audits

| dataset | declared_key_fields | source_rows | distinct_key_count | null_key_rows | duplicate_key_groups | duplicate_rows_beyond_first | exact_duplicate_rows | audit_state |
|---|---|---|---|---|---|---|---|---|
| contract | skp_credit_case | 3775371 | 3775371.0 | 0.0 | 0.0 | 0.0 | 0 | AUDITED_UNIQUE |
| leads | id_uuid | 6130637 | 5921646.0 | 0.0 | 208990.0 | 208991.0 |  | UUID_REPEAT_AUDITED; SOURCE_ROWS_PRESERVED; EXACT_ROW_FINGERPRINT_SKIPPED_PERFORMANCE |
| contract_product |  | 784902 |  |  |  |  | 1400 | NO_DECLARED_PRIMARY_KEY; ROW_FINGERPRINT_AUDITED |
| employee_assignment | role,skp_salesroom,skp_employee,dtime_valid_from,dtime_valid_to,code_status | 275856 | 274944.0 | 0.0 | 912.0 | 912.0 | 912 | AUDITED; DUPLICATES_RETAINED_AND_FLAGGED |
| shop | SKP_SALESROOM | 14231 | 14231.0 | 0.0 | 0.0 | 0.0 | 0 | AUDITED_UNIQUE |
| seller | SKP_SELLER | 11639 | 11639.0 | 0.0 | 0.0 | 0.0 | 0 | AUDITED_UNIQUE |
| lead_reason | ID_SOURCE,DATE_EFFECTIVE,CODE_SOURCE_SYSTEM | 12 | 12.0 | 0.0 | 0.0 | 0.0 | 0 | AUDITED_UNIQUE |

## Highest missing/blank rates

| dataset | column | ingest_type | source_rows | null_count | blank_count | null_or_blank_count | null_or_blank_pct | placeholder_count | zero_count_if_numeric | numeric_sum_if_numeric |
|---|---|---|---|---|---|---|---|---|---|---|
| leads | skp_employee | VARCHAR-preserved | 6130637 | 6130637 | 0 | 6130637 | 100.0 | 0 |  |  |
| shop | SALESROOM_END | XLSX-inferred | 14231 | 12030 | 0 | 12030 | 84.5338 | 0 |  |  |
| contract | price | VARCHAR-preserved | 3775371 | 2995428 | 0 | 2995428 | 79.3413 | 0 | 0.0 | 21224263646820.0 |
| contract | amt_billing_1st | VARCHAR-preserved | 3775371 | 2959530 | 0 | 2959530 | 78.3904 | 0 | 26165.0 | 3212441955012.5 |
| contract | amt_billing_2nd | VARCHAR-preserved | 3775371 | 2959530 | 0 | 2959530 | 78.3904 | 0 | 606642.0 | 952196450798.0 |
| contract | amt_billing_3rd | VARCHAR-preserved | 3775371 | 2959530 | 0 | 2959530 | 78.3904 | 0 | 654710.0 | 808448499792.0 |
| contract | payment_num | VARCHAR-preserved | 3775371 | 1417426 | 0 | 1417426 | 37.544 | 0 | 0.0 | 37895375.0 |
| contract_product | goods_group | VARCHAR-preserved | 784902 | 12476 | 0 | 12476 | 1.5895 | 0 |  |  |
| contract | product | VARCHAR-preserved | 3775371 | 49147 | 0 | 49147 | 1.3018 | 0 |  |  |
| contract | init_pay | VARCHAR-preserved | 3775371 | 49147 | 0 | 49147 | 1.3018 | 0 | 2983329.0 | 7645004854000.0 |
| leads | result | VARCHAR-preserved | 6130637 | 20411 | 0 | 20411 | 0.3329 | 0 | 0.0 | 7629554.0 |
| leads | amt_loan_limit | VARCHAR-preserved | 6130637 | 19372 | 0 | 19372 | 0.316 | 0 | 0.0 | 378447352063523.0 |
| contract | skp_salesroom | VARCHAR-preserved | 3775371 | 55 | 0 | 55 | 0.0015 | 0 |  |  |
| contract | skp_product | VARCHAR-preserved | 3775371 | 7 | 0 | 7 | 0.0002 | 0 |  |  |
| contract | credit_amount | VARCHAR-preserved | 3775371 | 7 | 0 | 7 | 0.0002 | 0 | 1137724.0 | 70604962581146.0 |
| contract | ins_amount | VARCHAR-preserved | 3775371 | 7 | 0 | 7 | 0.0002 | 0 | 2624686.0 | 3109817679076.9004 |
| contract | skp_client | VARCHAR-preserved | 3775371 | 7 | 0 | 7 | 0.0002 | 0 |  |  |
| contract | skp_emp_pre_process | VARCHAR-preserved | 3775371 | 1 | 0 | 1 | 0.0 | 0 |  |  |
| contract | skp_credit_case | VARCHAR-preserved | 3775371 | 0 | 0 | 0 | 0.0 | 0 |  |  |
| contract | name_status | VARCHAR-preserved | 3775371 | 0 | 0 | 0 | 0.0 | 0 |  |  |

## Coverage

| coverage_area | population | numerator | denominator | coverage_pct | status | details |
|---|---|---|---|---|---|---|
| CURRENT_SHOP_MASTER | CONTRACT_TO_CURRENT_SHOP | 621387.0 | 3775371.0 | 16.459 | CURRENT_SNAPSHOT_ONLY | 26,654 distinct fact shop IDs; unmatched IDs preserved. |
| CURRENT_SHOP_MASTER | LEAD_TO_CURRENT_SHOP | 385273.0 | 6130637.0 | 6.2844 | CURRENT_SNAPSHOT_ONLY | 27,380 distinct fact shop IDs; unmatched IDs preserved. |
| PRODUCT_CROSSWALK | LEAD_EVENT_ROWS | 6031418.0 | 6130637.0 | 98.3816 | CONFIGURED | 0 event rows have literal candidate mappings; not approved by default. |
| LEAD_CONTRACT_CANDIDATES | LEAD_CONTRACT_BRIDGE_ROWS | 339529.0 | 339529.0 | 100.0 | CONDITIONAL_ON_APPROVED_PRODUCT_CROSSWALK | {"MATCHED": 339529} |
| ROUND2_LINKAGE | R2_SCORE_FILES:ALL | 1000528.0 |  |  | CUTOFF_PROVENANCE_REVIEW_REQUIRED | FHS 1,000,528 rows/1,000,528 clients; CES 1,000,528/1,000,528; 0 unpaired/ambiguous. |
| ROUND2_LINKAGE | CONTRACT_APPLICATIONS:ALL | 349399.0 | 2513153.0 | 13.9028 | CUTOFF_PROVENANCE_REVIEW_REQUIRED | Distinct clients are unweighted; duplicated lead UUID/version rows remain event rows. |
| ROUND2_LINKAGE | CONTRACT_APPLICATIONS:STRICTLY_POST_COMMON_CUTOFF | 200892.0 | 1974930.0 | 10.1721 | CUTOFF_PROVENANCE_REVIEW_REQUIRED | Distinct clients are unweighted; duplicated lead UUID/version rows remain event rows. |
| ROUND2_LINKAGE | LEAD_ASSIGNMENTS:ALL | 228427.0 | 3631389.0 | 6.2903 | CUTOFF_PROVENANCE_REVIEW_REQUIRED | Distinct clients are unweighted; duplicated lead UUID/version rows remain event rows. |
| ROUND2_LINKAGE | LEAD_ASSIGNMENTS:STRICTLY_POST_COMMON_CUTOFF | 228427.0 | 3631389.0 | 6.2903 | CUTOFF_PROVENANCE_REVIEW_REQUIRED | Distinct clients are unweighted; duplicated lead UUID/version rows remain event rows. |
| LEAD_WEIGHT | ALL_LEAD_SOURCE_ROWS | 6130637.0 | 6130637.0 | 100.0 | UNAPPROVED_QA_ONLY | Observed weight sum 43454845.0002234; missing 0; nonpositive 0. Not a lead count or population estimate. |

## Core row counts

| table | rows |
|---|---|
| contract_fact | 3775371 |
| leads_clean | 6130637 |
| contract_product_bridge | 784902 |
| shop_bridge | 14231 |
| seller_master | 11639 |
| employee_shop_bridge | 275856 |
| lead_contract_candidates | 339529 |
| shop_month_foundation | 715528 |
| lead_shop_month_product | 349564 |
| lead_conversion_shop_month | 140230 |
| shop_behavior_profile | 30705 |
| r2_customer_segment | 1000528 |

## Automated validations

| check | status | severity | observed | expected | note |
|---|---|---|---|---|---|
| all_contract_source_rows_preserved | PASS | FATAL | 3775371 | 3775371 | Every contract source row remains in contract_event_version, including duplicates and conflicting case versions. |
| all_lead_source_rows_preserved | PASS | FATAL | 6130637 | 6130637 | Every lead source row remains in lead_event_version; repeated UUIDs are not deduplicated. |
| all_product_detail_rows_preserved | PASS | FATAL | 784902 | 784902 | Source-level detail rows remain in their bridge table. |
| all_employee_assignment_rows_preserved | PASS | FATAL | 275856 | 275856 | Source-level detail rows remain in their bridge table. |
| all_lead_reason_rows_preserved | PASS | FATAL | 12 | 12 | Source-level detail rows remain in their bridge table. |
| contract_fact_id_unique | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| lead_row_id_unique | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| shop_master_record_id_unique | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| seller_master_record_id_unique | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| r2_segment_client_key_unique | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| lead_match_summary_one_row_per_lead | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| shop_behavior_profile_one_row_per_shop | PASS | FATAL | 0 | 0 | Canonical bridge key must not fan out downstream joins. |
| contract_shop_bridge_no_row_inflation | PASS | FATAL | 3775371 | 3775371 | One-row-per-source-event bridge must preserve its source grain. |
| lead_shop_bridge_no_row_inflation | PASS | FATAL | 6130637 | 6130637 | One-row-per-source-event bridge must preserve its source grain. |
| contract_segment_bridge_no_row_inflation | PASS | FATAL | 3775371 | 3775371 | One-row-per-source-event bridge must preserve its source grain. |
| lead_segment_bridge_no_row_inflation | PASS | FATAL | 6130637 | 6130637 | One-row-per-source-event bridge must preserve its source grain. |
| lead_match_summary_no_row_loss | PASS | FATAL | 6130637 | 6130637 | One-row-per-source-event bridge must preserve its source grain. |
| contract_product_summary_one_row_per_case | PASS | FATAL | 0 | 0 | Product details are aggregated before joining to contract_fact. |
| contract_shop_month_grain_unique | PASS | FATAL | 0 | 0 | Declared aggregate grain is unique. |
| contract_shop_month_total_grain_unique | PASS | FATAL | 0 | 0 | Declared aggregate grain is unique. |
| lead_conversion_shop_month_grain_unique | PASS | FATAL | 0 | 0 | Declared aggregate grain is unique. |
| shop_month_foundation_grain_unique | PASS | FATAL | 0 | 0 | One row per shop identifier (including unknown) and month. |
| lead_product_month_event_rows_reconcile | PASS | FATAL | 6130637 | 6130637 | Product-month aggregates count raw lead events once; UUID/client counts remain separate. |
| lead_shop_month_event_rows_reconcile | PASS | FATAL | 6130637 | 6130637 | Shop-month lead event totals come directly from lead source events, not sums of product-level distinct counts. |
| contract_month_event_rows_reconcile | PASS | FATAL | 3775371 | 3775371 | Contract shop-month totals reconcile to date-valid canonical application events. |
| contract_foundation_event_rows_reconcile | PASS | FATAL | 3775371 | 3775371 | Shop-month foundation totals reconcile without dimension fanout. |
| raw_to_event_version_amount_reconcile | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Casting to numeric must preserve the sum of parseable source credit_amount values. |
| contract_shop_bridge_amount_no_inflation | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Left-joining current shop attributes must preserve canonical raw amounts. |
| contract_segment_bridge_amount_no_inflation | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Left-joining Round 2 segments must preserve canonical raw amounts. |
| dated_contract_month_amount_reconcile | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Raw amount sum in shop-month total must match date-valid canonical events; it is not labeled funded volume. |
| funded_month_counts_reconcile | PASS | FATAL | 2715985 | 2715985 | Selected funded flag counts reconcile over dated application months. |
| funded_month_amount_reconcile | PASS | FATAL | 48180834314366.0 | 48180834314366.0 | Selected funded credit amount reconciles over dated application months. |
| funded_foundation_counts_reconcile | PASS | FATAL | 2715985 | 2715985 | Foundation selected-funded count reconciles without fanout. |
| funded_foundation_amount_reconcile | PASS | FATAL | 48180834314366.0 | 48180834314366.0 | Foundation selected-funded amount reconciles without fanout. |
| conversion_month_primary_matches_reconcile | PASS | FATAL | 260674 | 260674 | Shop-month conversion table accounts for each primary confirmed match once. |
| sample_weight_raw_and_typed_columns_are_distinct | PASS | FATAL | {"sample_weight": "DOUBLE", "sample_weight_raw": "VARCHAR"} | {"sample_weight": "DOUBLE", "sample_weight_raw": "VARCHAR"} | Raw source representation and parsed QA-only sensitivity value must not collide or be mistaken for each other. |
| round2_production_score_cutoffs_read_from_source_config | PASS | CONDITIONAL | "2025-06-05" | "FHS and CES SNAPSHOT_DATE" | Production score snapshots are read from Round 2 config; feature-level timestamp lineage still requires review. |
| round2_feature_timestamp_lineage_audited | FAIL | BUSINESS_GATE | "REVIEW_REQUIRED" | "Every score feature timestamp verified" | Code snapshot dates are known, but this pipeline does not certify every feature's point-in-time lineage. |
| lead_product_crosswalk_approved | PASS | BUSINESS_GATE | 4 | ">=1 configured team-assumption mappings" | Configured equality mappings are competition assumptions, not owner approvals. |
| contract_status_outcome_semantics_approved | PASS | BUSINESS_GATE | 7 | ">=1 explicit status mappings" | Current/final statuses are retained raw; funded outcome remains undefined unless approved. |
| lead_sample_weight_semantics_approved | FAIL | BUSINESS_GATE | "UNAPPROVED_QA_ONLY" | "source-owner scope and estimator approval" | Weights are preserved and summarized for QA only; no weighted population claim is emitted. |
| employee_active_status_codes_approved | PASS | BUSINESS_GATE | 1 | ">=1 approved active status" | Raw assignment intervals remain available; active headcount proxy is null by default. |
| primary_matches_at_most_one_per_contract | PASS | FATAL | 0 | 0 | At most one primary lead per contract. |
| primary_match_amount_not_above_all_contracts | PASS | FATAL | 5839719628947.0 | 70604962581146.0 | Primary-match amount cannot exceed canonical contract amount. |
| confirmed_pairs_minimum_expected | PASS | FATAL | 339529 | ">=339000" | Expected approximately 339,529 criterion-qualified pairs. |
| existing_table_row_count_unchanged:contract_fact | PASS | FATAL | 3775371 | 3775371 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:leads_clean | PASS | FATAL | 6130637 | 6130637 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:contract_product_bridge | PASS | FATAL | 784902 | 784902 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:shop_bridge | PASS | FATAL | 14231 | 14231 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:seller_master | PASS | FATAL | 11639 | 11639 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:employee_shop_bridge | PASS | FATAL | 275856 | 275856 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:lead_contract_candidates | PASS | WARNING | 339529 | 339529 | Candidate count may change under strict client/product/known-date/time eligibility; all other legacy grains remain invariant. |
| existing_table_row_count_unchanged:shop_month_foundation | PASS | FATAL | 715528 | 715528 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:lead_shop_month_product | PASS | FATAL | 349564 | 349564 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:lead_conversion_shop_month | PASS | FATAL | 140230 | 140230 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:shop_behavior_profile | PASS | FATAL | 30705 | 30705 | Existing published table count should remain stable. |
| existing_table_row_count_unchanged:r2_customer_segment | PASS | FATAL | 1000528 | 1000528 | Existing published table count should remain stable. |
| existing_amount_sum_unchanged:contract_fact_amount_sum | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Existing canonical amount sum should remain stable. |
| existing_amount_sum_unchanged:contract_month_amount_sum | PASS | FATAL | 70604962581146.0 | 70604962581146.0 | Existing canonical amount sum should remain stable. |

## Cutoff and unresolved business definitions

- Round 2 production score snapshot: FHS `2025-06-05`; CES `2025-06-05`; combined segment outcome cutoff `2025-06-05`.
- Round 2 validation freezes (not used as export cutoffs): FH_ASOF `2024-10-01`; ENG_ASOF `2025-02-01`.
- The Round 2 production score-generation code uses SNAPSHOT_DATE for both exported populations; feature-level timestamp lineage remains a review gate.
- Cutoff status: PRODUCTION_SCORE_SNAPSHOT_DECLARED_IN_ROUND2_CONFIG; FEATURE-LEVEL TIMESTAMP AUDIT STILL REQUIRED
- Product compatibility uses a competition-run exact-code assumption for TW/CL/CC/CD only; REL remains unmapped and the assumption is not owner approval.
- `is_funded` uses `STATUS_MAP`; provisional status categories include FUNDED, PAID_OFF and WRITTEN_OFF.
- `sample_weight` remains QA-only; it is not used as an estimator or applied to counts, conversions, customers, or amounts.
- Employee active proxy uses configured provisional code A based on the status profile; confirm operational meaning before treating as headcount.
- Shop/seller fields describe current master snapshots only; historical validity is not claimed.
- Sentinel years 2999/3000 are converted to NULL in canonical timestamps and retained as source raw values plus explicit flags.
- Contract/lead rows with missing or invalid event dates remain flagged in `contract_clean.parquet` / `leads_clean.parquet`; exception-row counts are recorded in `metrics_phase1.json` and such rows are excluded only from dated monthly aggregates.

## Phase boundary

This report and its Parquet outputs constitute Phase 1 only. Continue only after explicit approval and resolution of the relevant Foundation gates.
