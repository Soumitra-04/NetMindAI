"""Random Forest model inference service for intrusion detection.

Compatibility Note:
-------------------
The trained baseline model (models/baseline_random_forest.joblib) expects
67 CICIDS-style flow features (e.g., 'Flow Duration', 'Total Fwd Packets',
'Flow Bytes/s', 'Flow IAT Mean', 'FIN Flag Count', 'Init_Win_bytes_forward').

The existing NetMind network simulator operates at an abstract graph topology
level, modeling nodes, links, and high-level traffic flow rates (packets per
second, packet size in bytes, offered Mbps, shortest-path latency).

The simulator does NOT generate packet-level timings, inter-arrival times, or
TCP flag statistics. In accordance with the project specification:
- Features are NEVER fabricated or synthetic-zero-filled.
- Unrelated simulator metrics are NEVER fed into the model.
- This inference service is maintained independently to evaluate valid
  CICIDS-format flow records, and is NOT wired to live simulator detection.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


class ModelInferenceService:
    """Load and execute inference on the trained baseline Random Forest model."""

    DEFAULT_ARTIFACT_REL_PATH = Path("models") / "baseline_random_forest.joblib"

    def __init__(self, model_path: str | Path | None = None) -> None:
        if model_path is None:
            # Resolve relative to the repository root (two levels up from backend/services)
            repo_root = Path(__file__).resolve().parents[2]
            self.model_path = repo_root / self.DEFAULT_ARTIFACT_REL_PATH
        else:
            self.model_path = Path(model_path)

        self._load_artifact()

    def _load_artifact(self) -> None:
        """Load and validate the model artifact dictionary once at initialization."""
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {self.model_path}. "
                "Ensure models/baseline_random_forest.joblib exists."
            )

        try:
            bundle = joblib.load(self.model_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load model artifact from {self.model_path}: {exc}"
            ) from exc

        if not isinstance(bundle, dict):
            raise ValueError(
                f"Model artifact at {self.model_path} must be a dictionary bundle."
            )

        required_keys = {"model", "threshold", "feature_columns"}
        missing_keys = required_keys - set(bundle.keys())
        if missing_keys:
            raise ValueError(
                f"Model artifact missing required keys: {sorted(missing_keys)}"
            )

        self.model = bundle["model"]
        if not hasattr(self.model, "predict_proba"):
            raise ValueError(
                "Model estimator in artifact must provide predict_proba method."
            )

        # Silence verbose parallel joblib output during inference
        if hasattr(self.model, "verbose"):
            self.model.verbose = 0

        self.threshold = float(bundle["threshold"])
        self.feature_columns: list[str] = list(bundle["feature_columns"])
        self.target_mapping: dict[str, int] = dict(
            bundle.get("target_mapping", {"BENIGN": 0, "ATTACK": 1})
        )
        self.model_name: str = str(
            bundle.get("model_name", type(self.model).__name__)
        )
        self.random_state: Any = bundle.get("random_state", None)

        self._reverse_target_mapping: dict[int, str] = {
            v: k for k, v in self.target_mapping.items()
        }

    @property
    def feature_count(self) -> int:
        return len(self.feature_columns)

    @property
    def metadata(self) -> dict[str, Any]:
        """Return model metadata extracted from the trained artifact."""
        return {
            "model_name": self.model_name,
            "feature_count": self.feature_count,
            "threshold": self.threshold,
            "target_mapping": self.target_mapping,
            "random_state": self.random_state,
            "artifact_path": str(self.model_path),
        }

    def _validate_dict_sample(self, sample: dict[str, Any]) -> list[float]:
        """Validate a single dictionary sample and return an ordered float vector."""
        if not isinstance(sample, dict):
            raise TypeError(
                f"Sample must be a dictionary, got {type(sample).__name__}."
            )

        sample_keys = set(sample.keys())
        expected_keys = set(self.feature_columns)

        missing = expected_keys - sample_keys
        if missing:
            raise ValueError(
                f"Missing {len(missing)} required feature(s): {sorted(missing)}"
            )

        extra = sample_keys - expected_keys
        if extra:
            raise ValueError(
                f"Unexpected extra feature(s): {sorted(extra)}"
            )

        ordered_values: list[float] = []
        for feature in self.feature_columns:
            val = sample[feature]

            # Reject booleans specifically (isinstance(True, int) is True in Python)
            if isinstance(val, bool) or not isinstance(val, (int, float, np.number)):
                raise TypeError(
                    f"Feature '{feature}' must be numeric, got {type(val).__name__} ({val!r})."
                )

            val_float = float(val)
            if math.isnan(val_float) or math.isinf(val_float):
                raise ValueError(
                    f"Feature '{feature}' must be finite, got non-finite value: {val}."
                )

            ordered_values.append(val_float)

        return ordered_values

    def _prepare_matrix(
        self,
        inputs: dict[str, Any] | list[dict[str, Any]] | pd.DataFrame | np.ndarray,
    ) -> tuple[np.ndarray, bool]:
        """Validate inputs and convert to an (N, 67) float64 numpy matrix.

        Returns:
            A tuple of (feature_matrix, is_single_sample).
        """
        if isinstance(inputs, dict):
            ordered = self._validate_dict_sample(inputs)
            matrix = np.array([ordered], dtype=np.float64)
            return matrix, True

        if isinstance(inputs, list):
            if not inputs:
                raise ValueError("Input list cannot be empty.")
            rows = [self._validate_dict_sample(s) for s in inputs]
            matrix = np.array(rows, dtype=np.float64)
            return matrix, False

        if isinstance(inputs, pd.DataFrame):
            if inputs.empty:
                raise ValueError("Input DataFrame cannot be empty.")

            expected_keys = set(self.feature_columns)
            actual_keys = set(inputs.columns)

            missing = expected_keys - actual_keys
            if missing:
                raise ValueError(
                    f"Missing {len(missing)} required feature column(s): {sorted(missing)}"
                )

            extra = actual_keys - expected_keys
            if extra:
                raise ValueError(
                    f"Unexpected extra feature column(s): {sorted(extra)}"
                )

            # Reorder columns strictly matching feature_columns
            df_ordered = inputs[self.feature_columns]

            for col in self.feature_columns:
                if not pd.api.types.is_numeric_dtype(df_ordered[col]):
                    raise TypeError(
                        f"Feature column '{col}' must be numeric, got dtype {df_ordered[col].dtype}."
                    )

            arr = df_ordered.to_numpy(dtype=np.float64)
            if not np.isfinite(arr).all():
                raise ValueError("Input DataFrame contains non-finite values (NaN, Inf, or -Inf).")

            return arr, False

        if isinstance(inputs, np.ndarray):
            if inputs.ndim != 2 or inputs.shape[1] != self.feature_count:
                raise ValueError(
                    f"Expected 2D numpy array with shape (N, {self.feature_count}), "
                    f"got shape {inputs.shape}."
                )
            if not np.issubdtype(inputs.dtype, np.number) or inputs.dtype == bool:
                raise TypeError(
                    f"Array dtype must be numeric, got {inputs.dtype}."
                )
            if not np.isfinite(inputs).all():
                raise ValueError("Input numpy array contains non-finite values (NaN, Inf, or -Inf).")

            return inputs.astype(np.float64), False

        raise TypeError(
            f"Unsupported input type {type(inputs).__name__}. "
            "Supported types: dict, list[dict], pd.DataFrame, np.ndarray."
        )

    def predict(
        self,
        inputs: dict[str, Any] | list[dict[str, Any]] | pd.DataFrame | np.ndarray,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Run intrusion classification on validated CICIDS-style flow features.

        Args:
            inputs: Single sample dict, list of sample dicts, DataFrame, or numpy array.

        Returns:
            Dictionary (for single sample) or list of dictionaries containing:
            - prediction: 0 (BENIGN) or 1 (ATTACK)
            - label: "BENIGN" or "ATTACK"
            - attack_probability: float between 0.0 and 1.0
            - threshold: decision threshold applied from the artifact (0.3065)
            - model_metadata: dictionary of model metadata
        """
        matrix, is_single = self._prepare_matrix(inputs)
        df_matrix = pd.DataFrame(matrix, columns=self.feature_columns)

        probs = self.model.predict_proba(df_matrix)[:, 1]
        preds = (probs >= self.threshold).astype(int)

        results: list[dict[str, Any]] = []
        metadata = self.metadata

        for prob, pred in zip(probs, preds):
            label = self._reverse_target_mapping.get(pred, str(pred))
            results.append({
                "prediction": int(pred),
                "label": label,
                "attack_probability": round(float(prob), 6),
                "threshold": self.threshold,
                "model_metadata": metadata,
            })

        return results[0] if is_single else results
