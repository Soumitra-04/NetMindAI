#!/usr/bin/env python
"""
Audit NetMind's unusually high Stratified K-Fold results.

Run from D:\\NetMind:
    uv run python experiments/stratified_cv/audit_cv.py

This is diagnostic only. It does not train models, modify datasets, or alter the
existing baseline/CV outputs. It checks:
- feature-vector overlap between CV folds using the fold assignment implied by
  the same StratifiedKFold configuration (no model fitting required);
- exact feature-vector duplicates within the training dataset;
- conflicting labels for identical feature vectors;
- target/label consistency and metadata leakage risks;
- class/family counts by fold;
- feature importance from the saved baseline model, if available.

Important: the script's fold overlap check is based on the same fold assignment
rule (StratifiedKFold(shuffle=True, random_state=42), stratified by Label) used
by train_cv.py. It does not prove independence of correlated or near-duplicate
flows, and it does not establish the cause of the test performance gap.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "cleaned_final" / "train.csv"
BASELINE_PATH = ROOT / "models" / "baseline_random_forest.joblib"
OUT_DIR = ROOT / "experiments" / "stratified_cv"
SEED = 42
N_SPLITS = 5


def json_safe(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        val = float(value)
        return val if np.isfinite(val) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def main():
    started = time.time()
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Training CSV not found: {DATA_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading training data: {DATA_PATH}", flush=True)
    # Need feature columns for duplicate/conflict checks, so read the full CSV.
    df = pd.read_csv(DATA_PATH, low_memory=False)
    metadata_cols = {"Label", "target", "capture_day"}
    feature_cols = [c for c in df.columns if c not in metadata_cols]
    if not feature_cols:
        raise ValueError("No model feature columns found.")
    missing = metadata_cols - set(df.columns)
    if missing:
        raise ValueError(f"Expected metadata columns missing: {sorted(missing)}")

    labels = df["Label"].astype(str)
    target = pd.to_numeric(df["target"], errors="raise").astype(np.uint8)
    capture_day = df["capture_day"].astype(str)
    if not target.isin([0, 1]).all():
        raise ValueError("target contains values outside 0/1.")

    # Verify mapping consistency: BENIGN -> 0; every non-BENIGN label -> 1.
    expected_target = (labels != "BENIGN").astype(np.uint8)
    inconsistent = int((target.to_numpy() != expected_target.to_numpy()).sum())

    print(f"Rows: {len(df):,} | features: {len(feature_cols)}", flush=True)
    print("Checking duplicate feature vectors (this may take a few minutes)...", flush=True)

    # Hash the feature vectors in chunks to keep peak memory moderate. Hashes are
    # used to screen exact equality; representative duplicate groups are then
    # checked with actual feature values for label conflicts.
    feature_frame = df.loc[:, feature_cols]
    row_hash = pd.util.hash_pandas_object(feature_frame, index=False, categorize=True).to_numpy(dtype=np.uint64)
    duplicate_hash_mask = pd.Series(row_hash).duplicated(keep=False).to_numpy()
    duplicated_rows = int(duplicate_hash_mask.sum())
    unique_hash_count = int(pd.Series(row_hash).nunique())

    # Hash collision is extremely unlikely, but use full feature-row grouping on
    # the candidate duplicates to establish exact duplicate/conflict counts.
    duplicate_positions = np.flatnonzero(duplicate_hash_mask)
    exact_duplicate_groups = 0
    conflicting_groups = 0
    conflicting_rows = 0
    duplicate_groups_examined = 0
    if len(duplicate_positions):
        candidate = feature_frame.iloc[duplicate_positions].copy()
        candidate["_row_hash_"] = row_hash[duplicate_positions]
        candidate["_label_"] = labels.iloc[duplicate_positions].to_numpy()
        # Group by hash then compare the feature columns in each group, guarding
        # against a theoretical hash collision.
        for _, group in candidate.groupby("_row_hash_", sort=False):
            if len(group) < 2:
                continue
            values = group[feature_cols]
            # duplicated() uses exact pandas value equality for rows.
            exact_mask = values.duplicated(keep=False)
            if not exact_mask.any():
                continue
            exact = group.loc[exact_mask]
            exact_duplicate_groups += 1
            duplicate_groups_examined += 1
            if exact["_label_"].nunique(dropna=False) > 1:
                conflicting_groups += 1
                conflicting_rows += int(len(exact))
        del candidate

    # Recreate fold assignment matching train_cv.py.
    family_counts = labels.value_counts()
    if family_counts.min() < N_SPLITS:
        raise ValueError(f"Smallest label group has {family_counts.min()} rows, below {N_SPLITS} folds.")
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    fold_id = np.full(len(df), -1, dtype=np.int8)
    X_dummy = np.zeros((len(df), 1), dtype=np.uint8)
    for fold_number, (_, val_idx) in enumerate(cv.split(X_dummy, labels), start=1):
        fold_id[val_idx] = fold_number

    # For every exact duplicate group, determine if its rows cross fold boundaries.
    # Hash-based screening followed by feature equality checks.
    print("Checking whether exact duplicate vectors cross folds...", flush=True)
    fold_crossing_duplicate_groups = 0
    fold_crossing_duplicate_rows = 0
    cross_fold_conflict_groups = 0
    cross_fold_conflict_rows = 0
    if len(duplicate_positions):
        candidate = feature_frame.iloc[duplicate_positions].copy()
        candidate["_row_hash_"] = row_hash[duplicate_positions]
        candidate["_label_"] = labels.iloc[duplicate_positions].to_numpy()
        candidate["_fold_"] = fold_id[duplicate_positions]
        for _, group in candidate.groupby("_row_hash_", sort=False):
            if len(group) < 2:
                continue
            exact_mask = group[feature_cols].duplicated(keep=False)
            if not exact_mask.any():
                continue
            exact = group.loc[exact_mask]
            if exact["_fold_"].nunique() > 1:
                fold_crossing_duplicate_groups += 1
                fold_crossing_duplicate_rows += int(len(exact))
                if exact["_label_"].nunique(dropna=False) > 1:
                    cross_fold_conflict_groups += 1
                    cross_fold_conflict_rows += int(len(exact))

    # Family counts by fold and capture-day counts by fold.
    family_fold_counts = pd.crosstab(labels, fold_id).rename_axis(index="Label", columns="fold")
    day_fold_counts = pd.crosstab(capture_day, fold_id).rename_axis(index="capture_day", columns="fold")
    family_fold_counts.index.name = "Label"
    day_fold_counts.index.name = "capture_day"

    # Feature importance from the existing baseline, if bundle schema supports it.
    top_features = []
    baseline_note = "Existing baseline bundle not found; skipped feature importance."
    if BASELINE_PATH.exists():
        bundle = joblib.load(BASELINE_PATH)
        model = bundle.get("model") if isinstance(bundle, dict) else None
        saved_features = bundle.get("feature_columns", []) if isinstance(bundle, dict) else []
        if model is not None and hasattr(model, "feature_importances_") and len(saved_features) == len(model.feature_importances_):
            order = np.argsort(model.feature_importances_)[::-1][:20]
            top_features = [
                {"feature": str(saved_features[i]), "importance": float(model.feature_importances_[i])}
                for i in order
            ]
            baseline_note = "Top importances extracted from the saved baseline model; these are associations, not proof of leakage."
        else:
            baseline_note = "Baseline bundle found but its model/schema did not expose matching feature_importances_."

    report = {
        "audit": "stratified_cv_integrity_and_generalization_gap",
        "data_path": str(DATA_PATH),
        "rows": int(len(df)),
        "feature_count": int(len(feature_cols)),
        "features": feature_cols,
        "cv_reproduction": {
            "method": "StratifiedKFold",
            "n_splits": N_SPLITS,
            "shuffle": True,
            "random_state": SEED,
            "stratification_column": "Label",
        },
        "target_consistency": {
            "rows_inconsistent_with_BENIGN_vs_attack_mapping": inconsistent,
            "mapping_rule": "Label == BENIGN -> target 0; otherwise target 1",
        },
        "exact_duplicate_audit": {
            "rows_part_of_duplicate_hash_groups": duplicated_rows,
            "unique_feature_row_hashes": unique_hash_count,
            "candidate_duplicate_groups_exactly_examined": duplicate_groups_examined,
            "exact_duplicate_groups_within_training_pool": exact_duplicate_groups,
            "conflicting_label_groups_within_training_pool": conflicting_groups,
            "rows_in_conflicting_label_groups": conflicting_rows,
            "exact_duplicate_groups_crossing_cv_folds": fold_crossing_duplicate_groups,
            "rows_in_duplicate_groups_crossing_cv_folds": fold_crossing_duplicate_rows,
            "conflicting_label_groups_crossing_cv_folds": cross_fold_conflict_groups,
            "rows_in_cross_fold_conflicting_groups": cross_fold_conflict_rows,
            "note": "Hashing is a candidate-screening step; candidate duplicate rows are compared by actual feature values before being counted.",
        },
        "label_counts_by_fold": family_fold_counts.to_dict(),
        "capture_day_counts_by_fold": day_fold_counts.to_dict(),
        "top_baseline_feature_importances": top_features,
        "feature_importance_note": baseline_note,
        "limitations": [
            "Exact duplicate checks do not detect near-duplicates or correlated flows.",
            "Random stratified folds can mix capture days and related traffic sessions.",
            "This audit does not prove why the original test score differs from CV.",
            "The original test split contains attack families absent from the training pool; this audit does not train or test on those families.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    json_path = OUT_DIR / "audit_results.json"
    txt_path = OUT_DIR / "audit_results.txt"
    json_path.write_text(json.dumps(json_safe(report), indent=2, allow_nan=False), encoding="utf-8")

    lines = [
        "NETMIND STRATIFIED CV AUDIT",
        "=" * 29,
        f"Rows: {len(df):,}",
        f"Features: {len(feature_cols)}",
        f"Target mapping inconsistencies: {inconsistent}",
        "",
        "EXACT DUPLICATE AUDIT",
        "-" * 21,
        f"Rows in duplicate hash groups: {duplicated_rows:,}",
        f"Exact duplicate groups in training pool: {exact_duplicate_groups:,}",
        f"Conflicting-label duplicate groups: {conflicting_groups:,}",
        f"Exact duplicate groups crossing CV folds: {fold_crossing_duplicate_groups:,}",
        f"Rows in duplicate groups crossing folds: {fold_crossing_duplicate_rows:,}",
        f"Conflicting-label groups crossing folds: {cross_fold_conflict_groups:,}",
        "",
        "LABEL COUNTS BY FOLD",
        "-" * 20,
        family_fold_counts.to_string(),
        "",
        "CAPTURE-DAY COUNTS BY FOLD",
        "-" * 25,
        day_fold_counts.to_string(),
        "",
        "TOP BASELINE FEATURE IMPORTANCES",
        "-" * 32,
    ]
    if top_features:
        lines += [f"{x['feature']}: {x['importance']:.6f}" for x in top_features]
    else:
        lines.append(baseline_note)
    lines += [
        "",
        "INTERPRETATION",
        "-" * 14,
        "Near-perfect random-fold metrics may reflect strong separability on these data,",
        "but can be optimistic when correlated flows or capture sessions cross folds.",
        "Compare these results with a day/group-aware evaluation before claiming generalization.",
        "",
        f"Elapsed: {report['elapsed_seconds']:.1f} seconds",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\nAudit complete.", flush=True)
    print(f"Text report: {txt_path}", flush=True)
    print(f"JSON report: {json_path}", flush=True)
    print(f"Elapsed: {report['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
