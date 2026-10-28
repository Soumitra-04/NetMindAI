#!/usr/bin/env python
"""
Capture-day generalization experiment for NetMind.

Run from D:\\NetMind:
    uv run python experiments/stratified_cv/day_holdout.py

This evaluates the existing trained Random Forest without retraining it. Each run
holds out one capture day from the already-cleaned training pool and trains on the
other available days, then evaluates on the held-out day. Because the model is
already trained on Monday/Tuesday/Wednesday, this script trains fresh models for
the day-holdout experiment. It uses only the existing train.csv; validation/test
sets are untouched.

IMPORTANT INTERPRETATION:
- Attack families are not evenly distributed across days. If an attack family
  exists only on a held-out day, it is unseen during that fold's training.
- Metrics are reported both overall and by attack family.
- For each day, this experiment evaluates only the rows from that day that are
  present in the existing training CSV. It cannot evaluate days absent from that
  CSV (e.g. Thursday/Friday).
- This is a grouped/day generalization check, not a replacement for final test.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "cleaned_final" / "train.csv"
BASELINE_PATH = ROOT / "models" / "baseline_random_forest.joblib"
OUT_DIR = ROOT / "experiments" / "stratified_cv"


def calc_metrics(y, scores, threshold=0.5):
    pred = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "pr_auc_average_precision": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)) if len(np.unique(y)) == 2 else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "support_benign": int(np.sum(y == 0)),
        "support_attack": int(np.sum(y == 1)),
    }


def make_rf(n_estimators, random_state):
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=24,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=random_state,
        verbose=0,
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-estimators", type=int, default=80)
    parser.add_argument("--days", nargs="+", default=None,
                        help="Optional subset of days to hold out, e.g. --days Monday Tuesday")
    args = parser.parse_args()

    if args.n_estimators < 1:
        parser.error("--n-estimators must be at least 1")
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Training CSV not found: {DATA_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading: {DATA_PATH}", flush=True)
    started = time.time()
    df = pd.read_csv(DATA_PATH, low_memory=False)

    metadata = {"Label", "target", "capture_day"}
    missing = metadata - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    if BASELINE_PATH.exists():
        bundle = joblib.load(BASELINE_PATH)
        feature_cols = bundle.get("feature_columns")
        if not feature_cols:
            raise ValueError("Baseline model bundle has no feature_columns.")
    else:
        feature_cols = [c for c in df.columns if c not in metadata]

    missing_features = sorted(set(feature_cols) - set(df.columns))
    if missing_features:
        raise ValueError(f"Missing model features: {missing_features}")

    # Use the same feature order as the saved baseline. The baseline's saved
    # threshold is recorded for reference; day-holdout metrics use 0.5 uniformly.
    saved_threshold = float(bundle.get("threshold", 0.306)) if BASELINE_PATH.exists() else 0.306
    X = df.loc[:, feature_cols].to_numpy(dtype=np.float32, copy=True)
    y = pd.to_numeric(df["target"], errors="raise").to_numpy(dtype=np.uint8)
    labels = df["Label"].astype(str).to_numpy()
    days = df["capture_day"].astype(str).to_numpy()
    del df

    unique_days = list(pd.unique(days))
    if args.days:
        unknown = sorted(set(args.days) - set(unique_days))
        if unknown:
            raise ValueError(f"Requested days absent from training CSV: {unknown}. Available: {unique_days}")
        holdout_days = args.days
    else:
        holdout_days = unique_days

    results = {
        "experiment": "capture_day_holdout_on_existing_training_pool",
        "data_path": str(DATA_PATH),
        "rows": int(len(y)),
        "feature_count": int(len(feature_cols)),
        "n_estimators": int(args.n_estimators),
        "days_available": unique_days,
        "days_held_out": holdout_days,
        "saved_baseline_threshold_reference_only": saved_threshold,
        "evaluation_threshold": 0.5,
        "notes": [
            "Only the existing cleaned training CSV was used.",
            "Validation and test CSVs were not loaded or used.",
            "Fresh Random Forest models were fit for each day-holdout run.",
            "Metrics use a fixed 0.5 threshold for consistency; no threshold tuning was performed.",
            "Attack families absent from a fold's training days are unseen in that fold.",
            "This does not evaluate Thursday/Friday rows because they are absent from the training CSV.",
        ],
        "runs": [],
    }

    for run_idx, day in enumerate(holdout_days, start=1):
        test_mask = days == day
        train_mask = ~test_mask
        y_train, y_holdout = y[train_mask], y[test_mask]
        holdout_labels = labels[test_mask]
        print(
            f"\n[{run_idx}/{len(holdout_days)}] Holdout day: {day} | "
            f"train={int(train_mask.sum()):,} rows | holdout={int(test_mask.sum()):,} rows",
            flush=True,
        )
        if len(np.unique(y_train)) < 2 or len(np.unique(y_holdout)) < 2:
            print("  WARNING: train or holdout has only one binary class; some metrics may be unavailable.", flush=True)

        run_started = time.time()
        model = make_rf(args.n_estimators, 100 + run_idx)
        model.fit(X[train_mask], y_train)
        scores = model.predict_proba(X[test_mask])[:, 1]
        overall = calc_metrics(y_holdout, scores)

        family_metrics = []
        for family in sorted(np.unique(holdout_labels)):
            fam_mask = holdout_labels == family
            fam_y = y_holdout[fam_mask]
            fam_scores = scores[fam_mask]
            fam_pred = fam_scores >= 0.5
            attack_mask = fam_y == 1
            n_attack = int(np.sum(attack_mask))
            family_metrics.append({
                "label": str(family),
                "rows": int(fam_mask.sum()),
                "attack_rows": n_attack,
                "attack_detected": int(np.sum(fam_pred & attack_mask)),
                "attack_missed": int(np.sum(~fam_pred & attack_mask)),
                "attack_recall": float(np.mean(fam_pred[attack_mask])) if n_attack else None,
                "median_attack_score": float(np.median(fam_scores[attack_mask])) if n_attack else None,
                "median_all_score": float(np.median(fam_scores)),
            })

        trained_families = sorted(set(labels[train_mask]) - {"BENIGN"})
        heldout_attack_families = sorted(set(holdout_labels) - {"BENIGN"})
        unseen_families = sorted(set(heldout_attack_families) - set(trained_families))
        run_result = {
            "held_out_day": str(day),
            "train_rows": int(train_mask.sum()),
            "holdout_rows": int(test_mask.sum()),
            "train_attack_families": trained_families,
            "holdout_attack_families": heldout_attack_families,
            "attack_families_unseen_in_training": unseen_families,
            "overall_metrics": overall,
            "per_family": family_metrics,
            "elapsed_seconds": round(time.time() - run_started, 2),
        }
        results["runs"].append(run_result)
        print(
            f"  F1={overall['f1']:.4f} precision={overall['precision']:.4f} "
            f"recall={overall['recall']:.4f} PR-AUC={overall['pr_auc_average_precision']:.4f}",
            flush=True,
        )
        if unseen_families:
            print(f"  Unseen attack families in holdout: {', '.join(unseen_families)}", flush=True)
        for row in family_metrics:
            if row["attack_rows"]:
                print(
                    f"    {row['label']}: recall={row['attack_recall']:.4f} "
                    f"({row['attack_detected']}/{row['attack_rows']} detected), "
                    f"median score={row['median_attack_score']:.4f}",
                    flush=True,
                )
        del model, scores

    results["elapsed_seconds"] = round(time.time() - started, 2)
    json_path = OUT_DIR / "day_holdout_results.json"
    txt_path = OUT_DIR / "day_holdout_results.txt"
    json_path.write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")

    lines = [
        "NETMIND CAPTURE-DAY HOLDOUT EXPERIMENT",
        "=" * 39,
        f"Rows: {len(y):,} | features: {len(feature_cols)} | trees per run: {args.n_estimators}",
        "Evaluation threshold: 0.5",
        "",
    ]
    for run in results["runs"]:
        m = run["overall_metrics"]
        lines += [
            f"HOLDOUT DAY: {run['held_out_day']}",
            "-" * (12 + len(run["held_out_day"])),
            f"Train rows: {run['train_rows']:,} | holdout rows: {run['holdout_rows']:,}",
            f"Precision={m['precision']:.4f} Recall={m['recall']:.4f} F1={m['f1']:.4f} "
            f"PR-AUC={m['pr_auc_average_precision']:.4f} ROC-AUC={m['roc_auc'] if m['roc_auc'] is not None else 'N/A'}",
            f"TN={m['tn']:,} FP={m['fp']:,} FN={m['fn']:,} TP={m['tp']:,}",
            f"Attack families unseen in training: {run['attack_families_unseen_in_training']}",
            "Per-family attack recall:",
        ]
        for fam in run["per_family"]:
            if fam["attack_rows"]:
                lines.append(
                    f"  {fam['label']}: {fam['attack_recall']:.4f} "
                    f"({fam['attack_detected']}/{fam['attack_rows']}) "
                    f"median_score={fam['median_attack_score']:.4f}"
                )
        lines.append("")

    lines += [
        "INTERPRETATION NOTE",
        "-------------------",
        "A low score on a held-out day can reflect both day shift and missing attack families.",
        "A high score does not prove generalization to Thursday/Friday, which are not in this training CSV.",
        f"Elapsed: {results['elapsed_seconds']:.1f}s",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nDay-holdout experiment complete.", flush=True)
    print(f"Text report: {txt_path}", flush=True)
    print(f"JSON report: {json_path}", flush=True)
    print(f"Elapsed: {results['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
