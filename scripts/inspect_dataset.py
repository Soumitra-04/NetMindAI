
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data/raw/MachineLearningCVE")
CHUNK_SIZE = 100_000


def inspect_csv(path: Path) -> None:
    print("\n" + "=" * 80)
    print(f"FILE: {path.name}")
    print(f"SIZE: {path.stat().st_size / (1024**2):.2f} MB")

    try:
        header = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
        columns = [str(col).strip() for col in header.columns]

        print(f"COLUMNS: {len(columns)}")
        print("COLUMN NAMES:")
        for col in columns:
            print(f"  - {col}")

        label_col = next(
            (col for col in columns if col.lower() == "label"),
            None,
        )

        if label_col is None:
            print("WARNING: No Label column found.")
            return

        label_counts = {}
        total_rows = 0
        missing_cells = 0
        infinite_cells = 0
        duplicate_rows_within_chunks = 0

        for chunk in pd.read_csv(
            path,
            chunksize=CHUNK_SIZE,
            encoding="utf-8-sig",
            low_memory=False,
        ):
            chunk.columns = [str(col).strip() for col in chunk.columns]
            total_rows += len(chunk)

            counts = chunk[label_col].fillna("<MISSING>").value_counts()
            for label, count in counts.items():
                label_counts[str(label)] = (
                    label_counts.get(str(label), 0) + int(count)
                )

            missing_cells += int(chunk.isna().sum().sum())

            numeric = chunk.select_dtypes(include="number")
            infinite_cells += int(numeric.isin([float("inf"), float("-inf")]).sum().sum())

            duplicate_rows_within_chunks += int(chunk.duplicated().sum())

        print(f"\nTOTAL ROWS: {total_rows:,}")
        print(f"MISSING CELLS: {missing_cells:,}")
        print(f"INFINITE NUMERIC VALUES: {infinite_cells:,}")
        print(
            "DUPLICATES WITHIN INDIVIDUAL CHUNKS: "
            f"{duplicate_rows_within_chunks:,}"
        )
        print("\nLABEL DISTRIBUTION:")
        for label, count in sorted(
            label_counts.items(), key=lambda item: -item[1]
        ):
            print(f"  {label}: {count:,} ({count / total_rows:.2%})")

    except Exception as exc:
        print(f"ERROR inspecting {path.name}: {exc}")


def main() -> None:
    files = sorted(DATA_DIR.glob("*.csv"))

    if not files:
        print(f"No CSV files found in {DATA_DIR.resolve()}")
        return

    print(f"Found {len(files)} CSV files in {DATA_DIR.resolve()}")

    for path in files:
        inspect_csv(path)


if __name__ == "__main__":
    main()
