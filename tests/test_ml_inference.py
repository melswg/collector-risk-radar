import importlib.util
from pathlib import Path
import sys
import json
import pytest


spec = importlib.util.spec_from_file_location("ml_inference", Path("ml-заново/inference.py"))
ml_inference = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = ml_inference
spec.loader.exec_module(ml_inference)


def test_customer_rules():
    result = ml_inference.classify_observation(sensor_type="КД АВ", state="Обнаружено движение", alarm=True)
    assert result.is_critical_risk and "security" in result.categories
    assert not ml_inference.classify_observation(sensor_type="Газовый датчик", value="0.03", alarm=False).is_critical_risk
    assert "gas" in ml_inference.classify_observation(sensor_type="Газовый датчик", value="1.0", alarm=True).categories


def test_model_contract():
    features = {
        "sensor": "Газовый датчик", "sys": "газ", "objkind": "объект", "parent": "комплекс",
        "n_events": 10, "num_mean": 0.02, "num_max": 0.03, "methane": 0.03,
        "methane_delta": 0.01, "has_1970": 0, "hour_of_day": 12, "dow": 1, "month": 8,
        "is_weekend": 0, "h_since_prev": 1, "hours_since_alarm": 50,
        "alarms_24h": 0, "alarms_72h": 0, "alarms_168h": 1,
    }
    result = ml_inference.AlarmPredictor("ml-заново/models/incident_24h.cbm").predict(features)
    assert result["target"] == "new_alarm_24h"
    assert result["predicted_type"] == "unknown_pending_dispatcher"
    assert result["probability_calibrated"] is True
    assert 0 <= result["probability"] <= 1


def test_raw_fixture_to_calibrated_probability():
    from feature_builder import build_model_features

    request = json.loads(Path("tests/fixtures/ml_channel_example.json").read_text())
    features = build_model_features(request)
    result = ml_inference.AlarmPredictor("ml-заново/models/incident_24h.cbm").predict(features)
    assert len(features) == 19
    assert result["probability_calibrated"] is True
    assert result["probability"] == pytest.approx(0.03470437017994859, abs=1e-9)
