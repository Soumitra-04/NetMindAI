"""
NetMind baseline binary intrusion classifier.

Run from project root:
    uv run python scripts/train_baseline.py

Inputs:
    data/processed/cleaned_final/train.csv
    data/processed/cleaned_final/validation.csv
    data/processed/cleaned_final/test.csv

Outputs:
    models/baseline_random_forest.joblib
    reports/baseline_metrics.json
    reports/baseline_metrics.txt
    reports/baseline_confusion_matrix.png
    reports/baseline_precision_recall_curve.png

Protocol:
- Binary target: 0=BENIGN, 1=attack.
- Train only on train.csv.
- Use validation.csv to select a threshold based on F1.
- Evaluate test.csv once using the selected threshold.
- Test data is never used for fitting or threshold selection.
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed" / "cleaned_final"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"

TARGET = "target"
METADATA_COLUMNS = {"Label", "target", "capture_day"}
RANDOM_STATE = 42

# Resource-conscious first baseline. Can increase estimators after timing this run.
N_ESTIMATORS = 120
MAX_DEPTH = 24
MIN_SAMPLES_LEAF = 2
MAX_FEATURES = "sqrt"
N_JOBS = -1
THRESHOLD_POINTS = 201


def load_split(path: Path, expected_features: list[str] | None = None):
    print(f"Loading {path.name} ...", flush=True)
    frame = pd.read_csv(path)
    if TARGET not in frame.columns:
        raise ValueError(f"Missing '{TARGET}' column in {path}")
    y = frame[TARGET].astype("int8")
    if not set(y.unique()).issubset({0, 1}):
        raise ValueError(f"Unexpected target values in {path}: {sorted(y.unique())}")

    feature_cols = [
        col for col in frame.columns
        if col not in METADATA_COLUMNS
    ]
    if expected_features is not None and feature_cols != expected_features:
        missing = sorted(set(expected_features) - set(feature_cols))
        extra = sorted(set(feature_cols) - set(expected_features))
        raise ValueError(
            f"Feature columns differ in {path.name}. Missing={missing}; extra={extra}"
        )

    X = frame[feature_cols].replace([np.inf, -np.inf], np.nan)
    if X.isna().any().any():
        bad = X.columns[X.isna().any()].tolist()
        raise ValueError(f"Missing/nonfinite values remain in {path.name}: {bad}")
    # The CSV stores features as numeric columns; fail rather than silently coerce.
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]):
            raise TypeError(f"Feature {col!r} is not numeric in {path.name}")
    print(
        f"  rows={len(frame):,}; features={X.shape[1]}; "
        f"benign={(y == 0).sum():,}; attack={(y == 1).sum():,}",
        flush=True,
    )
    return X, y, feature_cols, frame


def calculate_metrics(y_true, probabilities, threshold: float):
    predictions = (probabilities >= threshold).astype(np.uint8)
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "average_precision_pr_auc": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "classification_report": classification_report(
            y_true,
            predictions,
            labels=[0, 1],
            target_names=["BENIGN", "ATTACK"],
            output_dict=True,
            zero_division=0,
        ),
    }


def main():
    start = time.time()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    for name in ("train.csv", "validation.csv", "test.csv"):
        if not (DATA_DIR / name).exists():
            raise FileNotFoundError(f"Expected dataset file: {DATA_DIR / name}")

    X_train, y_train, feature_cols, _ = load_split(DATA_DIR / "train.csv")
    X_val, y_val, _, _ = load_split(DATA_DIR / "validation.csv", feature_cols)
    X_test, y_test, _, _ = load_split(DATA_DIR / "test.csv", feature_cols)

    if y_train.nunique() != 2:
        raise ValueError("Training split must contain both target classes.")
    if y_val.nunique() != 2 or y_test.nunique() != 2:
        raise ValueError("Validation and test splits must contain both target classes.")

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        max_features=MAX_FEATURES,
        class_weight="balanced_subsample",
        n_jobs=N_JOBS,
        random_state=RANDOM_STATE,
        verbose=1,
    )

    print("\nTraining Random Forest baseline ...", flush=True)
    fit_start = time.time()
    # Keep the estimator's built-in class weighting; no resampling/oversampling.
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        model.fit(X_train, y_train)
    fit_seconds = time.time() - fit_start
    print(f"Training finished in {fit_seconds / 60:.2f} minutes.", flush=True)

    print("\nScoring validation split for threshold selection ...", flush=True)
    val_prob = model.predict_proba(X_val)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y_val, val_prob)
    if len(thresholds) == 0:
        chosen_threshold = 0.5
    else:
        # precision_recall_curve returns one more precision/recall point than thresholds.
        f1_values = (
            2 * precision[:-1] * recall[:-1]
            / np.maximum(precision[:-1] + recall[:-1], 1e-12)
        )
        # Restrict selection to a deterministic grid to avoid selecting a threshold
        # that is overfit to tiny probability fluctuations.
        grid = np.linspace(0.05, 0.95, THRESHOLD_POINTS)
        grid_scores = []
        for threshold in grid:
            preds = (val_prob >= threshold).astype(np.uint8)
            grid_scores.append(f1_score(y_val, preds, zero_division=0))
        best = int(np.argmax(grid_scores))
        chosen_threshold = float(grid[best])
        val_best_f1 = float(grid_scores[best])

    val_metrics = calculate_metrics(y_val, val_prob, chosen_threshold)
    print(
        f"Selected threshold={chosen_threshold:.3f}; "
        f"validation F1={val_metrics['f1']:.4f}; "
        f"precision={val_metrics['precision']:.4f}; "
        f"recall={val_metrics['recall']:.4f}",
        flush=True,
    )

    # Threshold/model are now fixed. Evaluate the held-out test set once.
    print("\nEvaluating held-out test split ...", flush=True)
    test_prob = model.predict_proba(X_test)[:, 1]
    test_metrics = calculate_metrics(y_test, test_prob, chosen_threshold)

    model_bundle = {
        "model": model,
        "threshold": chosen_threshold,
        "feature_columns": feature_cols,
        "target_mapping": {"BENIGN": 0, "ATTACK": 1},
        "model_name": "RandomForestClassifier",
        "random_state": RANDOM_STATE,
    }
    model_path = MODEL_DIR / "baseline_random_forest.joblib"
    joblib.dump(model_bundle, model_path, compress=3)

    # Confusion matrix plot for test data.
    cm = np.array([
        [test_metrics["confusion_matrix"]["true_negative"],
         test_metrics["confusion_matrix"]["false_positive"]],
        [test_metrics["confusion_matrix"]["false_negative"],
         test_metrics["confusion_matrix"]["true_positive"]],
    ])
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.imshow(cm)
    ax.set_title(f"Test Confusion Matrix (threshold={chosen_threshold:.2f})")
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_xticks([0, 1], labels=["BENIGN", "ATTACK"])
    ax.set_yticks([0, 1], labels=["BENIGN", "ATTACK"])
    for (i, j), value in np.ndenumerate(cm):
        ax.text(j, i, f"{value:,}", ha="center", va="center")
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "baseline_confusion_matrix.png", dpi=150)
    plt.close(fig)

    # Precision-recall curve for test probabilities (visualization only; no tuning).
    pr_precision, pr_recall, _ = precision_recall_curve(y_test, test_prob)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(pr_recall, pr_precision)
    ax.set_title("Test Precision–Recall Curve")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "baseline_precision_recall_curve.png", dpi=150)
    plt.close(fig)

    report = {
        "model": "RandomForestClassifier",
        "parameters": {
            "n_estimators": N_ESTIMATORS,
            "max_depth": MAX_DEPTH,
            "min_samples_leaf": MIN_SAMPLES_LEAF,
            "max_features": MAX_FEATURES,
            "class_weight": "balanced_subsample",
            "random_state": RANDOM_STATE,
        },
        "dataset": {
            "directory": str(DATA_DIR),
            "feature_count": len(feature_cols),
            "train_rows": len(y_train),
            "validation_rows": len(y_val),
            "test_rows": len(y_test),
            "train_attack_count": int((y_train == 1).sum()),
            "validation_attack_count": int((y_val == 1).sum()),
            "test_attack_count": int((y_test == 1).sum()),
        },
        "protocol": {
            "threshold_selected_using": "validation F1 grid",
            "test_used_for_model_or_threshold_selection": False,
            "binary_target": {"0": "BENIGN", "1": "ATTACK"},
        },
        "selected_threshold": chosen_threshold,
        "validation_metrics_at_selected_threshold": val_metrics,
        "test_metrics_at_selected_threshold": test_metrics,
        "fit_seconds": fit_seconds,
        "total_seconds": time.time() - start,
        "model_path": str(model_path),
        "feature_importance_top_20": sorted(
            [
                {"feature": feature, "importance": float(importance)}
                for feature, importance in zip(feature_cols, model.feature_importances_)
            ],
            key=lambda item: item["importance"],
            reverse=True,
        )[:20],
    }

    json_path = REPORT_DIR / "baseline_metrics.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    text_lines = [
        "NetMind — Random Forest Baseline",
        "=" * 38,
        f"Threshold selected on validation: {chosen_threshold:.3f}",
        "",
        "VALIDATION METRICS",
        f"Precision: {val_metrics['precision']:.4f}",
        f"Recall:    {val_metrics['recall']:.4f}",
        f"F1:        {val_metrics['f1']:.4f}",
        f"PR-AUC:    {val_metrics['average_precision_pr_auc']:.4f}",
        f"ROC-AUC:   {val_metrics['roc_auc']:.4f}",
        "",
        "HELD-OUT TEST METRICS",
        f"Precision: {test_metrics['precision']:.4f}",
        f"Recall:    {test_metrics['recall']:.4f}",
        f"F1:        {test_metrics['f1']:.4f}",
        f"PR-AUC:    {test_metrics['average_precision_pr_auc']:.4f}",
        f"ROC-AUC:   {test_metrics['roc_auc']:.4f}",
        "",
        "TEST CONFUSION MATRIX",
        f"TN={cm[0,0]:,}  FP={cm[0,1]:,}",
        f"FN={cm[1,0]:,}  TP={cm[1,1]:,}",
        "",
        f"Training time: {fit_seconds / 60:.2f} minutes",
        f"Model: {model_path}",
        f"JSON report: {json_path}",
    ]
    (REPORT_DIR / "baseline_metrics.txt").write_text(
        "\n".join(text_lines) + "\n", encoding="utf-8"
    )

    print("\n" + "\n".join(text_lines), flush=True)
    print(f"\nTop features:", flush=True)
    for item in report["feature_importance_top_20"][:10]:
        print(f"  {item['feature']}: {item['importance']:.5f}", flush=True)
    print("\nSaved model and reports.", flush=True)


if __name__ == "__main__":
    main()
