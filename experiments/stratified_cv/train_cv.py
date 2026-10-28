#!/usr/bin/env python
"""
Stratified 5-fold CV experiment for NetMind.

Run from D:\\NetMind:
    uv run python experiments/stratified_cv/train_cv.py

Optional:
    uv run python experiments/stratified_cv/train_cv.py --models rf
    uv run python experiments/stratified_cv/train_cv.py --folds 3 --n-estimators 60

Important:
- Uses ONLY the existing cleaned training CSV.
- Stratifies by original Label (attack family), not only binary target, so each fold
  preserves attack-family proportions as far as possible.
- Does not alter the existing model, validation/test CSVs, or baseline reports.
- This is binary benign-vs-attack classification; Label is used for stratification
  and diagnostics only, never as a model feature.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "cleaned_final" / "train.csv"
BASELINE_BUNDLE = ROOT / "models" / "baseline_random_forest.joblib"
OUT_DIR = ROOT / "experiments" / "stratified_cv"


def make_model(name: str, n_estimators: int, random_state: int):
    common = dict(
        n_estimators=n_estimators,
        max_depth=24,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced_subsample" if name == "random_forest" else "balanced",
        n_jobs=-1,
        random_state=random_state,
        verbose=0,
    )
    if name == "random_forest":
        return RandomForestClassifier(**common)
    if name == "extra_trees":
        # ExtraTreesClassifier supports class_weight="balanced", not
        # "balanced_subsample".
        return ExtraTreesClassifier(**common)
    raise ValueError(f"Unknown model: {name}")


def metrics_at_threshold(y_true, scores, threshold=0.5):
    pred = scores >= threshold
    tp = int(np.sum((y_true == 1) & pred))
    fp = int(np.sum((y_true == 0) & pred))
    fn = int(np.sum((y_true == 1) & ~pred))
    tn = int(np.sum((y_true == 0) & ~pred))
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "pr_auc_average_precision": float(average_precision_score(y_true, scores)),
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
    }


def summarize(rows, keys):
    summary = {}
    for key in keys:
        values = np.asarray([row[key] for row in rows], dtype=np.float64)
        summary[key] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "fold_values": [float(v) for v in values],
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=80)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["rf", "et"],
        default=["rf", "et"],
        help="rf=Random Forest, et=Extra Trees",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.folds < 2:
        parser.error("--folds must be at least 2")
    if args.n_estimators < 1:
        parser.error("--n-estimators must be at least 1")
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Training data not found: {DATA_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading training data only: {DATA_PATH}", flush=True)
    start = time.time()
    df = pd.read_csv(DATA_PATH, low_memory=False)
    required = {"Label", "target", "capture_day"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Training CSV missing expected columns: {sorted(missing)}")

    # Prefer the exact feature order used by the existing baseline bundle.
    if BASELINE_BUNDLE.exists():
        bundle = joblib.load(BASELINE_BUNDLE)
        feature_columns = bundle.get("feature_columns")
        if not feature_columns:
            raise ValueError("Existing baseline bundle has no feature_columns.")
        missing_features = sorted(set(feature_columns) - set(df.columns))
        if missing_features:
            raise ValueError(f"Training data missing baseline features: {missing_features}")
    else:
        feature_columns = [
            c for c in df.columns if c not in {"Label", "target", "capture_day"}
        ]

    # Float32 reduces feature-matrix memory use. Labels are not passed to the model.
    X = df.loc[:, feature_columns].to_numpy(dtype=np.float32, copy=True)
    y = pd.to_numeric(df["target"], errors="raise").to_numpy(dtype=np.uint8)
    strata = df["Label"].astype(str).to_numpy()
    del df

    if not np.isin(y, [0, 1]).all():
        raise ValueError("target must contain only 0 and 1")
    family_counts = pd.Series(strata).value_counts()
    if family_counts.min() < args.folds:
        raise ValueError(
            f"Cannot use {args.folds}-fold stratification by Label: "
            f"smallest label group has {family_counts.min()} rows."
        )

    print(f"Rows: {len(y):,} | Features: {X.shape[1]} | Folds: {args.folds}", flush=True)
    print(f"Benign: {int(np.sum(y == 0)):,} | Attack: {int(np.sum(y == 1)):,}", flush=True)
    print("Stratifying by Label (attack family); Label is NOT a feature.", flush=True)
    print("Fold models use 0.5 as the fixed diagnostic threshold; no threshold tuning.", flush=True)

    cv = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    splits = list(cv.split(X, strata))
    results = {
        "experiment": "stratified_k_fold_known_training_attack_families",
        "data_path": str(DATA_PATH),
        "rows": int(len(y)),
        "feature_count": int(X.shape[1]),
        "features": list(feature_columns),
        "folds": int(args.folds),
        "n_estimators": int(args.n_estimators),
        "seed": int(args.seed),
        "stratification_column": "Label",
        "model_input_excludes": ["Label", "target", "capture_day"],
        "threshold": 0.5,
        "notes": [
            "Only the existing training CSV was used.",
            "Validation and test CSVs were not loaded or used.",
            "Label was used only to stratify folds and was excluded from model inputs.",
            "Metrics use a fixed 0.5 threshold; threshold selection is a separate validation-only step.",
            "This experiment estimates performance on attack families represented in the training pool; it does not measure unseen-family generalization.",
        ],
        "models": {},
    }

    metric_keys = [
        "precision", "recall", "f1", "pr_auc_average_precision",
        "roc_auc", "false_positive_rate",
    ]
    for short_name in args.models:
        model_name = "random_forest" if short_name == "rf" else "extra_trees"
        fold_rows = []
        print(f"\n=== {model_name} ===", flush=True)
        model_start = time.time()
        for fold_idx, (train_idx, val_idx) in enumerate(splits, start=1):
            fold_start = time.time()
            model = make_model(model_name, args.n_estimators, args.seed + fold_idx)
            print(
                f"Fold {fold_idx}/{args.folds}: fitting on {len(train_idx):,} rows; "
                f"scoring {len(val_idx):,} rows...",
                flush=True,
            )
            model.fit(X[train_idx], y[train_idx])
            scores = model.predict_proba(X[val_idx])[:, 1]
            row = metrics_at_threshold(y[val_idx], scores, threshold=0.5)
            row.update({
                "fold": fold_idx,
                "train_rows": int(len(train_idx)),
                "validation_rows": int(len(val_idx)),
                "validation_attack_rows": int(np.sum(y[val_idx] == 1)),
                "validation_benign_rows": int(np.sum(y[val_idx] == 0)),
                "elapsed_seconds": round(time.time() - fold_start, 2),
            })
            fold_rows.append(row)
            print(
                f"  precision={row['precision']:.4f} recall={row['recall']:.4f} "
                f"F1={row['f1']:.4f} PR-AUC={row['pr_auc_average_precision']:.4f} "
                f"({row['elapsed_seconds']:.1f}s)",
                flush=True,
            )
            del model, scores

        results["models"][model_name] = {
            "folds": fold_rows,
            "summary": summarize(fold_rows, metric_keys),
            "elapsed_seconds": round(time.time() - model_start, 2),
        }
        print("Mean ± standard deviation:", flush=True)
        for key in metric_keys:
            entry = results["models"][model_name]["summary"][key]
            print(f"  {key}: {entry['mean']:.4f} ± {entry['std']:.4f}", flush=True)

    results["elapsed_seconds"] = round(time.time() - start, 2)
    json_path = OUT_DIR / "cv_results.json"
    csv_path = OUT_DIR / "cv_results.csv"
    json_path.write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")
    flat_rows = []
    for model_name, model_result in results["models"].items():
        for row in model_result["folds"]:
            flat_rows.append({"model": model_name, **row})
    pd.DataFrame(flat_rows).to_csv(csv_path, index=False)

    print("\nCross-validation complete.", flush=True)
    print(f"JSON: {json_path}", flush=True)
    print(f"CSV:  {csv_path}", flush=True)
    print(f"Elapsed: {results['elapsed_seconds']:.1f}s", flush=True)
    print("No existing model, validation data, test data, or baseline report was changed.", flush=True)


if __name__ == "__main__":
    main()
