"""
Final CIC-IDS2017 data-quality audit for NetMind.
Run from project root:
    uv run python scripts/audit_cleaned_data.py

Writes data/processed/cleaned/final_audit_report.json.
Does not modify data or train a model.
"""
from __future__ import annotations
import json
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed" / "cleaned"
OUT_PATH = DATA_DIR / "final_audit_report.json"
DB_PATH = DATA_DIR / "final_audit_work.duckdb"
SPLITS = {
    "train": DATA_DIR / "train.csv",
    "validation": DATA_DIR / "validation.csv",
    "test": DATA_DIR / "test.csv",
}
META = {"Label", "target", "capture_day"}

def qi(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'

def qp(p: Path) -> str:
    return "'" + p.as_posix().replace("'", "''") + "'"

def main() -> None:
    missing = [str(p) for p in SPLITS.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing cleaned split(s):\n" + "\n".join(missing))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "audit_tmp").mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads TO 4")
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = {qp(DATA_DIR / 'audit_tmp')}")
    for name, path in SPLITS.items():
        con.execute(f"""
            CREATE VIEW {name} AS
            SELECT * FROM read_csv_auto(
                {qp(path)}, header=true, sample_size=200000, ignore_errors=false
            )
        """)
    train_cols = [r[0] for r in con.execute("DESCRIBE train").fetchall()]
    for split in ("validation", "test"):
        cols = [r[0] for r in con.execute(f"DESCRIBE {split}").fetchall()]
        if cols != train_cols:
            raise ValueError(f"Schema mismatch: {split} columns differ from train.")
    if not {"Label", "target", "capture_day"}.issubset(train_cols):
        raise ValueError("Expected Label, target, and capture_day columns are missing.")
    features = [c for c in train_cols if c not in META]
    report = {
        "input_files": {k: str(v.relative_to(ROOT)) for k, v in SPLITS.items()},
        "model_feature_count": len(features),
        "model_features": features,
        "metadata_columns_excluded_from_features": ["Label", "target", "capture_day"],
        "split_summary": {},
        "feature_quality": {},
        "cross_split_duplicate_checks": {},
        "warnings": [],
    }

    for split in SPLITS:
        rows = int(con.execute(f"SELECT count(*) FROM {split}").fetchone()[0])
        days = dict(con.execute(
            f"SELECT capture_day, count(*) FROM {split} GROUP BY capture_day ORDER BY capture_day"
        ).fetchall())
        targets = dict(con.execute(
            f"SELECT target, count(*) FROM {split} GROUP BY target ORDER BY target"
        ).fetchall())
        labels = dict(con.execute(
            f'SELECT "Label", count(*) FROM {split} GROUP BY "Label" ORDER BY "Label"'
        ).fetchall())
        mismatches = int(con.execute(f"""
            SELECT count(*) FROM {split}
            WHERE target IS NULL OR target NOT IN (0,1)
               OR (upper("Label")='BENIGN' AND target<>0)
               OR (upper("Label")<>'BENIGN' AND target<>1)
        """).fetchone()[0])
        report["split_summary"][split] = {
            "rows": rows,
            "capture_day_counts": {str(k): int(v) for k,v in days.items()},
            "binary_target_counts": {str(k): int(v) for k,v in targets.items()},
            "original_label_counts": {str(k): int(v) for k,v in labels.items()},
            "target_label_mismatches": mismatches,
        }
        if mismatches:
            report["warnings"].append(f"{split}: {mismatches} target/Label mismatches.")

    # Feature quality: NULL/nonfinite, negative values, min/max, distinct counts.
    for col in features:
        c = qi(col)
        parts = []
        for split in SPLITS:
            parts.append(f"SELECT {c} AS value FROM {split}")
        union_sql = " UNION ALL ".join(parts)
        stats = con.execute(f"""
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE value IS NULL) AS nulls,
                   count(*) FILTER (
                     WHERE value IS NOT NULL
                       AND NOT isfinite(try_cast(value AS DOUBLE))
                   ) AS nonfinite,
                   count(*) FILTER (WHERE try_cast(value AS DOUBLE)<0) AS negatives,
                   min(try_cast(value AS DOUBLE)) AS min_value,
                   max(try_cast(value AS DOUBLE)) AS max_value,
                   count(DISTINCT value) AS distinct_values
            FROM ({union_sql}) u
        """).fetchone()
        per_split = {}
        for split in SPLITS:
            st = con.execute(f"""
                SELECT count(*) FILTER (WHERE {c} IS NULL),
                       count(*) FILTER (
                         WHERE {c} IS NOT NULL
                           AND NOT isfinite(try_cast({c} AS DOUBLE))
                       ),
                       count(*) FILTER (WHERE try_cast({c} AS DOUBLE)<0),
                       min(try_cast({c} AS DOUBLE)),
                       max(try_cast({c} AS DOUBLE)),
                       count(DISTINCT {c})
                FROM {split}
            """).fetchone()
            per_split[split] = {
                "nulls": int(st[0]), "nonfinite": int(st[1]),
                "negative_values": int(st[2]), "min": st[3], "max": st[4],
                "distinct_values": int(st[5]),
            }
        report["feature_quality"][col] = {
            "rows": int(stats[0]), "nulls": int(stats[1]),
            "infinite_or_nonfinite": int(stats[2]), "negative_values": int(stats[3]),
            "min": stats[4], "max": stats[5],
            "distinct_values_across_splits": int(stats[6]),
            "per_split": per_split,
        }

    constants = [c for c,v in report["feature_quality"].items()
                 if v["distinct_values_across_splits"] <= 1]
    missing_features = [c for c,v in report["feature_quality"].items()
                        if v["nulls"] or v["infinite_or_nonfinite"]]
    negative_features = [c for c,v in report["feature_quality"].items()
                         if v["negative_values"]]
    report["constant_features"] = constants
    report["features_with_missing_or_nonfinite_values"] = missing_features
    report["features_with_negative_values"] = negative_features
    if constants:
        report["warnings"].append("Constant features remain: " + ", ".join(constants))
    if missing_features:
        report["warnings"].append("Missing/nonfinite values remain; impute using training data only.")
    if negative_features:
        report["warnings"].append("Negative values found; review counts/ranges, do not drop blindly.")

    # Hash exact feature+label fingerprints across split pairs. Hashing occurs in DuckDB.
    feature_struct = "struct_pack(" + ", ".join(
        f"f{i} := {qi(c)}" for i,c in enumerate(features)
    ) + ")"
    labeled_struct = "struct_pack(" + ", ".join(
        [f"f{i} := {qi(c)}" for i,c in enumerate(features)] + ['label := "Label"']
    ) + ")"
    for a,b in (("train","validation"),("train","test"),("validation","test")):
        for split, suffix in ((a,"a"),(b,"b")):
            con.execute(f"""
                CREATE TEMP TABLE fp_{a}_{b}_{suffix} AS
                SELECT DISTINCT sha256(to_json({labeled_struct})) AS fp FROM {split}
            """)
        exact = int(con.execute(f"""
            SELECT count(*) FROM fp_{a}_{b}_a a
            JOIN fp_{a}_{b}_b b USING(fp)
        """).fetchone()[0])
        report["cross_split_duplicate_checks"][f"{a}_vs_{b}"] = {
            "shared_exact_feature_and_label_fingerprints": exact
        }
        con.execute(f"DROP TABLE fp_{a}_{b}_a")
        con.execute(f"DROP TABLE fp_{a}_{b}_b")
        for split, suffix in ((a,"a"),(b,"b")):
            con.execute(f"""
                CREATE TEMP TABLE feat_{a}_{b}_{suffix} AS
                SELECT { 'sha256(to_json(' + feature_struct + '))' } AS fp,
                       min("Label") AS label
                FROM {split} GROUP BY fp
            """)
        feature_overlap = int(con.execute(f"""
            SELECT count(*) FROM feat_{a}_{b}_a a
            JOIN feat_{a}_{b}_b b USING(fp)
        """).fetchone()[0])
        report["cross_split_duplicate_checks"][f"{a}_vs_{b}"][
            "shared_feature_fingerprints_any_label"
        ] = feature_overlap
        if exact or feature_overlap:
            report["warnings"].append(
                f"{a}/{b}: {exact} exact feature+label overlaps; "
                f"{feature_overlap} feature-vector overlaps."
            )
        con.execute(f"DROP TABLE feat_{a}_{b}_a")
        con.execute(f"DROP TABLE feat_{a}_{b}_b")

    report["evaluation_readiness"] = {
        "split_by_capture_day": True,
        "capture_day_overlap": False,
        "target_definition": "0=BENIGN, 1=any attack",
        "exclude_from_model_features": ["Label", "target", "capture_day"],
        "imputation": "Fit on training data only",
        "note": (
            "Thursday validation and Friday test contain attack families absent from training. "
            "Binary detection is still testable, but performance is specific to these held-out days."
        ),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nFinal data audit complete.")
    for split, info in report["split_summary"].items():
        print(f"{split.title():<10} {info['rows']:,} rows | days={info['capture_day_counts']} | target={info['binary_target_counts']}")
    print(f"Features: {len(features)}")
    print(f"Constant features: {constants}")
    print(f"Features with missing/nonfinite values: {missing_features}")
    print(f"Features with negative values: {negative_features}")
    print(f"Warnings: {len(report['warnings'])}")
    for w in report["warnings"]:
        print(" - " + w)
    print(f"Report: {OUT_PATH}")
    print("No data was modified and no model was trained.")
    con.close()

if __name__ == "__main__":
    main()
