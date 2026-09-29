"""Оценка калибровки и порога новой тревоги на отложенных годах.

Реконструкция: часовая витрина собрана `build_hourly_table.py` из годовых
архивах заказчика, потому что оригинальный `all_years_hourly.parquet` не
передан. Метрики относятся к этой реконструкции, а не к утраченной таблице.

Сплит как в `02_main.ipynb`: калибровка и порог на 2025, проверка на 2026.

Запуск: .venv/bin/python ml-заново/backtest.py [--tables /tmp/crr_tables]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from catboost import CatBoostClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score, brier_score_loss, log_loss, precision_recall_curve,
    roc_auc_score,
)

from calibrate import build_calm_table, to_frame
from inference import MODEL_FEATURES

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
CALIBRATION_YEAR = 2025
TEST_YEAR = 2026
PRECISION_FLOOR = 0.70


def load_tables(folder: Path) -> pl.DataFrame:
    files = sorted(folder.glob('*_hourly.parquet'))
    if not files:
        raise FileNotFoundError(f'Нет часовых витрин в {folder}')
    frames = [pl.read_parquet(path) for path in files]
    return pl.concat(frames, how='vertical').sort(['ch', 'hour'])


def score(model: CatBoostClassifier, frame: pl.DataFrame) -> np.ndarray:
    return model.predict_proba(to_frame(frame))[:, 1]


def metrics(labels: np.ndarray, raw: np.ndarray, calibrated: np.ndarray) -> dict:
    return {
        'rows': int(len(labels)),
        'positives': int(labels.sum()),
        'positive_rate': round(float(labels.mean()), 6),
        'pr_auc': round(float(average_precision_score(labels, calibrated)), 6),
        'roc_auc': round(float(roc_auc_score(labels, calibrated)), 6),
        'raw_brier': round(float(brier_score_loss(labels, raw)), 6),
        'calibrated_brier': round(float(brier_score_loss(labels, calibrated)), 6),
        'raw_log_loss': round(float(log_loss(labels, raw, labels=[0, 1])), 6),
        'calibrated_log_loss': round(float(log_loss(labels, calibrated, labels=[0, 1])), 6),
    }


def precision_recall(labels: np.ndarray, probability: np.ndarray, threshold: float) -> dict:
    predicted = probability >= threshold
    tp = int(((predicted == 1) & (labels == 1)).sum())
    fp = int(((predicted == 1) & (labels == 0)).sum())
    fn = int(((predicted == 0) & (labels == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        'threshold': round(float(threshold), 6),
        'flagged': int(predicted.sum()),
        'flagged_share': round(float(predicted.mean()), 6),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
    }


def threshold_for_precision(labels: np.ndarray, probability: np.ndarray, floor: float) -> float:
    curve_precision, curve_recall, thresholds = precision_recall_curve(labels, probability)
    allowed = np.where(curve_precision[:-1] >= floor)[0]
    if not len(allowed):
        return float(thresholds[-1]) if len(thresholds) else 1.0
    best = allowed[np.argmax(curve_recall[allowed])]
    return float(thresholds[best])


def object_days(scored: pl.DataFrame) -> pl.DataFrame:
    channel_day = (
        scored.group_by(['obj', 'obj_name', 'parent', 'ch', pl.col('hour').dt.date().alias('day')])
        .agg([
            pl.col('p').max().alias('p_ch'),
            pl.col('target_24h').max().alias('fact_ch'),
        ])
        .filter(pl.col('obj') != 'unknown')
        .with_columns(pl.col('p_ch').rank(method='ordinal', descending=True).over(['obj', 'day']).alias('rk'))
    )
    return (
        channel_day.filter(pl.col('rk') <= 5)
        .group_by(['obj', 'obj_name', 'parent', 'day'])
        .agg([
            pl.col('p_ch').mean().alias('p_obj'),
            pl.col('fact_ch').max().alias('fact'),
        ])
        .sort(['obj', 'day'])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', type=Path, default=ROOT / 'model_tables')
    parser.add_argument('--out', type=Path, default=MODELS / 'new_alarm_backtest_2026.json')
    args = parser.parse_args()

    hourly = load_tables(args.tables)
    calm = build_calm_table(hourly)
    model = CatBoostClassifier()
    model.load_model(str(MODELS / 'incident_24h.cbm'))
    if list(model.feature_names_) != MODEL_FEATURES:
        raise RuntimeError('Веса обучены на другом наборе признаков')
    shipped = joblib.load(MODELS / 'new_alarm_channel_isotonic.joblib')

    result: dict = {
        'note': 'Реконструкция часовой витрины из годовых архивов, не оригинальная таблица.',
        'calibration_year': CALIBRATION_YEAR,
        'test_year': TEST_YEAR,
        'hourly_rows': int(hourly.height),
        'calm_rows': int(calm.height),
    }

    valid = calm.filter(pl.col('year') == CALIBRATION_YEAR)
    valid_raw = score(model, valid)
    valid_labels = valid['target_24h'].to_numpy().astype(int)
    refit = IsotonicRegression(out_of_bounds='clip').fit(valid_raw, valid_labels)
    result['valid_raw'] = metrics(valid_labels, valid_raw, valid_raw)
    result['valid_refit'] = metrics(valid_labels, valid_raw, refit.predict(valid_raw))
    result['valid_shipped_calibrator'] = metrics(valid_labels, valid_raw, shipped.predict(valid_raw))

    test = calm.filter(pl.col('year') == TEST_YEAR)
    test_raw = score(model, test)
    test_labels = test['target_24h'].to_numpy().astype(int)
    test_calibrated = shipped.predict(test_raw)
    result['test_raw'] = metrics(test_labels, test_raw, test_raw)
    result['test_shipped_calibrator'] = metrics(test_labels, test_raw, test_calibrated)

    result['valid_channel_threshold'] = precision_recall(valid_labels, valid_raw,
                                                         threshold_for_precision(valid_labels, valid_raw, PRECISION_FLOOR))
    result['test_channel_threshold'] = precision_recall(test_labels, test_raw,
                                                        threshold_for_precision(valid_labels, valid_raw, PRECISION_FLOOR))

    valid_days = object_days(valid.select(['obj', 'obj_name', 'parent', 'ch', 'hour', 'target_24h'])
                             .with_columns(pl.Series('p', valid_raw)))
    test_days = object_days(test.select(['obj', 'obj_name', 'parent', 'ch', 'hour', 'target_24h'])
                            .with_columns(pl.Series('p', test_raw)))
    chosen = 1.0
    for name, days in (('valid', valid_days), ('test', test_days)):
        labels = days['fact'].to_numpy().astype(int)
        probability = days['p_obj'].to_numpy()
        row = {'object_days': int(days.height), 'with_fact': int(labels.sum()),
               'fact_rate': round(float(labels.mean()), 6),
               'pr_auc': round(float(average_precision_score(labels, probability)), 6)}
        if name == 'valid':
            chosen = threshold_for_precision(labels, probability, PRECISION_FLOOR)
            row['chosen_threshold'] = round(float(chosen), 6)
        row['at_chosen'] = precision_recall(labels, probability, chosen)
        result[f'{name}_object_days'] = row

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
