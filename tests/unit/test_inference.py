"""Unit tests for the baseline Random Forest model inference service."""

from pathlib import Path
import math

import numpy as np
import pandas as pd
import pytest

from backend.services.inference_service import ModelInferenceService


@pytest.fixture(scope="module")
def inference_service() -> ModelInferenceService:
    return ModelInferenceService()


@pytest.fixture(scope="module")
def sample_valid_row(inference_service) -> dict[str, float]:
    """Extract a single valid sample from the cleaned test dataset."""
    test_csv_path = Path("data/processed/cleaned_final/test.csv")
    if test_csv_path.exists():
        df = pd.read_csv(test_csv_path, nrows=1)
        return {col: float(df[col].iloc[0]) for col in inference_service.feature_columns}

    # Fallback to zeros vector if test.csv is not present
    return {col: 0.0 for col in inference_service.feature_columns}


def test_inference_service_metadata(inference_service):
    """Verify the loaded artifact exposes expected metadata and preserved threshold."""
    meta = inference_service.metadata

    assert meta["model_name"] == "RandomForestClassifier"
    assert meta["feature_count"] == 67
    assert meta["threshold"] == pytest.approx(0.3065, abs=1e-4)
    assert meta["target_mapping"] == {"BENIGN": 0, "ATTACK": 1}
    assert meta["random_state"] == 42
    assert Path(meta["artifact_path"]).exists()


def test_valid_single_sample_inference(inference_service, sample_valid_row):
    """Verify single dictionary prediction produces complete structured output."""
    result = inference_service.predict(sample_valid_row)

    assert isinstance(result, dict)
    assert "prediction" in result
    assert result["prediction"] in (0, 1)
    assert "label" in result
    assert result["label"] in ("BENIGN", "ATTACK")
    assert "attack_probability" in result
    assert 0.0 <= result["attack_probability"] <= 1.0
    assert result["threshold"] == pytest.approx(0.3065, abs=1e-4)
    assert "model_metadata" in result
    assert result["model_metadata"]["feature_count"] == 67


def test_feature_order_invariance(inference_service, sample_valid_row):
    """Ensure dictionary feature order does not affect the prediction."""
    # Reverse the key order in the input dictionary
    reversed_sample = {k: sample_valid_row[k] for k in reversed(list(sample_valid_row.keys()))}

    res1 = inference_service.predict(sample_valid_row)
    res2 = inference_service.predict(reversed_sample)

    assert res1["prediction"] == res2["prediction"]
    assert res1["attack_probability"] == res2["attack_probability"]


def test_valid_batch_samples_inference(inference_service, sample_valid_row):
    """Verify batch prediction with a list of dictionaries."""
    batch = [sample_valid_row, sample_valid_row.copy()]
    results = inference_service.predict(batch)

    assert isinstance(results, list)
    assert len(results) == 2
    for item in results:
        assert item["prediction"] in (0, 1)
        assert item["threshold"] == pytest.approx(0.3065, abs=1e-4)


def test_valid_dataframe_inference(inference_service, sample_valid_row):
    """Verify inference accepts a pandas DataFrame."""
    df = pd.DataFrame([sample_valid_row, sample_valid_row])
    results = inference_service.predict(df)

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["prediction"] in (0, 1)


def test_valid_numpy_array_inference(inference_service, sample_valid_row):
    """Verify inference accepts a 2D numpy array."""
    vector = [sample_valid_row[col] for col in inference_service.feature_columns]
    matrix = np.array([vector, vector], dtype=np.float64)

    results = inference_service.predict(matrix)

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["prediction"] in (0, 1)


def test_inference_rejects_missing_features(inference_service, sample_valid_row):
    """Missing features must raise a ValueError indicating the missing columns."""
    bad_sample = sample_valid_row.copy()
    del bad_sample["Destination Port"]
    del bad_sample["Flow Duration"]

    with pytest.raises(ValueError, match="Missing 2 required feature"):
        inference_service.predict(bad_sample)


def test_inference_rejects_extra_features(inference_service, sample_valid_row):
    """Unexpected extra features must raise a ValueError."""
    bad_sample = sample_valid_row.copy()
    bad_sample["unrelated_sensor_reading"] = 42.0

    with pytest.raises(ValueError, match="Unexpected extra feature"):
        inference_service.predict(bad_sample)


def test_inference_rejects_empty_inputs(inference_service):
    """Empty batch inputs must raise ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        inference_service.predict([])

    with pytest.raises(ValueError, match="cannot be empty"):
        inference_service.predict(pd.DataFrame())


def test_inference_rejects_non_numeric_values(inference_service, sample_valid_row):
    """String, None, or boolean values must raise TypeError."""
    # String value
    bad_str = sample_valid_row.copy()
    bad_str["Destination Port"] = "eighty"
    with pytest.raises(TypeError, match="must be numeric"):
        inference_service.predict(bad_str)

    # None value
    bad_none = sample_valid_row.copy()
    bad_none["Flow Duration"] = None
    with pytest.raises(TypeError, match="must be numeric"):
        inference_service.predict(bad_none)

    # Boolean value (Python bool is subclass of int, so must be explicitly rejected)
    bad_bool = sample_valid_row.copy()
    bad_bool["Destination Port"] = True
    with pytest.raises(TypeError, match="must be numeric"):
        inference_service.predict(bad_bool)


def test_inference_rejects_non_finite_values(inference_service, sample_valid_row):
    """NaN, Inf, and -Inf values must raise ValueError."""
    bad_nan = sample_valid_row.copy()
    bad_nan["Flow Duration"] = float("nan")
    with pytest.raises(ValueError, match="must be finite"):
        inference_service.predict(bad_nan)

    bad_inf = sample_valid_row.copy()
    bad_inf["Flow Duration"] = float("inf")
    with pytest.raises(ValueError, match="must be finite"):
        inference_service.predict(bad_inf)

    bad_ninf = sample_valid_row.copy()
    bad_ninf["Flow Duration"] = float("-inf")
    with pytest.raises(ValueError, match="must be finite"):
        inference_service.predict(bad_ninf)


def test_inference_rejects_invalid_numpy_shapes(inference_service):
    """1D arrays or arrays with incorrect column counts must be rejected."""
    # 1D array
    arr_1d = np.zeros(67, dtype=np.float64)
    with pytest.raises(ValueError, match="Expected 2D numpy array"):
        inference_service.predict(arr_1d)

    # 2D array with wrong number of columns
    arr_wrong_cols = np.zeros((2, 10), dtype=np.float64)
    with pytest.raises(ValueError, match="Expected 2D numpy array"):
        inference_service.predict(arr_wrong_cols)


def test_missing_model_artifact_raises_file_not_found(tmp_path):
    """Non-existent model path must raise FileNotFoundError."""
    missing_path = tmp_path / "nonexistent_model.joblib"
    with pytest.raises(FileNotFoundError, match="Model artifact not found"):
        ModelInferenceService(model_path=missing_path)


def test_invalid_artifact_structure_raises_value_error(tmp_path):
    """Artifacts missing required bundle keys must raise ValueError."""
    import joblib

    bad_artifact = tmp_path / "corrupt_model.joblib"
    joblib.dump({"just_some_random_key": 123}, bad_artifact)

    with pytest.raises(ValueError, match="missing required keys"):
        ModelInferenceService(model_path=bad_artifact)
