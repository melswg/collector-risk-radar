"""Калибровка вероятности новой тревоги на отложенном 2025 году."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from catboost import CatBoostClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

from inference import CATEGORICAL_FEATURES, MODEL_FEATURES

ROOT = Path(__file__).resolve().parent
TABLE = ROOT / "model_tables" / "all_years_hourly.parquet"
MODEL = ROOT / "models" / "incident_24h.cbm"
OUT = ROOT / "models"


def build_calm_table(hourly: pl.DataFrame) -> pl.DataFrame:
    hourly = hourly.sort(["ch", "hour"]).with_columns([
        pl.when(pl.col("h_since_prev") < 0).then(None).otherwise(pl.col("h_since_prev")).alias("h_since_prev"),
        pl.when(pl.col("sensor") == "Газовый датчик").then(pl.col("num_max")).otherwise(None).alias("methane"),
    ]).with_columns(
        (pl.col("methane") - pl.col("methane").shift(1).over("ch")).alias("methane_delta")
    ).with_columns(
        pl.when(pl.col("h_since_prev").is_between(0, 48)).then(pl.col("methane_delta")).otherwise(None).alias("methane_delta")
    )
    alarms = hourly.filter(pl.col("has_alarm")).select("ch", pl.col("hour").alias("next_alarm")).sort(["ch", "next_alarm"])
    history = hourly.filter(pl.col("has_alarm") & (pl.col("year") != 2021)).select("ch", pl.col("hour").alias("alarm_hour")).sort(["ch", "alarm_hour"]).with_columns(pl.col("alarm_hour").cum_count().over("ch").alias("alarm_n"))
    base = hourly.with_columns((pl.col("hour") + pl.duration(microseconds=1)).alias("hour_after"), (pl.col("hour") - pl.duration(microseconds=1)).alias("before"))
    labeled = base.join_asof(alarms, left_on="hour_after", right_on="next_alarm", by="ch", strategy="forward", check_sortedness=False).with_columns((((pl.col("next_alarm") - pl.col("hour")).dt.total_seconds() / 3600) <= 24).fill_null(False).cast(pl.Int8).alias("target_24h"))
    last = labeled.join_asof(history, left_on="before", right_on="alarm_hour", by="ch", strategy="backward", check_sortedness=False).with_columns([
        ((pl.col("hour") - pl.col("alarm_hour")).dt.total_seconds() / 3600).alias("hours_since_alarm"),
        pl.col("alarm_n").fill_null(0).alias("alarm_n_past"),
    ])
    for hours, name in ((24, "alarms_24h"), (72, "alarms_72h"), (168, "alarms_168h")):
        cuts = last.select("ch", "hour", (pl.col("hour") - pl.duration(hours=hours) - pl.duration(microseconds=1)).alias("cut")).sort(["ch", "cut"])
        previous = cuts.join_asof(history.select("ch", "alarm_hour", pl.col("alarm_n").alias("n_before")), left_on="cut", right_on="alarm_hour", by="ch", strategy="backward", check_sortedness=False).select("ch", "hour", "n_before")
        last = last.join(previous, on=["ch", "hour"], how="left").with_columns((pl.col("alarm_n_past") - pl.col("n_before").fill_null(0)).cast(pl.Int32).alias(name)).drop("n_before")
    return last.filter(~pl.col("has_alarm")).with_columns([
        pl.when(pl.col("num_mean") == -1).then(None).otherwise(pl.col("num_mean")).alias("num_mean"),
        pl.when(pl.col("num_max") == -1).then(None).otherwise(pl.col("num_max")).alias("num_max"),
        pl.col("has_1970").cast(pl.Int8), pl.col("is_weekend").cast(pl.Int8), pl.col("n_events").cast(pl.Int32),
    ])


def to_frame(data: pl.DataFrame):
    frame = data.select(MODEL_FEATURES).to_pandas()
    for name in CATEGORICAL_FEATURES:
        frame[name] = frame[name].fillna("unknown").astype(str)
    for name in set(MODEL_FEATURES) - CATEGORICAL_FEATURES:
        frame[name] = frame[name].apply(lambda value: float(value) if value == value else np.nan)
    return frame


def main() -> None:
    calm = build_calm_table(pl.read_parquet(TABLE))
    valid = calm.filter(pl.col("year") == 2025)
    model = CatBoostClassifier()
    model.load_model(str(MODEL))
    probabilities = model.predict_proba(to_frame(valid))[:, 1]
    labels = valid["target_24h"].to_numpy()
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(probabilities, labels)
    calibrated = calibrator.predict(probabilities)
    joblib.dump(calibrator, OUT / "new_alarm_channel_isotonic.joblib")
    metrics = {
        "target": "new_alarm_24h", "calibration_year": 2025, "rows": len(labels),
        "raw_brier": round(float(brier_score_loss(labels, probabilities)), 6),
        "calibrated_brier": round(float(brier_score_loss(labels, calibrated)), 6),
        "raw_log_loss": round(float(log_loss(labels, probabilities, labels=[0, 1])), 6),
        "calibrated_log_loss": round(float(log_loss(labels, calibrated, labels=[0, 1])), 6),
        "note": "Калибровка меняет шкалу вероятности, но не смысл таргета.",
    }
    (OUT / "new_alarm_calibration_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(metrics)


if __name__ == "__main__":
    main()