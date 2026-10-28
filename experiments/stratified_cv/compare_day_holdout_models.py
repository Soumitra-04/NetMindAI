r"""
Controlled classifier comparison for NetMindAI.
Reads existing cleaned train.csv only. No cleaning is repeated.
Runs leave-one-capture-day-out evaluation for Random Forest, Extra Trees,
and HistGradientBoosting. Capture day and attack family are confounded, so
results test their combined generalization, not a pure day effect.
Threshold sweep is diagnostic only; do not choose a deployment threshold here.
"""
from pathlib import Path
import json, time, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "cleaned_final" / "train.csv"
OUT = ROOT / "experiments" / "stratified_cv" / "model_comparison"
THRESHOLDS = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]

MODELS = {
    "RandomForest": lambda: RandomForestClassifier(
        n_estimators=80, max_depth=24, min_samples_leaf=2,
        max_features="sqrt", class_weight="balanced_subsample",
        n_jobs=-1, random_state=42),
    "ExtraTrees": lambda: ExtraTreesClassifier(
        n_estimators=80, max_depth=24, min_samples_leaf=2,
        max_features="sqrt", class_weight="balanced",
        n_jobs=-1, random_state=42),
    "HistGradientBoosting": lambda: HistGradientBoostingClassifier(
        max_iter=100, learning_rate=0.1, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=42),
}

def fnum(x):
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def metrics(y, scores, threshold):
    pred = (scores >= threshold).astype(np.int8)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    has_attacks = bool(np.any(y == 1))
    return {
        "threshold": float(threshold),
        "precision": fnum(precision_score(y, pred, zero_division=0)) if has_attacks else None,
        "recall": fnum(recall_score(y, pred, zero_division=0)) if has_attacks else None,
        "f1": fnum(f1_score(y, pred, zero_division=0)) if has_attacks else None,
        "false_positive_rate": fnum(fp / (fp + tn)) if fp + tn else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }

def main():
    if not DATA.exists():
        raise FileNotFoundError(f"Cleaned training CSV not found: {DATA}")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Loading existing cleaned data: {DATA}")
    df = pd.read_csv(DATA, low_memory=False)
    required = {"Label", "target", "capture_day"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing required columns: {sorted(required - set(df.columns))}")
    excluded = {"Label", "target", "capture_day"}
    feature_cols = [c for c in df.columns if c not in excluded]
    X = df[feature_cols].replace([np.inf, -np.inf], np.nan)
    if X.isna().any().any():
        raise ValueError("Missing/non-finite features found; refusing to silently impute.")
    y = pd.to_numeric(df["target"], errors="raise").astype(np.int8).to_numpy()
    if not set(np.unique(y)).issubset({0, 1}):
        raise ValueError(f"Expected target 0/1, got {np.unique(y)}")
    days = df["capture_day"].astype(str).to_numpy()
    family = df["Label"].astype(str).to_numpy()
    unique_days = sorted(np.unique(days).tolist())
    results = {
        "rows": int(len(df)), "feature_count": len(feature_cols),
        "evaluation": "Leave-one-capture-day-out on existing cleaned train.csv",
        "caveat": "Capture day and attack family are confounded. Threshold sweep is diagnostic only.",
        "models": {},
    }
    report = [
        "NETMINDAI CONTROLLED MODEL COMPARISON", "=" * 78,
        f"Rows: {len(df):,}; features: {len(feature_cols)}; days: {unique_days}",
        "Evaluation: leave-one-capture-day-out on existing cleaned train.csv.",
        "Capture day and attack family are confounded; this is not a pure day-effect test.",
        "Threshold sweep is diagnostic only; do not use holdout days to select a production threshold.", "",
    ]
    flat = []
    for model_name, factory in MODELS.items():
        print(f"\n=== {model_name} ===")
        results["models"][model_name] = {}
        report += ["#" * 78, f"MODEL: {model_name}", "#" * 78]
        for day in unique_days:
            hold = days == day
            train = ~hold
            Xtr, Xho = X.loc[train], X.loc[hold]
            ytr, yho = y[train], y[hold]
            hold_families = sorted(np.unique(family[hold]).tolist())
            train_families = set(np.unique(family[train]).tolist())
            unseen = sorted(set(hold_families) - train_families)
            model = factory()
            start = time.time()
            if model_name == "HistGradientBoosting":
                model.fit(Xtr, ytr, sample_weight=compute_sample_weight("balanced", ytr))
            else:
                model.fit(Xtr, ytr)
            elapsed = time.time() - start
            if hasattr(model, "predict_proba"):
                scores = model.predict_proba(Xho)[:, list(model.classes_).index(1)]
            else:
                raw = np.clip(model.decision_function(Xho), -40, 40)
                scores = 1 / (1 + np.exp(-raw))
            fixed = metrics(yho, scores, 0.5)
            sweep = [metrics(yho, scores, t) for t in THRESHOLDS]
            both = len(np.unique(yho)) == 2
            roc = fnum(roc_auc_score(yho, scores)) if both else None
            ap = fnum(average_precision_score(yho, scores)) if np.any(yho == 1) else None
            per_family = {}
            for fam in hold_families:
                m = family[hold] == fam
                fs = scores[m]
                per_family[fam] = {
                    "count": int(m.sum()), "median_score": fnum(np.median(fs)),
                    "recall_at_0.5": fnum(np.mean(fs >= 0.5)) if fam.upper() != "BENIGN" else None,
                    "recall_at_0.01": fnum(np.mean(fs >= 0.01)) if fam.upper() != "BENIGN" else None,
                    "p95_score": fnum(np.quantile(fs, .95)),
                }
            entry = {
                "train_rows": int(train.sum()), "holdout_rows": int(hold.sum()),
                "holdout_benign_rows": int((yho == 0).sum()),
                "holdout_attack_rows": int((yho == 1).sum()),
                "unseen_families": unseen, "fit_seconds": round(elapsed, 2),
                "roc_auc": roc, "pr_auc_average_precision": ap,
                "metrics_at_0.5": fixed, "threshold_sweep_diagnostic_only": sweep,
                "per_family": per_family,
            }
            results["models"][model_name][day] = entry
            flat.append({
                "model": model_name, "holdout_day": day, "train_rows": int(train.sum()),
                "holdout_rows": int(hold.sum()), "holdout_attacks": int((yho == 1).sum()),
                "roc_auc": roc, "pr_auc_average_precision": ap,
                "precision_at_0.5": fixed["precision"], "recall_at_0.5": fixed["recall"],
                "f1_at_0.5": fixed["f1"], "false_positive_rate_at_0.5": fixed["false_positive_rate"],
                "fit_seconds": round(elapsed, 2), "unseen_families": "; ".join(unseen),
            })
            report += [
                "-" * 78, f"Holdout day: {day}",
                f"Benign={int((yho == 0).sum()):,}; attacks={int((yho == 1).sum()):,}",
                f"Unseen families: {unseen}", f"Fit seconds: {elapsed:.1f}",
                f"ROC-AUC: {roc if roc is not None else 'N/A (single-class holdout)'}",
                f"PR-AUC / Average Precision: {ap if ap is not None else 'N/A (no attacks)'}",
                f"At threshold 0.5: precision={fixed['precision']}, recall={fixed['recall']}, F1={fixed['f1']}, FPR={fixed['false_positive_rate']}",
                f"TN={fixed['tn']:,}; FP={fixed['fp']:,}; FN={fixed['fn']:,}; TP={fixed['tp']:,}",
                "Per-family:", json.dumps(per_family, indent=2),
                "Threshold sweep (diagnostic only):", "threshold | precision | recall | F1 | FPR | FP | FN | TP",
            ]
            for r in sweep:
                report.append(f"{r['threshold']:>9.3g} | {str(r['precision']):>9} | {str(r['recall']):>9} | {str(r['f1']):>9} | {str(r['false_positive_rate']):>9} | {r['fp']:>8,} | {r['fn']:>8,} | {r['tp']:>8,}")
            report.append("")
            print(f"{day}: ROC-AUC={roc}, PR-AUC={ap}, F1@0.5={fixed['f1']}, fit={elapsed:.1f}s")
    (OUT / "comparison_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "comparison_report.txt").write_text("\n".join(report), encoding="utf-8")
    pd.DataFrame(flat).to_csv(OUT / "comparison_results.csv", index=False)
    print("\nDone. Outputs:")
    print(OUT / "comparison_report.txt")
    print(OUT / "comparison_results.json")
    print(OUT / "comparison_results.csv")

if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        main()
