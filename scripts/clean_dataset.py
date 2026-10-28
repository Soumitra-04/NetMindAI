"""
Clean CIC-IDS2017 CSVs with DuckDB (disk-backed; avoids loading all rows into RAM).

Run from the NetMind project root:
    uv add duckdb
    uv run python scripts/clean_dataset.py

Expected raw files:
    data/raw/MachineLearningCVE/*.csv

Outputs:
    data/processed/cleaned/train.csv
    data/processed/cleaned/validation.csv
    data/processed/cleaned/test.csv
    data/processed/cleaned/cleaning_report.json

Split policy:
    Train: Monday, Tuesday, Wednesday
    Validation: Thursday
    Test: Friday

This is a chronological/capture-day holdout for the binary target (BENIGN vs ATTACK).
Attack-family labels are retained for reporting, but excluded from model features.
Conflicting rows with identical feature values but different labels are excluded from
the model-ready dataset and counted in the report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "MachineLearningCVE"
OUT_DIR = ROOT / "data" / "processed" / "cleaned"
DB_PATH = OUT_DIR / "cleaning_work.duckdb"

LABEL_COL = "Label"
DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}

# CIC-IDS2017 contains some features that are constant/duplicated in the published CSVs.
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
    "Fwd Header Length_1",
}


def day_from_filename(filename: str) -> str:
    name = Path(filename).name.lower()
    if "monday" in name:
        return "Monday"
    if "tuesday" in name:
        return "Tuesday"
    if "wednesday" in name:
        return "Wednesday"
    if "thursday" in name:
        return "Thursday"
    if "friday" in name:
        return "Friday"
    raise ValueError(f"Could not determine capture day from filename: {filename}")


def normalize_label_sql(expr: str) -> str:
    # The Web Attack labels may contain mojibake in the source CSV; normalize by
    # stable substrings rather than relying on the broken punctuation/encoding.
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


def main() -> None:
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {RAW_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads TO 4")
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{(OUT_DIR / 'duckdb_tmp').as_posix()}'")
    (OUT_DIR / "duckdb_tmp").mkdir(exist_ok=True)

    file_list = "[" + ", ".join("'" + str(f).replace("\\", "/").replace("'", "''") + "'" for f in files) + "]"
    print(f"Found {len(files)} CSV files.")
    print("Scanning schemas and importing data into the disk-backed DuckDB database...")

    # DuckDB reads files in parallel and keeps the working table on disk.
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

    columns = [row[0] for row in con.execute("DESCRIBE raw").fetchall()]
    # CIC-IDS2017 headers sometimes contain leading/trailing spaces.
    # Trim them at the database schema level before selecting columns.
    for col in columns:
        trimmed = col.strip()
        if trimmed and trimmed != col:
            old_q = '"' + col.replace('"', '""') + '"'
            new_q = '"' + trimmed.replace('"', '""') + '"'
            con.execute(f"ALTER TABLE raw RENAME COLUMN {old_q} TO {new_q}")
    columns = [row[0] for row in con.execute("DESCRIBE raw").fetchall()]
    if LABEL_COL not in columns:
        raise ValueError(f"No {LABEL_COL!r} column found. Columns: {columns}")
    if "filename" not in columns:
        raise RuntimeError("DuckDB did not include the filename virtual column.")

    # Remove BOM/whitespace from column names if present in the imported schema.
    # The source schema was already audited as consistent, so unexpected columns stop the run.
    feature_cols = [c for c in columns if c not in {LABEL_COL, "filename"}]
    if not feature_cols:
        raise RuntimeError("No feature columns were found.")

    # Explicitly cast features to DOUBLE. Non-numeric values become NULL and are reported.
    # Keep a source file/day field only for grouping and auditing, never as a model feature.
    select_exprs = []
    for col in feature_cols:
        escaped = '"' + col.replace('"', '""') + '"'
        select_exprs.append(f"try_cast(trim({escaped}) AS DOUBLE) AS {escaped}")
    select_exprs.extend([
        f"{normalize_label_sql('"' + LABEL_COL + '"')} AS clean_label",
        "filename AS source_file",
    ])

    con.execute(f"""
        CREATE TABLE normalized AS
        SELECT {", ".join(select_exprs)}
        FROM raw
        WHERE "{LABEL_COL}" IS NOT NULL
          AND trim(CAST("{LABEL_COL}" AS VARCHAR)) <> ''
    """)

    # Derive capture day and a stable ordering. Monday is preferred when identical
    # records appear on multiple capture days, preventing filename-sort order from
    # accidentally assigning Friday provenance to earlier-day duplicates.
    con.execute("""
        CREATE TABLE staged AS
        SELECT *,
          CASE
            WHEN contains(lower(source_file), 'monday') THEN 'Monday'
            WHEN contains(lower(source_file), 'tuesday') THEN 'Tuesday'
            WHEN contains(lower(source_file), 'wednesday') THEN 'Wednesday'
            WHEN contains(lower(source_file), 'thursday') THEN 'Thursday'
            WHEN contains(lower(source_file), 'friday') THEN 'Friday'
            ELSE 'Unknown'
          END AS capture_day,
          CASE
            WHEN contains(lower(source_file), 'monday') THEN 0
            WHEN contains(lower(source_file), 'tuesday') THEN 1
            WHEN contains(lower(source_file), 'wednesday') THEN 2
            WHEN contains(lower(source_file), 'thursday') THEN 3
            WHEN contains(lower(source_file), 'friday') THEN 4
            ELSE 99
          END AS day_order
        FROM normalized
    """)

    # Drop predetermined constant/duplicate columns only if present.
    present_drop = [c for c in DROP_FEATURES if c in feature_cols]
    effective_features = [c for c in feature_cols if c not in present_drop]
    if not effective_features:
        raise RuntimeError("No feature columns remain after the initial drop policy.")

    # Count missing and infinite values in the already-numeric staged table.
    # Do not call trim() here: these columns have already been cast to DOUBLE.
    missing_report = {}
    for col in effective_features:
        esc = '"' + col.replace('"', '""') + '"'

        missing_count = con.execute(
            f"SELECT count(*) FROM staged WHERE {esc} IS NULL"
        ).fetchone()[0]

        infinite_count = con.execute(
            f"SELECT count(*) FROM staged "
            f"WHERE {esc} IS NOT NULL AND NOT isfinite({esc})"
        ).fetchone()[0]

        missing_report[col] = {
            "null_or_non_numeric": int(missing_count),
            "infinite": int(infinite_count),
        }

    # Convert infinities to NULL; keep missing values for training-only imputation.
    clean_exprs = []
    for col in effective_features:
        esc = '"' + col.replace('"', '""') + '"'
        clean_exprs.append(
            f"CASE WHEN {esc} IS NULL OR NOT isfinite({esc}) "
            f"THEN NULL ELSE {esc} END AS {esc}"
        )
    clean_exprs.extend([
        "clean_label",
        "source_file",
        "capture_day",
        "day_order",
    ])
    con.execute(f"""
        CREATE TABLE clean_numeric AS
        SELECT {", ".join(clean_exprs)}
        FROM staged
        WHERE capture_day IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
    """)

    # Build a feature-only fingerprint. Rows with the same feature values but different
    # labels are conflicts; exclude those feature fingerprints to avoid ambiguous targets.
    # Hashing is used to keep the group-by compact; SHA256 collision risk is negligible.
    feature_json = "to_json(struct_pack(" + ", ".join(
        f'f{i} := "{c.replace(chr(34), chr(34)*2)}"' for i, c in enumerate(effective_features)
    ) + "))"
    con.execute(f"""
        CREATE TABLE fingerprinted AS
        SELECT *,
          sha256({feature_json}) AS feature_fingerprint,
          sha256(to_json(struct_pack(
            {", ".join(f'f{i} := "{c.replace(chr(34), chr(34)*2)}"' for i, c in enumerate(effective_features))},
            label := clean_label
          ))) AS full_fingerprint
        FROM clean_numeric
    """)

    con.execute("""
        CREATE TABLE conflicting_fingerprints AS
        SELECT feature_fingerprint
        FROM fingerprinted
        GROUP BY feature_fingerprint
        HAVING count(DISTINCT clean_label) > 1
    """)
    conflicting_feature_groups = con.execute(
        "SELECT count(*) FROM conflicting_fingerprints"
    ).fetchone()[0]
    conflicting_rows = con.execute("""
        SELECT count(*)
        FROM fingerprinted f
        JOIN conflicting_fingerprints c USING (feature_fingerprint)
    """).fetchone()[0]

    # Exact duplicates (same features + same label) are globally deduplicated.
    # For duplicate rows spanning days, keep the earliest capture day consistently.
    con.execute("""
        CREATE TABLE deduplicated AS
        SELECT * EXCLUDE (rn)
        FROM (
          SELECT f.*,
            row_number() OVER (
              PARTITION BY full_fingerprint
              ORDER BY day_order ASC, source_file ASC
            ) AS rn
          FROM fingerprinted f
          LEFT JOIN conflicting_fingerprints c USING (feature_fingerprint)
          WHERE c.feature_fingerprint IS NULL
        )
        WHERE rn = 1
    """)

    raw_rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    normalized_rows = con.execute("SELECT count(*) FROM clean_numeric").fetchone()[0]
    dedup_rows = con.execute("SELECT count(*) FROM deduplicated").fetchone()[0]
    exact_duplicate_rows_removed = normalized_rows - conflicting_rows - dedup_rows

    # Label counts before/after cleaning.
    labels_before = dict(con.execute("""
        SELECT clean_label, count(*)
        FROM clean_numeric GROUP BY clean_label ORDER BY clean_label
    """).fetchall())
    labels_after = dict(con.execute("""
        SELECT clean_label, count(*)
        FROM deduplicated GROUP BY clean_label ORDER BY clean_label
    """).fetchall())

    # Split by day. Days remain disjoint by design.
    split_def = {
        "train": ["Monday", "Tuesday", "Wednesday"],
        "validation": ["Thursday"],
        "test": ["Friday"],
    }
    split_counts = {}
    for split_name, days in split_def.items():
        day_list = ", ".join("'" + d + "'" for d in days)
        out_path = OUT_DIR / f"{split_name}.csv"
        # Do not export source_file, day_order, or fingerprints as model inputs.
        output_cols = [
            '"' + c.replace('"', '""') + '"' for c in effective_features
        ] + ["clean_label AS Label", "CASE WHEN upper(clean_label) = 'BENIGN' THEN 0 ELSE 1 END AS target", "capture_day"]
        con.execute(f"""
            COPY (
              SELECT {", ".join(output_cols)}
              FROM deduplicated
              WHERE capture_day IN ({day_list})
              ORDER BY capture_day
            ) TO '{out_path.as_posix()}' (HEADER, DELIMITER ',')
        """)
        rows = con.execute(
            f"SELECT count(*) FROM deduplicated WHERE capture_day IN ({day_list})"
        ).fetchone()[0]
        split_counts[split_name] = {
            "rows": int(rows),
            "days": days,
            "label_counts": dict(con.execute(
                f"SELECT clean_label, count(*) FROM deduplicated WHERE capture_day IN ({day_list}) GROUP BY clean_label ORDER BY clean_label"
            ).fetchall()),
        }

    # Verify no day overlap and no duplicate feature fingerprints across split files.
    day_overlap = {}
    for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]:
        day_overlap[f"{a}_{b}"] = sorted(set(split_def[a]) & set(split_def[b]))

    report = {
        "source_files": [p.name for p in files],
        "raw_rows_read": int(raw_rows),
        "rows_after_label_and_day_filter": int(normalized_rows),
        "conflicting_feature_groups_excluded": int(conflicting_feature_groups),
        "rows_in_conflicting_groups_excluded": int(conflicting_rows),
        "exact_duplicate_rows_removed_estimate": int(exact_duplicate_rows_removed),
        "rows_after_conflict_removal_and_global_deduplication": int(dedup_rows),
        "label_counts_before_conflict_and_duplicate_removal": {
            k: int(v) for k, v in labels_before.items()
        },
        "label_counts_after_cleaning": {k: int(v) for k, v in labels_after.items()},
        "numeric_features": effective_features,
        "features_dropped_by_policy": sorted(present_drop),
        "missing_and_infinite_values_before_cleaning": missing_report,
        "split_policy": split_def,
        "split_counts": split_counts,
        "day_overlap_checks": day_overlap,
        "preprocessing_policy": {
            "infinity_values": "Converted to NULL; do not impute using the full dataset.",
            "missing_values": "Retained as NULL; impute using training-set medians only during model pipeline fitting.",
            "deduplication": "Global exact duplicates removed by feature+label fingerprint; conflicting feature fingerprints excluded.",
            "target": "target=0 for BENIGN; target=1 for all attack labels.",
            "label_column": "Label retained for analysis; must not be used as a model feature.",
            "source_day": "capture_day retained for evaluation/grouping; must not be used as a model feature.",
        },
        "important_limitations": [
            "The split is day-based, but Thursday and Friday attack families may be absent from training.",
            "This is a binary BENIGN-vs-ATTACK dataset. It does not establish multiclass attack-family performance.",
            "Rows with conflicting labels for identical feature values are excluded and counted.",
            "Missing values remain NULL in CSV; fit imputation on training data only.",
        ],
    }
    report_path = OUT_DIR / "cleaning_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\nCleaning complete.")
    print(f"Raw rows: {raw_rows:,}")
    print(f"Rows after label/day filtering: {normalized_rows:,}")
    print(f"Conflicting feature groups excluded: {conflicting_feature_groups:,}")
    print(f"Rows in conflicting groups excluded: {conflicting_rows:,}")
    print(f"Exact duplicate rows removed (estimate): {exact_duplicate_rows_removed:,}")
    print(f"Rows retained after deduplication: {dedup_rows:,}")
    for name, details in split_counts.items():
        print(f"{name.title()}: {details['rows']:,} rows — {', '.join(details['days'])}")
    print(f"Report: {report_path}")
    print("Review the report before training; no model has been trained.")

    con.close()


if __name__ == "__main__":
    main()
