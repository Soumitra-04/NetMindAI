
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path("data/raw/MachineLearningCVE")
CHUNK_SIZE = 50_000
LABEL_COL = "Label"


def audit_file(path: Path, reference_columns: list[str] | None):
    print(f"\n{'=' * 80}\n{path.name}")
    print(f"File size: {path.stat().st_size / 1024**2:.2f} MB")

    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
    columns = [str(c).strip() for c in header.columns]

    if reference_columns is not None:
        print("Column names/order match first file:",
              columns == reference_columns)

        if set(columns) != set(reference_columns):
            print("Columns only in this file:",
                  sorted(set(columns) - set(reference_columns)))
            print("Columns missing from this file:",
                  sorted(set(reference_columns) - set(columns)))

    if LABEL_COL not in columns:
        print("ERROR: Label column missing.")
        return columns, None

    labels = Counter()
    rows = 0
    missing_by_col = Counter()
    infinite_by_col = Counter()
    nonnumeric_by_col = Counter()
    numeric_min = {}
    numeric_max = {}
    numeric_nonmissing = Counter()
    constant_candidates = set(columns)
    duplicate_count = 0

    for chunk in pd.read_csv(
        path,
        chunksize=CHUNK_SIZE,
        encoding="utf-8-sig",
        low_memory=False,
    ):
        chunk.columns = [str(c).strip() for c in chunk.columns]
        rows += len(chunk)

        labels.update(
            chunk[LABEL_COL].fillna("<MISSING LABEL>").astype(str).value_counts().to_dict()
        )

        missing_by_col.update(
            chunk.isna().sum().to_dict()
        )

        # This counts exact duplicates within each chunk only.
        duplicate_count += int(chunk.duplicated().sum())

        for col in columns:
            if col == LABEL_COL:
                continue

            raw = chunk[col]
            numeric = pd.to_numeric(raw, errors="coerce")

            nonnumeric = raw.notna() & numeric.isna()
            nonnumeric_by_col[col] += int(nonnumeric.sum())

            values = numeric.to_numpy(dtype="float64", na_value=np.nan)
            finite_mask = np.isfinite(values)
            infinite_by_col[col] += int(np.isinf(values).sum())

            finite_values = values[finite_mask]
            if len(finite_values):
                low = float(finite_values.min())
                high = float(finite_values.max())

                numeric_min[col] = min(numeric_min.get(col, low), low)
                numeric_max[col] = max(numeric_max.get(col, high), high)
                numeric_nonmissing[col] += len(finite_values)

                if low != high:
                    constant_candidates.discard(col)

    print(f"\nRows: {rows:,}")
    print(f"Exact duplicates within chunks: {duplicate_count:,}")

    print("\nLabels:")
    for label, count in labels.most_common():
        print(f"  {label}: {count:,} ({count / rows:.3%})")

    print("\nColumns with missing values:")
    for col, count in missing_by_col.most_common():
        if count:
            print(f"  {col}: {count:,}")

    print("\nColumns with infinite values:")
    for col, count in infinite_by_col.most_common():
        if count:
            print(f"  {col}: {count:,}")

    print("\nColumns with non-numeric values:")
    for col, count in nonnumeric_by_col.most_common():
        if count:
            print(f"  {col}: {count:,}")

    print("\nNumeric feature ranges (finite values only):")
    for col in columns:
        if col in numeric_min:
            print(
                f"  {col}: min={numeric_min[col]:.6g}, "
                f"max={numeric_max[col]:.6g}, "
                f"valid={numeric_nonmissing[col]:,}"
            )

    print("\nPossible constant columns in this file:")
    print("  " + ", ".join(sorted(constant_candidates - {LABEL_COL}))
          if constant_candidates - {LABEL_COL} else "  None detected")

    return columns, labels


def main():
    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {DATA_DIR.resolve()}")

    print(f"Found {len(files)} CSV files.")
    reference_columns = None
    combined_labels = Counter()

    for path in files:
        columns, labels = audit_file(path, reference_columns)

        if reference_columns is None:
            reference_columns = columns

        if labels is not None:
            combined_labels.update(labels)

    total = sum(combined_labels.values())
    print(f"\n{'=' * 80}\nCOMBINED LABEL DISTRIBUTION")
    print(f"Total rows: {total:,}")

    for label, count in combined_labels.most_common():
        print(f"  {label}: {count:,} ({count / total:.3%})")


if __name__ == "__main__":
    main()
