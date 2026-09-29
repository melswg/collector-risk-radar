import sys
from pathlib import Path
import pytest


sys.path.insert(0, str(Path("ml-заново").resolve()))
from feature_builder import build_model_features
from inference import MODEL_FEATURES


def test_raw_history_becomes_model_features():
    request = {
        "as_of": "2026-08-01T12:30:00",
        "channel": {
            "id": 120578,
            "sensor_type": "Газовый датчик",
            "engineering_system": "газ",
            "object_kind": "объект",
            "parent": "комплекс",
        },
        "history": [
            {"timestamp": "2026-08-01T10:00:00", "alarm": False, "value": "0.02"},
            {"timestamp": "2026-08-01T11:10:00", "alarm": False, "value": "0.03"},
            {"timestamp": "2026-08-01T12:10:00", "alarm": False, "value": "0.04"},
        ],
    }

    features = build_model_features(request)

    assert list(features) == MODEL_FEATURES
    assert features["methane"] == 0.04
    assert features["alarms_24h"] == 0


def test_current_alarm_is_not_sent_as_future_prediction():
    request = {
        "as_of": "2026-08-01T12:30:00",
        "channel": {
            "id": 1,
            "sensor_type": "Датчик дыма",
            "engineering_system": "пожарная охрана",
            "object_kind": "объект",
            "parent": "комплекс",
        },
        "history": [
            {"timestamp": "2026-08-01T12:20:00", "alarm": True, "value": "Обнаружен дым"},
        ],
    }

    try:
        build_model_features(request)
    except ValueError as error:
        assert "тревожном часу" in str(error)
    else:
        raise AssertionError("current alarm must be rejected")


def test_offset_future_event_is_excluded():
    features = build_model_features({
        "as_of": "2026-08-01T12:30:00+03:00",
        "channel": {"sensor_type": "Газовый датчик"},
        "history": [
            {"timestamp": "2026-08-01T10:00:00Z", "value": "0.9", "alarm": True},
            {"timestamp": "2026-08-01T09:10:00Z", "value": "0.04", "alarm": False},
        ],
    })
    assert features["n_events"] == 1
    assert features["num_max"] == 0.04
    assert features["alarms_24h"] == 0


def test_features_match_training_hourly_example():
    features = build_model_features({
        "as_of": "2026-08-01T12:30:00Z",
        "channel": {"sensor_type": "Газовый датчик", "engineering_system": "газ", "object_kind": "объект", "parent": "комплекс"},
        "history": [
            {"timestamp": "2026-08-01T10:05:00Z", "alarm": True, "value": "0.06"},
            {"timestamp": "2026-08-01T10:50:00Z", "alarm": True, "value": "0.07"},
            {"timestamp": "2026-08-01T11:05:00Z", "alarm": False, "value": "0.03"},
            {"timestamp": "2026-08-01T11:45:00Z", "alarm": False, "value": "0.05"},
            {"timestamp": "2026-08-01T12:10:00Z", "alarm": False, "value": "0.04"},
        ],
    })
    expected = dict(zip(MODEL_FEATURES, [
        "Газовый датчик", "газ", "объект", "комплекс", 1, 0.04, 0.04,
        0.04, -0.01, False, 12, 5, 8, True, 1.0, 2.0, 1, 1, 1,
    ]))
    assert features["methane_delta"] == pytest.approx(-0.01)
    assert {key: value for key, value in features.items() if key != "methane_delta"} == {key: value for key, value in expected.items() if key != "methane_delta"}


def test_methane_delta_expires_after_48_hours():
    features = build_model_features({
        "as_of": "2026-08-04T12:30:00Z",
        "channel": {"sensor_type": "Газовый датчик"},
        "history": [
            {"timestamp": "2026-08-01T11:00:00Z", "value": "0.03", "alarm": False},
            {"timestamp": "2026-08-04T12:00:00Z", "value": "0.04", "alarm": False},
        ],
    })
    assert features["h_since_prev"] == 73
    assert features["methane_delta"] is None
