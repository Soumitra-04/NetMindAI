r"""
Run ONLY Extra Trees on the existing cleaned train and validation splits.
Does not run Random Forest/HistGradientBoosting or modify the saved baseline.
Uses 80 trees for a faster standalone run. The Random Forest validation run
used 120 trees, so estimator counts differ; set N_ESTIMATORS=120 below if you
need an exact estimator-count match, at likely higher runtime.
Threshold/operating-point analysis uses validation only. Keep test.csv untouched.
"""
from pathlib import Path
import json, time, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed" / "cleaned_final"
TRAIN_PATH = DATA_DIR / "train.csv"
VAL_PATH = DATA_DIR / "validation.csv"
OUT_DIR = ROOT / "experiments" / "stratified_cv" / "validation_comparison"

N_ESTIMATORS = 80
THRESHOLDS = [0.001, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.3, 0.5]
FPR_TARGETS = [0.001, 0.005, 0.01]

def fnum(x):
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def metrics_at(y, scores, threshold):
    pred = (scores >= threshold).astype(np.int8)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": fnum(precision_score(y, pred, zero_division=0)),
        "recall": fnum(recall_score(y, pred, zero_division=0)),
        "f1": fnum(f1_score(y, pred, zero_division=0)),
        "false_positive_rate": fnum(fp / (fp + tn)) if fp + tn else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }

def threshold_for_fpr(y, scores, target_fpr):
    # Find observed score threshold with maximum recall under the requested FPR cap.
    candidates = np.unique(np.concatenate(([0.0, 1.0], scores)))
    best = None
    for threshold in candidates:
        row = metrics_at(y, scores, float(threshold))
        if row["false_positive_rate"] <= target_fpr:
            if best is None or row["recall"] > best["recall"] or (
                row["recall"] == best["recall"] and row["precision"] > best["precision"]
            ):
                best = row
    return best

def main():
    for p in (TRAIN_PATH, VAL_PATH):
        if not p.exists():
            raise FileNotFoundError(f"Required cleaned split not found: {p}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading train: {TRAIN_PATH}")
    train_df = pd.read_csv(TRAIN_PATH, low_memory=False)
    print(f"Loading validation: {VAL_PATH}")
    val_df = pd.read_csv(VAL_PATH, low_memory=False)

    excluded = {"Label", "target", "capture_day"}
    for name, df in [("train", train_df), ("validation", val_df)]:
        missing = excluded - set(df.columns)
        if missing:
            raise ValueError(f"{name}.csv missing columns: {sorted(missing)}")
    features = [c for c in train_df.columns if c not in excluded]
    val_features = [c for c in val_df.columns if c not in excluded]
    if set(features) != set(val_features):
        raise ValueError("Train/validation feature schemas differ.")
    val_df = val_df[features + ["Label", "target", "capture_day"]]

    X_train = train_df[features].replace([np.inf, -np.inf], np.nan)
    X_val = val_df[features].replace([np.inf, -np.inf], np.nan)
    if X_train.isna().any().any() or X_val.isna().any().any():
        raise ValueError("Missing/non-finite features found; refusing to silently impute.")
    y_train = pd.to_numeric(train_df["target"], errors="raise").astype(np.int8).to_numpy()
    y_val = pd.to_numeric(val_df["target"], errors="raise").astype(np.int8).to_numpy()
    if set(np.unique(y_train)) != {0, 1} or set(np.unique(y_val)) != {0, 1}:
        raise ValueError("Both train and validation must contain target classes 0 and 1.")

    print(f"Train rows={len(train_df):,}; validation rows={len(val_df):,}; features={len(features)}")
    print(f"Fitting Extra Trees only ({N_ESTIMATORS} trees).")
    model = ExtraTreesClassifier(
        n_estimators=N_ESTIMATORS, max_depth=24, min_samples_leaf=2,
        max_features="sqrt", class_weight="balanced", n_jobs=-1, random_state=42,
    )
    started = time.time()
    model.fit(X_train, y_train)
    fit_seconds = time.time() - started
    scores = model.predict_proba(X_val)[:, list(model.classes_).index(1)]

    roc = fnum(roc_auc_score(y_val, scores))
    ap = fnum(average_precision_score(y_val, scores))
    fixed = metrics_at(y_val, scores, 0.5)
    sweep = [metrics_at(y_val, scores, t) for t in THRESHOLDS]
    operating = {str(cap): threshold_for_fpr(y_val, scores, cap) for cap in FPR_TARGETS}

    labels = val_df["Label"].astype(str).to_numpy()
    family_results = {}
    for family in sorted(np.unique(labels).tolist()):
        mask = labels == family
        fs = scores[mask]
        family_results[family] = {
            "count": int(mask.sum()),
            "median_score": fnum(np.median(fs)),
            "p95_score": fnum(np.quantile(fs, .95)),
            "recall_at_0.5": fnum(np.mean(fs >= .5)) if family.upper() != "BENIGN" else None,
            "recall_at_0.01": fnum(np.mean(fs >= .01)) if family.upper() != "BENIGN" else None,
        }

    result = {
        "model": "ExtraTrees", "n_estimators": N_ESTIMATORS,
        "max_depth": 24, "min_samples_leaf": 2, "max_features": "sqrt",
        "class_weight": "balanced", "fit_seconds": round(fit_seconds, 2),
        "train_rows": int(len(train_df)), "validation_rows": int(len(val_df)),
        "feature_count": len(features), "roc_auc": roc,
        "pr_auc_average_precision": ap, "metrics_at_0.5": fixed,
        "operating_points_by_validation_fpr_cap": operating,
        "threshold_sweep_validation_only": sweep, "per_family": family_results,
        "note": "Faster 80-tree run; Random Forest validation used 120 trees, so estimator counts differ. Validation only; final test untouched.",
    }
    report = [
        "EXTRA TREES — VALIDATION RESULTS", "=" * 76,
        f"Trees={N_ESTIMATORS}; max_depth=24; min_samples_leaf=2; max_features=sqrt; class_weight=balanced",
        f"Train rows={len(train_df):,}; validation rows={len(val_df):,}; features={len(features)}",
        f"Fit seconds={fit_seconds:.1f}", f"ROC-AUC={roc}", f"PR-AUC / Average Precision={ap}",
        "Metrics at threshold 0.5:", json.dumps(fixed, indent=2),
        "Per-family results:", json.dumps(family_results, indent=2),
        "Validation-only operating points by FPR cap:", json.dumps(operating, indent=2),
        "Threshold sweep (validation only):", "threshold | precision | recall | F1 | FPR | FP | FN | TP",
    ]
    for row in sweep:
        report.append(
            f"{row['threshold']:>8.4g} | {row['precision']:>9.4f} | {row['recall']:>9.4f} | "
            f"{row['f1']:>9.4f} | {row['false_positive_rate']:>9.6f} | "
            f"{row['fp']:>8,} | {row['fn']:>8,} | {row['tp']:>8,}"
        )

    # Separate filenames: don't overwrite the existing full comparison outputs.
    (OUT_DIR / "extra_trees_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUT_DIR / "extra_trees_validation.txt").write_text("\n".join(report), encoding="utf-8")
    pd.DataFrame([{
        "model": "ExtraTrees", "n_estimators": N_ESTIMATORS,
        "fit_seconds": round(fit_seconds, 2), "roc_auc": roc, "pr_auc_average_precision": ap,
        "precision_at_0.5": fixed["precision"], "recall_at_0.5": fixed["recall"],
        "f1_at_0.5": fixed["f1"], "fpr_at_0.5": fixed["false_positive_rate"],
        **{f"recall_at_fpr_le_{cap:g}": operating[str(cap)]["recall"] if operating[str(cap)] else None
           for cap in FPR_TARGETS},
    }]).to_csv(OUT_DIR / "extra_trees_validation.csv", index=False)

    print(f"ROC-AUC={roc:.4f}; PR-AUC={ap:.4f}; F1@0.5={fixed['f1']:.4f}; fit={fit_seconds:.1f}s")
    for cap, point in operating.items():
        if point:
            print(f"FPR cap {cap}: threshold={point['threshold']:.6g}, recall={point['recall']:.4f}, precision={point['precision']:.4f}")
    print("\nSaved:")
    print(OUT_DIR / "extra_trees_validation.txt")
    print(OUT_DIR / "extra_trees_validation.json")
    print(OUT_DIR / "extra_trees_validation.csv")

if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        main()
