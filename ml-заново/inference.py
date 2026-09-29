"""Инференс модели новой тревоги и классификация наблюдаемого состояния."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import joblib
import pandas as pd
from catboost import CatBoostClassifier


MODEL_FEATURES = [
    "sensor", "sys", "objkind", "parent", "n_events", "num_mean",
    "num_max", "methane", "methane_delta", "has_1970", "hour_of_day",
    "dow", "month", "is_weekend", "h_since_prev", "hours_since_alarm",
    "alarms_24h", "alarms_72h", "alarms_168h",
]
CATEGORICAL_FEATURES = {"sensor", "sys", "objkind", "parent"}


@dataclass(frozen=True)
class ObservationClassification:
    categories: tuple[str, ...]
    is_technical_fault: bool
    is_critical_risk: bool
    source: str


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip().lower()


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def classify_observation(
    *, sensor_type: Any = None, state: Any = None, value: Any = None,
    alarm: bool | None = None,
) -> ObservationClassification:
    sensor = _text(sensor_type)
    state_text = _text(state)
    value_text = _text(value)
    text = f"{state_text} {value_text}"
    numeric_value = _number(value)
    negative_state = re.search(r"нет|не обнаруж|норма|исправен|замкнут", text)
    categories: list[str] = []

    if re.search(r"обнаружен дым|дым обнаружен|пожар", text) and not negative_state:
        categories.append("fire")
    gas_alarm = (
        re.search(r"обнаружен газ|газ обнаружен|метан", text) and not negative_state
    ) or ("газ" in sensor and numeric_value is not None and numeric_value >= 1.0)
    if gas_alarm:
        categories.append("gas")
    if re.search(r"затоплен|обнаружено затопление|вода обнаружена", text):
        categories.append("flood")
    if "не замкнут" in state_text:
        if re.search(r"теплов|ручн", sensor):
            categories.append("fire")
        elif re.search(r"затоп|вода", sensor):
            categories.append("flood")
    if re.search(
        r"люк открыт|дверь открыта|аварийн\w* выход|обнаружено движение|"
        r"движение обнаружено|рычаг сдернут|стекло разбито|проникновение", text
    ) and not negative_state:
        categories.append("security")
    if re.search(r"температур|перегрев|переохлаж|жар", text) and not negative_state:
        categories.append("temperature")

    technical_fault = bool(
        re.search(r"неисправ|неопредел|не определ|обесточ|отключ|выключ", text)
        or re.search(r"(?:01[./-]01[./-]1970|1970[./-]01[./-]01)", value_text)
        or ("газ" in sensor and numeric_value is not None and numeric_value < 0)
    )
    if technical_fault:
        categories.append("fault")
    if not categories and alarm is False:
        categories.append("normal")
    if not categories:
        categories.append("unknown")

    return ObservationClassification(
        categories=tuple(dict.fromkeys(categories)),
        is_technical_fault=technical_fault,
        is_critical_risk=bool(set(categories) & {"fire", "gas", "flood", "security", "temperature"}),
        source="customer_rules",
    )


class AlarmPredictor:
    """Прогнозирует новую тревожную запись в следующие 24 часа."""

    def __init__(self, model_path: str | Path, calibrator_path: str | Path | None = None):
        self.model = CatBoostClassifier()
        self.model.load_model(str(model_path))
        if list(self.model.feature_names_) != MODEL_FEATURES:
            raise ValueError("Модель обучена на другом наборе признаков")
        calibrator_path = calibrator_path or Path(model_path).with_name(
            "new_alarm_channel_isotonic.joblib"
        )
        self.calibrator = joblib.load(calibrator_path) if Path(calibrator_path).exists() else None

    def predict(self, features: Mapping[str, Any]) -> dict[str, Any]:
        missing = [name for name in MODEL_FEATURES if name not in features]
        if missing:
            raise ValueError("Не хватает признаков: " + ", ".join(missing))
        frame = pd.DataFrame([{name: features[name] for name in MODEL_FEATURES}])
        for name in CATEGORICAL_FEATURES:
            frame[name] = frame[name].fillna("unknown").astype(str)
        for name in set(MODEL_FEATURES) - CATEGORICAL_FEATURES:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        raw_probability = float(self.model.predict_proba(frame)[0, 1])
        probability = raw_probability
        if self.calibrator is not None:
            probability = float(self.calibrator.predict([raw_probability])[0])
        return {
            "target": "new_alarm_24h",
            "predicted_type": "unknown_pending_dispatcher",
            "probability": probability,
            "raw_probability": raw_probability,
            "probability_calibrated": self.calibrator is not None,
            "horizon_hours": 24,
            "source": "catboost:new_alarm_24h",
            "decision_required": True,
        }


def build_prediction_response(*, predictor: AlarmPredictor, features: Mapping[str, Any], observation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    response = predictor.predict(features)
    if observation is not None:
        classification = classify_observation(**observation)
        response["observed_classification"] = {
            "categories": list(classification.categories),
            "critical_risk": classification.is_critical_risk,
            "technical_fault": classification.is_technical_fault,
            "source": classification.source,
        }
    return response
