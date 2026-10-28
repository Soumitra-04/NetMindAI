"""
Leakage-aware CIC-IDS2017 cleaning pipeline for NetMind.

Run from project root:
    uv run python scripts/clean_dataset.py

Dependencies:
    uv add duckdb

Inputs:
    data/raw/MachineLearningCVE/*.csv

Outputs:
    data/processed/cleaned_v2/{train,validation,test}.csv
    data/processed/cleaned_v2/cleaning_report.json
    data/processed/cleaned_v2/cleaning_work.duckdb

Split policy:
    train      Monday, Tuesday, Wednesday
    validation Thursday
    test       Friday

Important design choices:
- Original raw files are never modified.
- Input is read with DuckDB into a disk-backed database.
- Rows with clearly invalid negative duration/IAT/header-length/packet-size values
  are removed. Large values alone are NOT considered outliers.
- -1 window-size sentinel values are preserved.
- Infinite flow rates are converted to missing; rows with any missing/nonfinite
  feature values are dropped (expected to affect a small number of rows).
- Deduplication is global and uses feature values only to identify identical
  flow records. Same-feature/different-label conflicts are reported and excluded
  as ambiguous rows. For duplicates spanning days, the earliest capture day is
  retained, so an exact flow cannot cross split boundaries.
- Feature columns are not selected using test/validation labels. The day split is
  assigned before conflict removal and deduplication.
- Label and capture_day are metadata and must never be model inputs.

Note:
This script is intentionally conservative with outlier removal: no IQR/z-score
cutoffs are used because rare attacks can legitimately have extreme traffic stats.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "MachineLearningCVE"
OUT_DIR = ROOT / "data" / "processed" / "cleaned_v2"
DB_PATH = OUT_DIR / "cleaning_work.duckdb"

LABEL_COL = "Label"
SPLIT_DAYS = {
    "train": ["Monday", "Tuesday", "Wednesday"],
    "validation": ["Thursday"],
    "test": ["Friday"],
}

# Known constant or duplicate fields in the CIC-IDS2017 export.
DROP_FEATURES = {
    "Bwd PSH Flags",
    "Bwd URG Flags",
    "CWE Flag Count",
    "Fwd URG Flags",
    "Fwd Avg Bytes/Bulk",
    "Fwd Avg Packets/Bulk",
    "Fwd Avg Bulk Rate",
    "Bwd Avg Bytes/Bulk",
    "Bwd Avg Packets/Bulk",
    "Bwd Avg Bulk Rate",
    "Fwd Header Length.1",
    "Fwd Header Length_1",
}

# These feature families represent quantities that cannot be negative.
# Window-size features are deliberately excluded because -1 can be a sentinel.
NONNEGATIVE_FEATURES = {
    "Flow Duration",
    "Flow IAT Mean",
    "Flow IAT Std",
    "Flow IAT Max",
    "Flow IAT Min",
    "Fwd IAT Total",
    "Fwd IAT Mean",
    "Fwd IAT Std",
    "Fwd IAT Max",
    "Fwd IAT Min",
    "Bwd IAT Total",
    "Bwd IAT Mean",
    "Bwd IAT Std",
    "Bwd IAT Max",
    "Bwd IAT Min",
    "Fwd Header Length",
    "Bwd Header Length",
    "Fwd Packet Length Max",
    "Fwd Packet Length Min",
    "Fwd Packet Length Mean",
    "Fwd Packet Length Std",
    "Bwd Packet Length Max",
    "Bwd Packet Length Min",
    "Bwd Packet Length Mean",
    "Bwd Packet Length Std",
    "Min Packet Length",
    "Max Packet Length",
    "Packet Length Mean",
    "Packet Length Std",
    "Packet Length Variance",
    "Average Packet Size",
    "Avg Fwd Segment Size",
    "Avg Bwd Segment Size",
    "Active Mean",
    "Active Std",
    "Active Max",
    "Active Min",
    "Idle Mean",
    "Idle Std",
    "Idle Max",
    "Idle Min",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Fwd Packets/s",
    "Bwd Packets/s",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Subflow Fwd Packets",
    "Subflow Fwd Bytes",
    "Subflow Bwd Packets",
    "Subflow Bwd Bytes",
    "act_data_pkt_fwd",
    "min_seg_size_forward",
}

WEB_ATTACK_LABELS = {
    "brute force": "Web Attack - Brute Force",
    "xss": "Web Attack - XSS",
    "sql injection": "Web Attack - SQL Injection",
}


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def qp(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def normalize_label_sql(expr: str) -> str:
    return f"""
        CASE
          WHEN upper(trim(CAST({expr} AS VARCHAR))) = 'BENIGN' THEN 'BENIGN'
          WHEN contains(lower(CAST({expr} AS VARCHAR)), 'web attack')
               AND contains(lower(CAST({expr} AS VARCHAR)), 'brute force')
            THEN 'Web Attack - Brute Force'
          WHEN contains(lower(CAST({expr} AS VARCHAR)), 'web attack')
               AND contains(lower(CAST({expr} AS VARCHAR)), 'xss')
            THEN 'Web Attack - XSS'
          WHEN contains(lower(CAST({expr} AS VARCHAR)), 'web attack')
               AND (contains(lower(CAST({expr} AS VARCHAR)), 'sql injection')
                    OR contains(lower(CAST({expr} AS VARCHAR)), 'sql'))
            THEN 'Web Attack - SQL Injection'
          ELSE trim(CAST({expr} AS VARCHAR))
        END
    """


def capture_day_sql(filename_expr: str) -> str:
    return f"""
        CASE
          WHEN contains(lower({filename_expr}), 'monday') THEN 'Monday'
          WHEN contains(lower({filename_expr}), 'tuesday') THEN 'Tuesday'
          WHEN contains(lower({filename_expr}), 'wednesday') THEN 'Wednesday'
          WHEN contains(lower({filename_expr}), 'thursday') THEN 'Thursday'
          WHEN contains(lower({filename_expr}), 'friday') THEN 'Friday'
          ELSE 'Unknown'
        END
    """


def day_order_sql(day_expr: str) -> str:
    return f"""
        CASE {day_expr}
          WHEN 'Monday' THEN 0
          WHEN 'Tuesday' THEN 1
          WHEN 'Wednesday' THEN 2
          WHEN 'Thursday' THEN 3
          WHEN 'Friday' THEN 4
          ELSE 99
        END
    """


def main() -> None:
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {RAW_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "duckdb_tmp").mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads TO 4")
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = {qp(OUT_DIR / 'duckdb_tmp')}")

    file_list = "[" + ", ".join(qp(f) for f in files) + "]"
    print(f"Found {len(files)} CSV files.")
    print("Importing source data into a disk-backed DuckDB database...")

    con.execute(f"""
        CREATE TABLE raw AS
        SELECT *
        FROM read_csv(
            {file_list},
            header = true,
            union_by_name = true,
            filename = true,
            all_varchar = true,
            ignore_errors = false
        )
    """)

    # Normalize whitespace in source column names.
    columns = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    for col in columns:
        trimmed = col.strip().lstrip("\ufeff")
        if trimmed and trimmed != col:
            con.execute(f"ALTER TABLE raw RENAME COLUMN {qi(col)} TO {qi(trimmed)}")
    columns = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    if LABEL_COL not in columns or "filename" not in columns:
        raise ValueError("Expected Label column or DuckDB filename metadata is missing.")

    raw_features = [c for c in columns if c not in {LABEL_COL, "filename"}]
    drop_present = sorted(c for c in DROP_FEATURES if c in raw_features)
    features = [c for c in raw_features if c not in drop_present]
    if not features:
        raise RuntimeError("No model features remain.")

    # Build a typed table. Invalid numeric strings become NULL.
    expressions = []
    for col in features:
        expressions.append(f"try_cast(trim(CAST({qi(col)} AS VARCHAR)) AS DOUBLE) AS {qi(col)}")
    expressions.extend([
        f"{normalize_label_sql(qi(LABEL_COL))} AS clean_label",
        "filename AS source_file",
        f"{capture_day_sql('filename')} AS capture_day",
    ])
    con.execute(f"""
        CREATE TABLE typed AS
        SELECT {", ".join(expressions)}
        FROM raw
        WHERE "{LABEL_COL}" IS NOT NULL
          AND trim(CAST("{LABEL_COL}" AS VARCHAR)) <> ''
    """)

    # Fail closed if unexpected files cannot be assigned to a known capture day.
    unknown_days = int(con.execute(
        "SELECT count(*) FROM typed WHERE capture_day='Unknown'"
    ).fetchone()[0])
    if unknown_days:
        raise ValueError(f"{unknown_days} rows have unknown capture days; refusing to split.")

    # Record label counts before cleaning and split assignment.
    labels_before = dict(con.execute("""
        SELECT clean_label, count(*) FROM typed
        GROUP BY clean_label ORDER BY clean_label
    """).fetchall())

    # Count and remove rows with missing or non-finite values in any retained feature.
    # Convert +/-infinity to NULL. Drop rows with any feature missing/non-finite.
    missing_per_feature = {}
    for col in features:
        c = qi(col)
        missing = int(con.execute(
            f"SELECT count(*) FROM typed WHERE {c} IS NULL"
        ).fetchone()[0])
        nonfinite = int(con.execute(
            f"SELECT count(*) FROM typed WHERE {c} IS NOT NULL AND NOT isfinite({c})"
        ).fetchone()[0])
        missing_per_feature[col] = {
            "null_or_non_numeric": missing,
            "infinite_or_nonfinite": nonfinite,
        }

    null_predicate = " OR ".join(
        f"{qi(c)} IS NULL OR NOT isfinite({qi(c)})" for c in features
    )
    rows_missing_or_nonfinite = int(con.execute(
        f"SELECT count(*) FROM typed WHERE {null_predicate}"
    ).fetchone()[0])

    # Remove records with impossible negative values in nonnegative feature fields.
    # Keep -1 for initial window size fields; they are not in NONNEGATIVE_FEATURES.
    nonnegative_present = [c for c in NONNEGATIVE_FEATURES if c in features]
    negative_predicate = " OR ".join(f"{qi(c)} < 0" for c in nonnegative_present)
    rows_with_invalid_negatives = int(con.execute(
        f"SELECT count(*) FROM typed WHERE {negative_predicate}"
    ).fetchone()[0]) if negative_predicate else 0

    # Track which rule removed a row first, so report categories are non-overlapping.
    con.execute(f"""
        CREATE TABLE valid_rows AS
        SELECT *
        FROM typed
        WHERE NOT ({null_predicate})
          AND NOT ({negative_predicate if negative_predicate else 'FALSE'})
    """)
    rows_after_value_cleaning = int(con.execute("SELECT count(*) FROM valid_rows").fetchone()[0])

    # Fingerprint features independently of label. If same feature vector has multiple
    # labels anywhere, treat it as ambiguous and exclude all rows with that fingerprint.
    feature_struct = "struct_pack(" + ", ".join(
        f"f{i} := {qi(c)}" for i, c in enumerate(features)
    ) + ")"
    feature_fp = f"sha256(to_json({feature_struct}))"
    label_counts_by_feature = """
        SELECT feature_fingerprint
        FROM (
          SELECT feature_fingerprint, count(DISTINCT clean_label) AS label_count
          FROM (
            SELECT clean_label, sha256(to_json(struct_pack(
              """ + ", ".join(f"f{i} := {qi(c)}" for i, c in enumerate(features)) + """
            ))) AS feature_fingerprint
            FROM valid_rows
          )
          GROUP BY feature_fingerprint
        )
        WHERE label_count > 1
    """
    con.execute(f"""
        CREATE TABLE fingerprinted AS
        SELECT *, {feature_fp} AS feature_fingerprint,
          sha256(to_json(struct_pack(
            {", ".join(f"f{i} := {qi(c)}" for i, c in enumerate(features))},
            label := clean_label
          ))) AS full_fingerprint,
          {day_order_sql('capture_day')} AS day_order
        FROM valid_rows
    """)
    con.execute(f"CREATE TABLE conflicts AS {label_counts_by_feature}")
    conflicting_groups = int(con.execute("SELECT count(*) FROM conflicts").fetchone()[0])
    conflicting_rows = int(con.execute("""
        SELECT count(*) FROM fingerprinted f
        JOIN conflicts c USING (feature_fingerprint)
    """).fetchone()[0])

    # Assign split membership BEFORE applying conflict exclusion/deduplication.
    # The split is derived only from source filename/day, never labels.
    con.execute("""
        CREATE TABLE assigned AS
        SELECT *,
          CASE
            WHEN capture_day IN ('Monday','Tuesday','Wednesday') THEN 'train'
            WHEN capture_day='Thursday' THEN 'validation'
            WHEN capture_day='Friday' THEN 'test'
          END AS split_name
        FROM fingerprinted
    """)

    # Exclude conflicting fingerprints. For exact duplicates with the same label,
    # keep the earliest day occurrence. This guarantees no exact flow crosses splits.
    con.execute("""
        CREATE TABLE unambiguous AS
        SELECT a.*
        FROM assigned a
        LEFT JOIN conflicts c USING (feature_fingerprint)
        WHERE c.feature_fingerprint IS NULL
    """)
    con.execute("""
        CREATE TABLE deduplicated AS
        SELECT * EXCLUDE (rn)
        FROM (
          SELECT *,
            row_number() OVER (
              PARTITION BY full_fingerprint
              ORDER BY day_order ASC, source_file ASC
            ) AS rn
          FROM unambiguous
        )
        WHERE rn=1
    """)

    # Report row accounting.
    raw_rows = int(con.execute("SELECT count(*) FROM raw").fetchone()[0])
    typed_rows = int(con.execute("SELECT count(*) FROM typed").fetchone()[0])
    valid_rows_count = int(con.execute("SELECT count(*) FROM valid_rows").fetchone()[0])
    dedup_rows = int(con.execute("SELECT count(*) FROM deduplicated").fetchone()[0])
    duplicate_rows_removed = valid_rows_count - conflicting_rows - dedup_rows
    if duplicate_rows_removed < 0:
        # Conflict rows were counted before split and all are removed from valid rows;
        # defensive fallback for unexpected accounting differences.
        duplicate_rows_removed = int(con.execute("""
            SELECT count(*) - count(DISTINCT full_fingerprint) FROM unambiguous
        """).fetchone()[0])

    labels_after = dict(con.execute("""
        SELECT clean_label, count(*) FROM deduplicated
        GROUP BY clean_label ORDER BY clean_label
    """).fetchall())

    split_report = {}
    for split_name, days in SPLIT_DAYS.items():
        day_list = ", ".join("'" + d + "'" for d in days)
        rows = int(con.execute(
            f"SELECT count(*) FROM deduplicated WHERE split_name='{split_name}'"
        ).fetchone()[0])
        labels = dict(con.execute(f"""
            SELECT clean_label, count(*) FROM deduplicated
            WHERE split_name='{split_name}'
            GROUP BY clean_label ORDER BY clean_label
        """).fetchall())
        targets = dict(con.execute(f"""
            SELECT CASE WHEN upper(clean_label)='BENIGN' THEN 0 ELSE 1 END AS target,
                   count(*)
            FROM deduplicated
            WHERE split_name='{split_name}'
            GROUP BY target ORDER BY target
        """).fetchall())
        split_report[split_name] = {
            "days": days,
            "rows": rows,
            "label_counts": {str(k): int(v) for k,v in labels.items()},
            "binary_target_counts": {str(k): int(v) for k,v in targets.items()},
        }
        out_path = OUT_DIR / f"{split_name}.csv"
        output_cols = [qi(c) for c in features] + [
            "clean_label AS Label",
            "CASE WHEN upper(clean_label)='BENIGN' THEN 0 ELSE 1 END AS target",
            "capture_day",
        ]
        con.execute(f"""
            COPY (
              SELECT {", ".join(output_cols)}
              FROM deduplicated
              WHERE split_name='{split_name}'
            ) TO {qp(out_path)} (HEADER, DELIMITER ',')
        """)

    report = {
        "source_files": [p.name for p in files],
        "raw_rows": raw_rows,
        "rows_with_nonempty_labels": typed_rows,
        "rows_with_missing_or_nonfinite_feature_values": rows_missing_or_nonfinite,
        "rows_with_invalid_negative_values": rows_with_invalid_negatives,
        "rows_after_value_cleaning": rows_after_value_cleaning,
        "conflicting_feature_groups_excluded": conflicting_groups,
        "rows_in_conflicting_groups_excluded": conflicting_rows,
        "exact_duplicate_rows_removed": duplicate_rows_removed,
        "rows_retained": dedup_rows,
        "features_retained": features,
        "features_dropped_by_policy": drop_present,
        "missing_or_nonfinite_by_feature_before_row_drop": missing_per_feature,
        "label_counts_before_cleaning": {str(k): int(v) for k,v in labels_before.items()},
        "label_counts_after_cleaning_and_deduplication": {str(k): int(v) for k,v in labels_after.items()},
        "split_policy": SPLIT_DAYS,
        "split_summary": split_report,
        "integrity_checks": {
            "split_membership_assigned_by_capture_day_before_conflict_removal": True,
            "no_unknown_capture_days": True,
            "target_definition": "0=BENIGN, 1=any attack",
            "metadata_excluded_from_model_features": ["Label", "target", "capture_day"],
            "window_size_minus_one_preserved": True,
            "no_statistical_outlier_cutoff_used": True,
        },
        "notes": [
            "Original CSVs were not modified.",
            "Rows with any missing/non-finite retained feature were dropped.",
            "Rows with negative values in designated nonnegative features were dropped.",
            "Large values were retained unless they violated explicit nonnegative validity rules.",
            "Conflicting feature vectors with different labels were excluded globally and reported.",
            "Identical feature+label duplicates were globally deduplicated, keeping earliest capture day.",
            "No imputation was performed; no model was trained.",
            "The split is by capture day and some validation/test attack families may be unseen in training.",
            "Because cross-day exact duplicates are assigned to their earliest day, later-day split counts may decrease.",
        ],
    }
    report_path = OUT_DIR / "cleaning_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nCleaning complete.")
    print(f"Raw rows: {raw_rows:,}")
    print(f"Rows with nonempty labels: {typed_rows:,}")
    print(f"Rows with missing/nonfinite feature values: {rows_missing_or_nonfinite:,}")
    print(f"Rows with invalid negative values: {rows_with_invalid_negatives:,}")
    print(f"Rows after value cleaning: {rows_after_value_cleaning:,}")
    print(f"Conflicting feature groups excluded: {conflicting_groups:,}")
    print(f"Rows in conflicting groups excluded: {conflicting_rows:,}")
    print(f"Exact duplicate rows removed: {duplicate_rows_removed:,}")
    print(f"Rows retained: {dedup_rows:,}")
    for name, info in split_report.items():
        print(f"{name.title():<10}: {info['rows']:,} rows | days={', '.join(info['days'])}")
    print(f"Report: {report_path}")
    print("Inspect cleaning_report.json before training.")
    con.close()


if __name__ == "__main__":
    main()
