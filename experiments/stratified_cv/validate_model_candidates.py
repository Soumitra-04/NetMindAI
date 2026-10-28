r"""
Validation comparison for NetMindAI CIC-IDS2017.
Fits candidate models on the existing cleaned train split and evaluates on the
existing validation split. It does not modify raw data, cleaned CSVs, or the
saved baseline model.

Threshold selection uses validation predictions only and is reported under
explicit false-positive-rate constraints. This is still model-selection data;
do not treat these validation metrics as final test performance.
"""
from pathlib import Path
import json, time, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed" / "cleaned_final"
TRAIN_PATH = DATA_DIR / "train.csv"
VAL_PATH = DATA_DIR / "validation.csv"
OUT_DIR = ROOT / "experiments" / "stratified_cv" / "validation_comparison"

RANDOM_STATE = 42
DIAGNOSTIC_THRESHOLDS = [0.001, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.3, 0.5]
# Operating-point summaries: choose the lowest threshold whose validation FPR
# does not exceed each target. These are validation-selected, not test-selected.
FPR_TARGETS = [0.001, 0.005, 0.01]

MODELS = {
    "RandomForest": lambda: RandomForestClassifier(
        n_estimators=120, max_depth=24, min_samples_leaf=2,
        max_features="sqrt", class_weight="balanced_subsample",
        n_jobs=-1, random_state=RANDOM_STATE,
    ),
    "ExtraTrees": lambda: ExtraTreesClassifier(
        n_estimators=120, max_depth=24, min_samples_leaf=2,
        max_features="sqrt", class_weight="balanced",
        n_jobs=-1, random_state=RANDOM_STATE,
    ),
    "HistGradientBoosting": lambda: HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.1, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=RANDOM_STATE,
    ),
}

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
    """Find threshold with maximum recall among thresholds satisfying FPR cap."""
    # Unique predicted scores plus endpoints give exact empirical operating points.
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

def score_model(model, X):
    if not hasattr(model, "predict_proba"):
        raise TypeError(f"{type(model).__name__} does not support predict_proba")
    classes = list(model.classes_)
    return model.predict_proba(X)[:, classes.index(1)]

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
    required = excluded
    for name, df in [("train", train_df), ("validation", val_df)]:
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"{name}.csv missing columns: {sorted(missing)}")

    # Ensure both splits have the same feature schema and order.
    train_features = [c for c in train_df.columns if c not in excluded]
    val_features = [c for c in val_df.columns if c not in excluded]
    if set(train_features) != set(val_features):
        raise ValueError(
            "Train/validation feature columns differ. "
            f"Train-only={sorted(set(train_features)-set(val_features))}; "
            f"validation-only={sorted(set(val_features)-set(train_features))}"
        )
    feature_cols = train_features
    val_df = val_df[feature_cols + ["Label", "target", "capture_day"]]
    X_train = train_df[feature_cols].replace([np.inf, -np.inf], np.nan)
    X_val = val_df[feature_cols].replace([np.inf, -np.inf], np.nan)
    if X_train.isna().any().any() or X_val.isna().any().any():
        raise ValueError("Found missing/non-finite features; script will not silently impute.")

    y_train = pd.to_numeric(train_df["target"], errors="raise").astype(np.int8).to_numpy()
    y_val = pd.to_numeric(val_df["target"], errors="raise").astype(np.int8).to_numpy()
    if set(np.unique(y_train)) != {0, 1} or set(np.unique(y_val)) != {0, 1}:
        raise ValueError("Both train and validation must contain target classes 0 and 1.")
    val_labels = val_df["Label"].astype(str).to_numpy()
    train_labels = train_df["Label"].astype(str).to_numpy()

    print(f"Train rows={len(train_df):,}; validation rows={len(val_df):,}; features={len(feature_cols)}")
    print(f"Train families: {sorted(np.unique(train_labels).tolist())}")
    print(f"Validation families: {sorted(np.unique(val_labels).tolist())}")
    print("Fitting three models. This may take several minutes.")

    results = {
        "train_rows": int(len(train_df)), "validation_rows": int(len(val_df)),
        "feature_count": len(feature_cols), "excluded_columns": sorted(excluded),
        "train_families": sorted(np.unique(train_labels).tolist()),
        "validation_families": sorted(np.unique(val_labels).tolist()),
        "validation_only_threshold_selection": True,
        "fpr_targets": FPR_TARGETS,
        "warning": "These are validation results for model selection, not final test results. Keep test.csv untouched until model and operating point are locked.",
        "models": {},
    }
    summary_rows = []
    report = [
        "NETMINDAI VALIDATION MODEL COMPARISON", "=" * 80,
        f"Train rows: {len(train_df):,}; validation rows: {len(val_df):,}; features: {len(feature_cols)}",
        f"Train families: {sorted(np.unique(train_labels).tolist())}",
        f"Validation families: {sorted(np.unique(val_labels).tolist())}",
        "Thresholds/operating points below use validation only; final test remains untouched.", "",
    ]

    for name, factory in MODELS.items():
        print(f"\n=== {name} ===")
        model = factory()
        start = time.time()
        if name == "HistGradientBoosting":
            model.fit(X_train, y_train, sample_weight=compute_sample_weight("balanced", y_train))
        else:
            model.fit(X_train, y_train)
        fit_seconds = time.time() - start
        scores = score_model(model, X_val)
        roc = fnum(roc_auc_score(y_val, scores))
        ap = fnum(average_precision_score(y_val, scores))
        fixed = metrics_at(y_val, scores, 0.5)
        sweep = [metrics_at(y_val, scores, t) for t in DIAGNOSTIC_THRESHOLDS]
        fpr_points = {
            str(target): threshold_for_fpr(y_val, scores, target)
            for target in FPR_TARGETS
        }

        family_results = {}
        for family in sorted(np.unique(val_labels).tolist()):
            mask = val_labels == family
            fs, ys = scores[mask], y_val[mask]
            is_attack = family.upper() != "BENIGN"
            family_results[family] = {
                "count": int(mask.sum()),
                "median_score": fnum(np.median(fs)),
                "p95_score": fnum(np.quantile(fs, 0.95)),
                "recall_at_0.5": fnum(np.mean(fs >= 0.5)) if is_attack else None,
                "recall_at_0.01": fnum(np.mean(fs >= 0.01)) if is_attack else None,
            }

        model_result = {
            "fit_seconds": round(fit_seconds, 2),
            "roc_auc": roc, "pr_auc_average_precision": ap,
            "metrics_at_0.5": fixed,
            "threshold_sweep_validation_only": sweep,
            "operating_points_by_validation_fpr_cap": fpr_points,
            "per_family": family_results,
        }
        results["models"][name] = model_result
        summary_rows.append({
            "model": name, "fit_seconds": round(fit_seconds, 2),
            "roc_auc": roc, "pr_auc_average_precision": ap,
            "precision_at_0.5": fixed["precision"], "recall_at_0.5": fixed["recall"],
            "f1_at_0.5": fixed["f1"], "fpr_at_0.5": fixed["false_positive_rate"],
            **{
                f"recall_at_fpr_le_{target:g}": (
                    fpr_points[str(target)]["recall"] if fpr_points[str(target)] else None
                )
                for target in FPR_TARGETS
            },
        })

        report += [
            "#" * 80, f"MODEL: {name}", "#" * 80,
            f"Fit seconds: {fit_seconds:.1f}",
            f"ROC-AUC: {roc}", f"PR-AUC / Average Precision: {ap}",
            "Metrics at threshold 0.5:", json.dumps(fixed, indent=2),
            "Per-family validation scores:", json.dumps(family_results, indent=2),
            "Validation-only operating points by FPR cap:", json.dumps(fpr_points, indent=2),
            "Threshold sweep (validation only):",
            "threshold | precision | recall | F1 | FPR | FP | FN | TP",
        ]
        for row in sweep:
            report.append(
                f"{row['threshold']:>8.4g} | {row['precision']:>9.4f} | "
                f"{row['recall']:>9.4f} | {row['f1']:>9.4f} | "
                f"{row['false_positive_rate']:>9.6f} | {row['fp']:>8,} | "
                f"{row['fn']:>8,} | {row['tp']:>8,}"
            )
        report.append("")
        print(f"ROC-AUC={roc:.4f}; PR-AUC={ap:.4f}; F1@0.5={fixed['f1']:.4f}; fit={fit_seconds:.1f}s")
        for cap, point in fpr_points.items():
            if point:
                print(f"  FPR cap {cap}: threshold={point['threshold']:.6g}, recall={point['recall']:.4f}, precision={point['precision']:.4f}")
            else:
                print(f"  FPR cap {cap}: no operating point found")

    (OUT_DIR / "validation_comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT_DIR / "validation_comparison.txt").write_text("\n".join(report), encoding="utf-8")
    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "validation_comparison.csv", index=False)
    print("\nDone. Outputs:")
    print(OUT_DIR / "validation_comparison.txt")
    print(OUT_DIR / "validation_comparison.json")
    print(OUT_DIR / "validation_comparison.csv")

if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        main()
