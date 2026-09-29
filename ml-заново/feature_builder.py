"""Build the model feature row from a channel passport and event history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping, Sequence

from inference import MODEL_FEATURES


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_model_features(request: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one channel passport and causal history into model features."""
    channel = request.get("channel")
    events = request.get("history", [])
    if not isinstance(channel, Mapping):
        raise ValueError("channel обязателен")
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise ValueError("history должен быть массивом событий")
    as_of = _timestamp(request.get("as_of"))
    current_hour = as_of.replace(minute=0, second=0, microsecond=0)
    parsed = []
    for event in events:
        if not isinstance(event, Mapping) or "timestamp" not in event:
            raise ValueError("каждое событие должно содержать timestamp")
        timestamp = _timestamp(event["timestamp"])
        if timestamp < as_of:
            parsed.append((timestamp, event))
    parsed.sort(key=lambda item: item[0])
    current = [item for item in parsed if current_hour <= item[0] < current_hour + timedelta(hours=1)]
    if any(bool(event.get("alarm")) for _, event in current):
        raise ValueError("нельзя прогнозировать новую тревогу в уже тревожном часу")

    numeric_values = [
        number for _, event in current
        if (number := _number(event.get("value"))) is not None and number != -1
    ]
    sensor = str(channel.get("sensor_type", "unknown"))
    current_methane = max(numeric_values) if "газ" in sensor.lower() and numeric_values else None
    prior_events = [(timestamp, event) for timestamp, event in parsed if timestamp < current_hour]
    previous_hour = prior_events[-1][0].replace(minute=0, second=0, microsecond=0) if prior_events else None
    previous_values = [
        number for timestamp, event in prior_events
        if previous_hour <= timestamp < previous_hour + timedelta(hours=1)
        if (number := _number(event.get("value"))) is not None and number != -1
    ] if previous_hour else []
    previous_methane = max(previous_values) if current_methane is not None and previous_values else None
    hours_since_previous = (current_hour - previous_hour).total_seconds() / 3600 if previous_hour else None
    last_alarm_hour = next(
        (timestamp.replace(minute=0, second=0, microsecond=0)
         for timestamp, event in reversed(prior_events) if bool(event.get("alarm"))), None
    )

    def alarm_count(hours: int) -> int:
        start = current_hour - timedelta(hours=hours)
        return len({timestamp.replace(minute=0, second=0, microsecond=0)
                    for timestamp, event in prior_events
                    if start <= timestamp < current_hour and bool(event.get("alarm"))})

    values = {
        "sensor": sensor,
        "sys": channel.get("engineering_system", "unknown"),
        "objkind": channel.get("object_kind", "unknown"),
        "parent": channel.get("parent", "unknown"),
        "n_events": len(current),
        "num_mean": sum(numeric_values) / len(numeric_values) if numeric_values else None,
        "num_max": max(numeric_values) if numeric_values else None,
        "methane": current_methane,
        "methane_delta": current_methane - previous_methane if current_methane is not None and previous_methane is not None and hours_since_previous <= 48 else None,
        "has_1970": any("1970" in str(event.get("value")) for _, event in current),
        "hour_of_day": current_hour.hour,
        "dow": current_hour.weekday(),
        "month": current_hour.month,
        "is_weekend": current_hour.weekday() >= 5,
        "h_since_prev": hours_since_previous,
        "hours_since_alarm": (current_hour - last_alarm_hour).total_seconds() / 3600 if last_alarm_hour else None,
        "alarms_24h": alarm_count(24),
        "alarms_72h": alarm_count(72),
        "alarms_168h": alarm_count(168),
    }
    if list(values) != MODEL_FEATURES:
        raise ValueError("feature builder вернул неожиданный набор признаков")
    return values
