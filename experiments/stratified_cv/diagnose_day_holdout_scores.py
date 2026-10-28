r"""Diagnostic-only analysis of Random Forest capture-day holdout scores.

Run from anywhere in the D:\NetMind project tree:
  uv run python experiments\stratified_cv\diagnose_day_holdout_scores.py

Reads the existing cleaned train.csv; does not clean or modify the dataset.
Retrains one Random Forest per held-out capture day, so it may take several minutes.
Threshold sweep is diagnostic only; do not select a deployment threshold from these holdouts.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "cleaned_final" / "train.csv"
OUT = ROOT / "experiments" / "stratified_cv" / "day_holdout_diagnostics"
THRESHOLDS = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
FIXED_THRESHOLD = 0.5

def finite(x):
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def score_summary(scores):
    scores = np.asarray(scores, dtype=float)
    if not len(scores):
        return {"count": 0}
    q = np.quantile(scores, [0, .25, .5, .75, .9, .95, .99, 1])
    return {
        "count": int(len(scores)), "min": finite(q[0]), "p25": finite(q[1]),
        "median": finite(q[2]), "p75": finite(q[3]), "p90": finite(q[4]),
        "p95": finite(q[5]), "p99": finite(q[6]), "max": finite(q[7]),
        "mean": finite(np.mean(scores)),
        "fraction_score_ge_0.01": finite(np.mean(scores >= .01)),
        "fraction_score_ge_0.1": finite(np.mean(scores >= .1)),
        "fraction_score_ge_0.5": finite(np.mean(scores >= .5)),
    }

def metrics(y, scores, threshold):
    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    has_attacks = bool(np.any(y == 1))
    return {
        "threshold": float(threshold),
        "precision": finite(precision_score(y, pred, zero_division=0)) if has_attacks else None,
        "recall": finite(recall_score(y, pred, zero_division=0)) if has_attacks else None,
        "f1": finite(f1_score(y, pred, zero_division=0)) if has_attacks else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }

def plot_scores(day, y, scores, path):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bins = np.linspace(0, 1, 51)
    if np.any(y == 0):
        ax.hist(scores[y == 0], bins=bins, alpha=.65, density=True,
                label=f"Benign (n={(y == 0).sum():,})")
    if np.any(y == 1):
        ax.hist(scores[y == 1], bins=bins, alpha=.65, density=True,
                label=f"Attack (n={(y == 1).sum():,})")
    ax.axvline(.5, linestyle="--", linewidth=1.5, label="Current threshold = 0.5")
    ax.set(title=f"{day} holdout: predicted attack-score distributions",
           xlabel="Predicted probability of attack", ylabel="Density", xlim=(0, 1))
    ax.grid(True, alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(path, dpi=150); plt.close(fig)

def plot_thresholds(day, rows, path):
    valid = [r for r in rows if r["recall"] is not None]
    if not valid:
        return
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for key in ("precision", "recall", "f1"):
        ax.plot([r["threshold"] for r in valid], [r[key] for r in valid],
                marker="o", label=key.title())
    ax.axvline(.5, linestyle="--", linewidth=1.5, label="Current threshold = 0.5")
    ax.set_xscale("log"); ax.set_ylim(-.02, 1.02)
    ax.set(title=f"{day} holdout: threshold sweep (diagnostic only)",
           xlabel="Threshold (log scale)", ylabel="Metric")
    ax.grid(True, alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(path, dpi=150); plt.close(fig)

def main():
    if not DATA.exists():
        raise FileNotFoundError(f"Cleaned training CSV not found: {DATA}")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Loading existing cleaned data: {DATA}")
    df = pd.read_csv(DATA, low_memory=False)
    needed = {"Label", "target", "capture_day"}
    if not needed.issubset(df.columns):
        raise ValueError(f"Missing required columns: {sorted(needed - set(df.columns))}")
    drop = {"Label", "target", "capture_day"}
    features = [c for c in df.columns if c not in drop]
    X = df[features].replace([np.inf, -np.inf], np.nan)
    if X.isna().any().any():
        raise ValueError("Non-finite/missing feature values found; script will not silently impute.")
    y = pd.to_numeric(df["target"], errors="raise").astype(int).to_numpy()
    if not set(np.unique(y)).issubset({0, 1}):
        raise ValueError(f"Expected target values 0/1, got {np.unique(y)}")
    day_values = df["capture_day"].astype(str).to_numpy()
    label_values = df["Label"].astype(str).to_numpy()
    days = sorted(np.unique(day_values).tolist())
    results = {
        "rows": int(len(df)), "feature_count": len(features),
        "excluded_columns": sorted(drop), "fixed_threshold": FIXED_THRESHOLD,
        "threshold_sweep_warning": "Diagnostic only. Do not select a deployment threshold from held-out days.",
        "days": {},
    }
    report = [
        "DAY-HOLDOUT SCORE DIAGNOSTICS", "=" * 72,
        f"Rows: {len(df):,}; features: {len(features)}",
        "Threshold sweep is diagnostic only, not a deployment-threshold selection procedure.", ""
    ]

    for day in days:
        hold = day_values == day
        train = ~hold
        X_train, y_train = X.loc[train], y[train]
        X_hold, y_hold = X.loc[hold], y[hold]
        labels_hold = label_values[hold]
        train_families = sorted(np.unique(label_values[train]).tolist())
        hold_families = sorted(np.unique(labels_hold).tolist())
        unseen = sorted(set(hold_families) - set(train_families))
        print(f"\nHoldout {day}: train={len(y_train):,}, holdout={len(y_hold):,}")
        print(f"Unseen families: {unseen}")

        model = RandomForestClassifier(
            n_estimators=80, max_depth=24, min_samples_leaf=2,
            max_features="sqrt", class_weight="balanced_subsample",
            n_jobs=-1, random_state=42,
        )
        model.fit(X_train, y_train)
        attack_col = list(model.classes_).index(1)
        scores = model.predict_proba(X_hold)[:, attack_col]
        sweep = [metrics(y_hold, scores, t) for t in THRESHOLDS]
        fixed = metrics(y_hold, scores, FIXED_THRESHOLD)
        both_classes = len(np.unique(y_hold)) == 2
        roc = finite(roc_auc_score(y_hold, scores)) if both_classes else None
        ap = finite(average_precision_score(y_hold, scores)) if np.any(y_hold == 1) else None
        per_family = {}
        for family in hold_families:
            mask = labels_hold == family
            fam_scores = scores[mask]
            is_attack = family.upper() != "BENIGN"
            per_family[family] = {
                "count": int(mask.sum()),
                "median_score": finite(np.median(fam_scores)),
                "mean_score": finite(np.mean(fam_scores)),
                "recall_at_0.5": finite(np.mean(fam_scores >= .5)) if is_attack else None,
                "score_summary": score_summary(fam_scores),
            }
        day_result = {
            "train_rows": int(train.sum()), "holdout_rows": int(hold.sum()),
            "holdout_benign_rows": int((y_hold == 0).sum()),
            "holdout_attack_rows": int((y_hold == 1).sum()),
            "holdout_has_both_classes": bool(both_classes),
            "train_families": train_families, "holdout_families": hold_families,
            "unseen_families": unseen, "roc_auc": roc, "pr_auc_average_precision": ap,
            "metrics_at_0.5": fixed,
            "benign_score_summary": score_summary(scores[y_hold == 0]),
            "attack_score_summary": score_summary(scores[y_hold == 1]),
            "per_family": per_family, "threshold_sweep_diagnostic_only": sweep,
        }
        results["days"][day] = day_result
        safe_day = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in day)
        plot_scores(day, y_hold, scores, OUT / f"{safe_day}_score_distribution.png")
        plot_thresholds(day, sweep, OUT / f"{safe_day}_threshold_sweep.png")

        report += [
            "-" * 72, f"HOLDOUT DAY: {day}",
            f"Holdout benign={int((y_hold == 0).sum()):,}; attacks={int((y_hold == 1).sum()):,}",
            f"Unseen families: {unseen}",
            f"ROC-AUC: {roc if roc is not None else 'N/A (holdout lacks both classes)'}",
            f"PR-AUC / Average Precision: {ap if ap is not None else 'N/A (no attacks in holdout)'}",
            f"At threshold 0.5: precision={fixed['precision']}, recall={fixed['recall']}, F1={fixed['f1']}",
            f"TN={fixed['tn']:,}; FP={fixed['fp']:,}; FN={fixed['fn']:,}; TP={fixed['tp']:,}",
            "Benign score summary:", json.dumps(day_result["benign_score_summary"], indent=2),
            "Attack score summary:", json.dumps(day_result["attack_score_summary"], indent=2),
            "Per-family summary:", json.dumps(per_family, indent=2),
            "Threshold sweep (diagnostic only):",
            "threshold | precision | recall | F1 | FP | FN | TP",
        ]
        for row in sweep:
            report.append(
                f"{row['threshold']:>9.3g} | {str(row['precision']):>9} | "
                f"{str(row['recall']):>9} | {str(row['f1']):>9} | "
                f"{row['fp']:>8,} | {row['fn']:>8,} | {row['tp']:>8,}"
            )
        report.append("")
        print(f"At 0.5: precision={fixed['precision']}, recall={fixed['recall']}, F1={fixed['f1']}")
        print(f"ROC-AUC={roc}; PR-AUC={ap}")

    (OUT / "day_holdout_score_diagnostics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "day_holdout_score_diagnostics.txt").write_text("\n".join(report), encoding="utf-8")
    print("\nFinished. Outputs:")
    print(f"  {OUT / 'day_holdout_score_diagnostics.txt'}")
    print(f"  {OUT / 'day_holdout_score_diagnostics.json'}")
    print(f"  Plots: {OUT}")

if __name__ == "__main__":
    main()
