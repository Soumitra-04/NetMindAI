#!/usr/bin/env python
"""
Diagnostics for the trained NetMind baseline.

Run from the project root:
    uv run python scripts/diagnose_baseline.py

This script does NOT retrain the model and does NOT choose a threshold using test labels.
Validation data is used for threshold analysis. Test data is used only for post-hoc
diagnostics, including per-attack-family results and score distributions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed" / "cleaned_final"
MODEL_PATH = ROOT / "models" / "baseline_random_forest.joblib"
REPORT_DIR = ROOT / "reports"

# Thresholds are explored on VALIDATION only. Test threshold sweeps are deliberately
# not performed, to avoid encouraging selection based on test labels.
THRESHOLD_GRID = np.linspace(0.05, 0.95, 181)
VALIDATION_RECALL_TARGETS = (0.80, 0.90, 0.95, 0.98)


def safe_float(value):
    value = float(value)
    return value if np.isfinite(value) else None


def binary_metrics(y_true, scores, threshold):
    y_true = np.asarray(y_true, dtype=np.uint8)
    scores = np.asarray(scores, dtype=np.float64)
    pred = scores >= float(threshold)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": safe_float(precision_score(y_true, pred, zero_division=0)),
        "recall": safe_float(recall_score(y_true, pred, zero_division=0)),
        "f1": safe_float(f1_score(y_true, pred, zero_division=0)),
        "pr_auc_average_precision": safe_float(average_precision_score(y_true, scores)),
        "roc_auc": safe_float(roc_auc_score(y_true, scores)) if len(np.unique(y_true)) == 2 else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "false_positive_rate": safe_float(fp / (fp + tn)) if (fp + tn) else None,
        "false_negative_rate": safe_float(fn / (fn + tp)) if (fn + tp) else None,
    }


def score_summary(scores):
    scores = np.asarray(scores, dtype=np.float64)
    if scores.size == 0:
        return {"count": 0}
    return {
        "count": int(scores.size),
        "min": safe_float(np.min(scores)),
        "p05": safe_float(np.quantile(scores, 0.05)),
        "p25": safe_float(np.quantile(scores, 0.25)),
        "median": safe_float(np.median(scores)),
        "mean": safe_float(np.mean(scores)),
        "p75": safe_float(np.quantile(scores, 0.75)),
        "p95": safe_float(np.quantile(scores, 0.95)),
        "max": safe_float(np.max(scores)),
    }


def load_split(name, feature_columns):
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    print(f"Loading {name}: {path}")
    df = pd.read_csv(path, low_memory=False)
    required = set(feature_columns) | {"target", "Label"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{name}.csv is missing required columns: {missing}")
    # Model inputs are strictly the saved feature list and saved order.
    X = df.loc[:, feature_columns]
    y = pd.to_numeric(df["target"], errors="raise").astype(np.uint8).to_numpy()
    labels = df["Label"].astype(str).to_numpy()
    if not np.isin(y, [0, 1]).all():
        raise ValueError(f"{name}.csv target contains values other than 0/1")
    return df, X, y, labels


def main():
    started = time.time()
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model bundle not found: {MODEL_PATH}\n"
            "Run the baseline training script first."
        )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    bundle = joblib.load(MODEL_PATH)
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ValueError("Expected a dict model bundle containing a 'model' entry.")
    model = bundle["model"]
    feature_columns = bundle.get("feature_columns")
    if not feature_columns:
        raise ValueError("Model bundle has no feature_columns list.")
    saved_threshold = float(bundle.get("threshold", 0.306))

    val_df, X_val, y_val, val_labels = load_split("validation", feature_columns)
    test_df, X_test, y_test, test_labels = load_split("test", feature_columns)

    print("Scoring validation split...")
    val_scores = model.predict_proba(X_val)[:, 1]
    print("Scoring test split...")
    test_scores = model.predict_proba(X_test)[:, 1]

    # Validation-only threshold analysis.
    val_sweep = []
    for threshold in THRESHOLD_GRID:
        metrics = binary_metrics(y_val, val_scores, threshold)
        val_sweep.append(metrics)

    best_f1_row = max(val_sweep, key=lambda row: (row["f1"], row["recall"]))
    threshold_by_recall = {}
    for target_recall in VALIDATION_RECALL_TARGETS:
        eligible = [row for row in val_sweep if row["recall"] >= target_recall]
        # Among thresholds reaching the recall target, maximize precision;
        # break ties by F1, then prefer the higher threshold.
        chosen = max(
            eligible,
            key=lambda row: (row["precision"], row["f1"], row["threshold"]),
        ) if eligible else None
        threshold_by_recall[str(target_recall)] = chosen

    val_saved_metrics = binary_metrics(y_val, val_scores, saved_threshold)
    val_best_f1_metrics = binary_metrics(y_val, val_scores, best_f1_row["threshold"])

    # Test metrics are computed at the saved validation-selected threshold only.
    test_metrics = binary_metrics(y_test, test_scores, saved_threshold)
    test_family_rows = []
    for family in sorted(np.unique(test_labels)):
        mask = test_labels == family
        family_y = y_test[mask]
        family_scores = test_scores[mask]
        family_pred = family_scores >= saved_threshold
        is_attack = family_y == 1
        attack_scores = family_scores[is_attack]
        detected_attacks = int(np.sum(family_pred & is_attack))
        total_attacks = int(np.sum(is_attack))
        test_family_rows.append({
            "label": str(family),
            "rows": int(mask.sum()),
            "attack_rows": total_attacks,
            "detected_attacks": detected_attacks,
            "missed_attacks": int(total_attacks - detected_attacks),
            "attack_recall": safe_float(detected_attacks / total_attacks) if total_attacks else None,
            "attack_score_summary": score_summary(attack_scores),
            "all_rows_score_summary": score_summary(family_scores),
        })

    benign_scores = test_scores[y_test == 0]
    attack_scores = test_scores[y_test == 1]
    test_score_summary = {
        "benign": score_summary(benign_scores),
        "attack": score_summary(attack_scores),
        "attack_families": {
            str(family): score_summary(test_scores[(test_labels == family) & (y_test == 1)])
            for family in sorted(np.unique(test_labels))
            if np.any((test_labels == family) & (y_test == 1))
        },
    }

    # A compact diagnostic: how much of the test attack score mass is below threshold?
    below = attack_scores < saved_threshold
    score_diagnostics = {
        "saved_threshold": saved_threshold,
        "test_attack_fraction_below_threshold": safe_float(np.mean(below)) if len(below) else None,
        "test_attack_fraction_at_or_above_threshold": safe_float(np.mean(~below)) if len(below) else None,
        "test_benign_fraction_at_or_above_threshold": safe_float(np.mean(benign_scores >= saved_threshold)) if len(benign_scores) else None,
        "test_attack_score_summary": score_summary(attack_scores),
        "test_benign_score_summary": score_summary(benign_scores),
    }

    report = {
        "model_path": str(MODEL_PATH),
        "model_name": bundle.get("model_name", type(model).__name__),
        "feature_count": len(feature_columns),
        "saved_threshold": saved_threshold,
        "data_rows": {
            "validation": int(len(val_df)),
            "test": int(len(test_df)),
            "validation_attacks": int(np.sum(y_val == 1)),
            "validation_benign": int(np.sum(y_val == 0)),
            "test_attacks": int(np.sum(y_test == 1)),
            "test_benign": int(np.sum(y_test == 0)),
        },
        "validation": {
            "at_saved_threshold": val_saved_metrics,
            "best_f1_on_validation_grid": best_f1_row,
            "thresholds_for_validation_recall_targets": threshold_by_recall,
            "threshold_sweep": val_sweep,
        },
        "test": {
            "at_saved_threshold_only": test_metrics,
            "per_label": test_family_rows,
            "score_diagnostics": score_diagnostics,
            "score_distributions": test_score_summary,
        },
        "methodology_notes": [
            "No model training or refitting was performed.",
            "Threshold exploration and recall-target thresholds use validation labels only.",
            "Test metrics are reported only at the saved threshold; test labels are not used to select a threshold.",
            "Per-label attack recall is computed only for rows whose target is attack (target=1).",
            "Label and target are reporting metadata, not model input features.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    json_path = REPORT_DIR / "baseline_diagnostics.json"
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    # Human-readable report.
    lines = [
        "NETMIND BASELINE DIAGNOSTICS",
        "=" * 31,
        f"Model: {report['model_name']}",
        f"Saved threshold: {saved_threshold:.3f}",
        f"Features: {len(feature_columns)}",
        "",
        "VALIDATION — threshold analysis (validation labels only)",
        "-" * 57,
    ]
    for title, metrics in [
        ("Saved threshold", val_saved_metrics),
        ("Best validation F1", best_f1_row),
    ]:
        lines.append(
            f"{title}: threshold={metrics['threshold']:.3f}, "
            f"precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, "
            f"F1={metrics['f1']:.4f}, PR-AUC={metrics['pr_auc_average_precision']:.4f}"
        )
    lines.append("")
    lines.append("Thresholds meeting validation recall targets (not test-tuned):")
    for target, metrics in threshold_by_recall.items():
        if metrics:
            lines.append(
                f"  recall >= {float(target):.0%}: threshold={metrics['threshold']:.3f}, "
                f"precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, "
                f"F1={metrics['f1']:.4f}, FP={metrics['fp']}, FN={metrics['fn']}"
            )
        else:
            lines.append(f"  recall >= {float(target):.0%}: no threshold in grid reached target")

    lines += [
        "",
        "TEST — saved threshold only (not used for threshold selection)",
        "-" * 62,
        f"Precision={test_metrics['precision']:.4f}, Recall={test_metrics['recall']:.4f}, "
        f"F1={test_metrics['f1']:.4f}, PR-AUC={test_metrics['pr_auc_average_precision']:.4f}, "
        f"ROC-AUC={test_metrics['roc_auc']:.4f}",
        f"TN={test_metrics['tn']}, FP={test_metrics['fp']}, "
        f"FN={test_metrics['fn']}, TP={test_metrics['tp']}",
        "",
        "PER-LABEL ATTACK RECALL AT SAVED THRESHOLD",
        "-" * 44,
    ]
    for row in test_family_rows:
        if row["attack_rows"]:
            lines.append(
                f"{row['label']}: attacks={row['attack_rows']}, "
                f"detected={row['detected_attacks']}, missed={row['missed_attacks']}, "
                f"recall={row['attack_recall']:.4f}, "
                f"median_score={row['attack_score_summary']['median']:.4f}"
            )
        else:
            lines.append(f"{row['label']}: rows={row['rows']} (no target=1 rows)")
    lines += [
        "",
        "SCORE DIAGNOSTICS",
        "-" * 18,
        f"Test attack scores below threshold: {score_diagnostics['test_attack_fraction_below_threshold']:.2%}",
        f"Test benign scores at/above threshold: {score_diagnostics['test_benign_fraction_at_or_above_threshold']:.2%}",
        f"Attack score median: {score_diagnostics['test_attack_score_summary']['median']:.4f}",
        f"Benign score median: {score_diagnostics['test_benign_score_summary']['median']:.4f}",
        "",
        "Interpretation reminder: select any operating threshold using validation data,",
        "then freeze it before the final test evaluation.",
        f"Elapsed: {report['elapsed_seconds']:.1f}s",
    ]
    txt_path = REPORT_DIR / "baseline_diagnostics.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Plot score distributions for benign vs attack and each test attack family.
    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.linspace(0.0, 1.0, 51)
    ax.hist(benign_scores, bins=bins, density=True, alpha=0.55, label="Benign", log=True)
    ax.hist(attack_scores, bins=bins, density=True, alpha=0.55, label="All attacks", log=True)
    ax.axvline(saved_threshold, linestyle="--", linewidth=2, label=f"Saved threshold ({saved_threshold:.3f})")
    ax.set_xlabel("Predicted attack probability")
    ax.set_ylabel("Density (log scale)")
    ax.set_title("Test score distributions: benign vs attacks")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "baseline_test_score_distributions.png", dpi=160)
    plt.close(fig)

    attack_rows = [row for row in test_family_rows if row["attack_rows"] > 0]
    if attack_rows:
        attack_rows.sort(key=lambda row: row["attack_recall"] if row["attack_recall"] is not None else -1)
        fig, ax = plt.subplots(figsize=(11, max(5, 0.45 * len(attack_rows))))
        names = [row["label"] for row in attack_rows]
        recalls = [row["attack_recall"] for row in attack_rows]
        bars = ax.barh(names, recalls)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Attack recall")
        ax.set_title(f"Test attack-family recall at saved threshold ({saved_threshold:.3f})")
        ax.grid(axis="x", alpha=0.25)
        for bar, value in zip(bars, recalls):
            ax.text(min(value + 0.015, 0.94), bar.get_y() + bar.get_height()/2,
                    f"{value:.1%}", va="center")
        fig.tight_layout()
        fig.savefig(REPORT_DIR / "baseline_attack_family_recall.png", dpi=160)
        plt.close(fig)

    print("\nDiagnostics complete.")
    print(f"Text report: {txt_path}")
    print(f"JSON report: {json_path}")
    print(f"Score plot: {REPORT_DIR / 'baseline_test_score_distributions.png'}")
    print(f"Attack-family plot: {REPORT_DIR / 'baseline_attack_family_recall.png'}")
    print(f"Elapsed: {time.time() - started:.1f} seconds")


if __name__ == "__main__":
    main()
