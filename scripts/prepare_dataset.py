
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "MachineLearningCVE"
OUT_DIR = ROOT / "data" / "processed"

RANDOM_STATE = 42
SAMPLE_SIZE = 300_000
CHUNK_SIZE = 50_000
LABEL_COL = "Label"

# Exclude known constant features in this dataset and a duplicated header feature.
KNOWN_CONSTANTS = {
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
}

DROP_FEATURES = KNOWN_CONSTANTS | {"Fwd Header Length.1"}


def normalize_columns(columns):
    return [str(c).strip() for c in columns]


def normalize_label(value):
    if pd.isna(value):
        return None

    label = str(value).strip()
    if not label:
        return None

    # Normalize common Web Attack label variants without changing the class.
    lowered = label.lower()
    if "web attack" in lowered and "brute force" in lowered:
        return "Web Attack - Brute Force"
    if "web attack" in lowered and "xss" in lowered:
        return "Web Attack - XSS"
    if "web attack" in lowered and (
        "sql injection" in lowered or "sql" in lowered
    ):
        return "Web Attack - SQL Injection"

    return label


def read_chunk(path, columns):
    chunk = pd.read_csv(
        path,
        chunksize=CHUNK_SIZE,
        encoding="utf-8-sig",
        low_memory=False,
    )
    return chunk


def main():
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {RAW_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    reference_columns = None
    label_counts = {}
    missing_labels = 0
    sampled_parts = []
    total_rows = 0
    feature_missing = {}
    seen_schema_files = []

    # Reservoir-style sampling: keep a random bounded sample while streaming.
    rng = np.random.default_rng(RANDOM_STATE)
    reservoir = None
    seen = 0

    for path in files:
        print(f"Reading {path.name} ...")

        header = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
        columns = normalize_columns(header.columns)

        if LABEL_COL not in columns:
            raise ValueError(f"{path.name} has no {LABEL_COL!r} column")

        if reference_columns is None:
            reference_columns = columns
        elif columns != reference_columns:
            raise ValueError(
                f"Schema mismatch in {path.name}; inspect column names before proceeding."
            )

        seen_schema_files.append(path.name)

        for chunk in pd.read_csv(
            path,
            chunksize=CHUNK_SIZE,
            encoding="utf-8-sig",
            low_memory=False,
        ):
            chunk.columns = normalize_columns(chunk.columns)
            chunk[LABEL_COL] = chunk[LABEL_COL].map(normalize_label)

            missing_labels += int(chunk[LABEL_COL].isna().sum())
            chunk = chunk.dropna(subset=[LABEL_COL])
            if chunk.empty:
                continue

            labels = chunk[LABEL_COL].value_counts()
            for label, count in labels.items():
                label_counts[label] = label_counts.get(label, 0) + int(count)

            # Binary target: BENIGN=0; all attack classes=1.
            chunk["target"] = (chunk[LABEL_COL].str.upper() != "BENIGN").astype("int8")

            # Drop columns excluded by the initial schema review.
            drop_now = [c for c in DROP_FEATURES if c in chunk.columns]
            chunk = chunk.drop(columns=drop_now)

            # Convert feature columns to numeric; unexpected text becomes NaN.
            feature_cols = [
                c for c in chunk.columns if c not in {LABEL_COL, "target"}
            ]
            for col in feature_cols:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

            chunk[feature_cols] = chunk[feature_cols].replace(
                [np.inf, -np.inf], np.nan
            )

            for col in feature_cols:
                n_missing = int(chunk[col].isna().sum())
                feature_missing[col] = feature_missing.get(col, 0) + n_missing

            total_rows += len(chunk)

            # Reservoir sampling over rows, preserving class proportions approximately.
            records = chunk[feature_cols + ["target", LABEL_COL]].to_dict("records")
            if reservoir is None:
                reservoir = []
            for record in records:
                seen += 1
                if len(reservoir) < SAMPLE_SIZE:
                    reservoir.append(record)
                else:
                    j = int(rng.integers(0, seen))
                    if j < SAMPLE_SIZE:
                        reservoir[j] = record

    if not reservoir:
        raise ValueError("No valid records found.")

    sampled = pd.DataFrame(reservoir)
    sampled = sampled.replace([np.inf, -np.inf], np.nan)

    # Remove features that are constant in the sample, except the target/labels.
    feature_cols = [
        c for c in sampled.columns if c not in {"target", LABEL_COL}
    ]
    constant_features = [
        c for c in feature_cols if sampled[c].nunique(dropna=True) <= 1
    ]
    sampled = sampled.drop(columns=constant_features)
    feature_cols = [
        c for c in sampled.columns if c not in {"target", LABEL_COL}
    ]

    # Save raw prepared sample and a fixed stratified train/test split.
    train, test = train_test_split(
        sampled,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=sampled["target"],
    )

    train.to_csv(OUT_DIR / "train.csv", index=False)
    test.to_csv(OUT_DIR / "test.csv", index=False)

    report = {
        "source_files": seen_schema_files,
        "total_rows_read": total_rows,
        "sample_size": len(sampled),
        "random_state": RANDOM_STATE,
        "test_size": 0.20,
        "missing_labels_dropped": missing_labels,
        "original_label_counts": label_counts,
        "binary_sample_counts": {
            "normal": int((sampled["target"] == 0).sum()),
            "attack": int((sampled["target"] == 1).sum()),
        },
        "features_retained": feature_cols,
        "features_dropped_by_initial_policy": sorted(
            c for c in DROP_FEATURES if c in reference_columns
        ),
        "constant_features_dropped_in_sample": constant_features,
        "missing_values_by_feature_across_source": feature_missing,
        "duplicates": (
            "Not removed in this preparation stage; evaluate duplication "
            "before finalizing the training split."
        ),
        "notes": [
            "Original CSV files are not modified.",
            "Sampling is bounded-memory reservoir sampling.",
            "The split is stratified by binary target, not grouped by capture day.",
            "Do not use this random-split result as proof of generalization to unseen days.",
        ],
    }

    (OUT_DIR / "preparation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nPreparation complete.")
    print(f"Rows scanned: {total_rows:,}")
    print(f"Sample rows: {len(sampled):,}")
    print(f"Features retained: {len(feature_cols)}")
    print(f"Train rows: {len(train):,}")
    print(f"Test rows: {len(test):,}")
    print(f"Output directory: {OUT_DIR}")
    print("Review preparation_report.json before training.")


if __name__ == "__main__":
    main()
