"""Детерминированная диагностика и модель-независимая оценка."""
from datetime import datetime, timedelta
import numpy as np
from backend.db import utc


def sensor_health(points: list, as_of: datetime, type_code: str = 'temperature', expected_seconds: int = 300, neighbor_mean: float | None = None) -> dict:
    clean = [(utc(t), float(v)) for t, v in points if v is not None and utc(t) <= utc(as_of)]
    clean.sort()
    if not clean:
        return dict(status='critical', flatline=False, dropout_rate=1.0, chatter=False, noise_ratio=0.0, drift=0.0, reasons=['Нет данных'])
    values = np.array([v for _, v in clean])
    duration = max(expected_seconds, (utc(as_of) - clean[0][0]).total_seconds())
    gap = (utc(as_of) - clean[-1][0]).total_seconds()
    dropout = min(1.0, max(0.0, 1 - len(clean) / (duration / expected_seconds + 1), gap / duration))
    analog = type_code in ('temperature', 'gas')
    flatline = bool(analog and len(values) >= 12 and np.ptp(values[-12:]) < 0.001)
    chatter = bool(not analog and len(values) >= 12 and np.count_nonzero(np.diff(values[-12:])) >= 10)
    noise = float(np.std(np.diff(values))) if len(values) > 2 and analog else 0.0
    drift = abs(float(np.mean(values[-12:])) - neighbor_mean) if neighbor_mean is not None and analog else 0.0
    reasons = []
    for condition, text in [(flatline, 'Залипание'), (dropout > 0.3 or gap > expected_seconds * 3, 'Потеря связи'), (chatter, 'Дребезг'), (noise > 3, 'Шум'), (drift > 8, 'Дрейф')]:
        if condition:
            reasons.append(text)
    return dict(status='critical' if dropout > 0.7 or flatline else 'warning' if reasons else 'ok', flatline=flatline, dropout_rate=round(dropout, 4), chatter=chatter, noise_ratio=round(noise, 4), drift=round(drift, 4), reasons=reasons)


def is_expected(ts: datetime, works: list[dict], tolerance: int = 15) -> bool:
    return any(w.get('status') in ('in_progress', 'approved') and utc(datetime.fromisoformat(w['from'])) - timedelta(minutes=tolerance) <= utc(ts) <= utc(datetime.fromisoformat(w['to'])) + timedelta(minutes=tolerance) for w in works)


def label_window(as_of: datetime, horizon_h: int, incidents: list[datetime], observation_end: datetime) -> int | None:
    end = utc(as_of) + timedelta(hours=horizon_h)
    if end > utc(observation_end):
        return None
    return int(any(utc(as_of) < utc(t) <= end for t in incidents))


def metrics(labels: list[int], probabilities: list[float], threshold: float = 0.5, object_days: float = 1.0, lead_times: list[float] | None = None) -> dict:
    if not labels:
        return dict(count=0, precision=None, recall=None, f1=None, pr_auc=None, brier=None, lead_time_h=None, false_alarms_per_object_day=None)
    y, p = np.asarray(labels), np.asarray(probabilities)
    pred = p >= threshold
    tp, fp, fn = int(np.sum(pred & (y == 1))), int(np.sum(pred & (y == 0))), int(np.sum(~pred & (y == 1)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    # Одинаковые вероятности группируются: результат не зависит от порядка строк.
    area, previous_recall = 0.0, 0.0
    for cut in sorted(set(probabilities), reverse=True):
        selected = p >= cut
        hits = int(np.sum(y[selected]))
        r = hits / int(np.sum(y)) if np.sum(y) else 0.0
        area += (r - previous_recall) * hits / int(np.sum(selected))
        previous_recall = r
    return dict(count=len(y), positives=int(np.sum(y)), tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=2 * precision * recall / (precision + recall) if precision + recall else 0.0, pr_auc=area if np.sum(y) else None, pr_auc_method='average_precision_step', brier=float(np.mean((p-y)**2)), lead_time_h=float(np.mean(lead_times)) if lead_times else None, false_alarms_per_object_day=fp / max(object_days, 1e-9))
