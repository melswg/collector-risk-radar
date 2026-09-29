"""Сборка часовой витрины «канал × час» из годовых архивов заказчика.

Восстановление шага, файла которого нет в переданных материалах: оригинальный
`model_tables/all_years_hourly.parquet` не приложен, поэтому витрина собирается
из годовых `*_labeled.zip`. Это реконструкция по колонкам, которые ожидают
`calibrate.py` и `02_main.ipynb`, а не исходная таблица.

Колонки: ch, hour, year, sensor, sys, objkind, parent, obj, obj_name, n_events,
num_mean, num_max, has_alarm, has_1970, is_weekend, h_since_prev, target_24h.

Запуск: .venv/bin/python ml-заново/build_hourly_table.py 2025 2026 --out /tmp/...
"""

from __future__ import annotations

import argparse
import glob
import shutil
import tempfile
import zipfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = Path('/Users/malikamkhadov/Downloads/00_Inbox')
HORIZON_H = 24

EVENT_COLUMNS = [
    'ид_канала_данных', 'datetime', 'тревожное', 'значение_датчика',
    'тип_инж_системы', 'тип_датчика',
]


def archive_for(archive_dir: Path, year: int) -> Path:
    matches = sorted(archive_dir.glob(f'{year}_*abeled.zip'))
    if not matches:
        raise FileNotFoundError(f'Нет годового архива для {year} в {archive_dir}')
    return matches[0]


def reference_tables(archive_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Справочники каналов и объектов из архива заказчика."""
    customers = sorted(archive_dir.glob('archive-2026-*.zip'))
    if not customers:
        raise FileNotFoundError('Нет архива со справочниками заказчика')
    with zipfile.ZipFile(customers[-1], metadata_encoding='cp866') as source:
        names = {Path(name).name: name for name in source.namelist()}
        channels = pl.read_csv(source.read(names['справочник_каналов_датчиков.csv']), infer_schema_length=0)
        objects = pl.read_csv(source.read(names['справочник_объектов_диспетчер.csv']), infer_schema_length=0)
    return channels, objects


def aggregate_year(path: Path, temporary: Path) -> pl.DataFrame:
    target = temporary / path.stem
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(path) as source:
        source.extractall(temporary)
    parts = sorted(glob.glob(str(temporary / '*' / 'part_*.parquet')))
    if not parts:
        raise FileNotFoundError(f'Нет part_*.parquet в {path}')
    frame = (
        pl.scan_parquet(parts)
        .select(EVENT_COLUMNS)
        .with_columns([
            pl.col('ид_канала_данных').cast(pl.Int64, strict=False).alias('ch'),
            pl.col('datetime').dt.truncate('1h').alias('hour'),
            pl.col('тревожное').fill_null(False).cast(pl.Boolean).alias('alarm'),
            pl.col('значение_датчика').cast(pl.Utf8).str.replace_all(',', '.')
              .cast(pl.Float64, strict=False).alias('numeric'),
            pl.col('значение_датчика').cast(pl.Utf8).str.contains('1970').alias('is_1970'),
        ])
        .filter(pl.col('ch').is_not_null() & pl.col('hour').is_not_null())
        .group_by(['ch', 'hour'])
        .agg([
            pl.len().cast(pl.Int64).alias('n_events'),
            pl.col('alarm').any().alias('has_alarm'),
            pl.col('is_1970').any().alias('has_1970'),
            pl.col('numeric').mean().alias('num_mean'),
            pl.col('numeric').max().alias('num_max'),
            pl.col('тип_датчика').first().alias('sensor'),
            pl.col('тип_инж_системы').first().alias('sys'),
        ])
        .collect(engine='streaming')
    )
    shutil.rmtree(target, ignore_errors=True)
    return frame.sort(['ch', 'hour'])


def add_calendar(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns([
        pl.col('hour').dt.year().cast(pl.Int64).alias('year'),
        pl.col('hour').dt.hour().cast(pl.Int64).alias('hour_of_day'),
        (pl.col('hour').dt.weekday() - 1).cast(pl.Int64).alias('dow'),
        pl.col('hour').dt.month().cast(pl.Int64).alias('month'),
        (pl.col('hour').dt.weekday() >= 6).alias('is_weekend'),
        (
            (pl.col('hour') - pl.col('hour').shift(1).over('ch')).dt.total_seconds() / 3600
        ).alias('h_since_prev'),
    ])


def add_target(frame: pl.DataFrame) -> pl.DataFrame:
    """Тревога строго после часа и не дальше 24 часов от его начала."""
    alarms = (
        frame.filter(pl.col('has_alarm'))
        .select('ch', pl.col('hour').alias('next_alarm'))
        .sort(['ch', 'next_alarm'])
    )
    base = frame.with_columns((pl.col('hour') + pl.duration(microseconds=1)).alias('after'))
    return (
        base.join_asof(alarms, left_on='after', right_on='next_alarm', by='ch',
                       strategy='forward', check_sortedness=False)
        .with_columns(
            (((pl.col('next_alarm') - pl.col('hour')).dt.total_seconds() / 3600) <= HORIZON_H)
            .fill_null(False).cast(pl.Int8).alias('target_24h')
        )
        .drop('after')
        .sort(['ch', 'hour'])
    )


def attach_registry(frame: pl.DataFrame, channels: pl.DataFrame, objects: pl.DataFrame) -> pl.DataFrame:
    registry = (
        channels.with_columns([
            pl.col('ид_канала_данных').cast(pl.Int64, strict=False).alias('ch'),
            pl.col('ид_объект').cast(pl.Int64, strict=False).alias('obj'),
        ])
        .select('ch', 'obj')
        .unique(subset=['ch'])
    )
    tree = objects.with_columns(
        pl.col('ид_объект').cast(pl.Int64, strict=False).alias('obj')
    ).select(
        'obj',
        pl.col('родитель').alias('parent'),
        pl.col('вид_объекта').alias('objkind'),
        pl.col('диспетчерское_название_объекта').alias('obj_name'),
    ).unique(subset=['obj'])
    return (
        frame.join(registry, on='ch', how='left')
        .join(tree, on='obj', how='left')
        .with_columns([
            pl.col('parent').fill_null('unknown'),
            pl.col('objkind').fill_null('unknown'),
            pl.col('obj_name').fill_null('unknown'),
            pl.col('obj').cast(pl.Utf8).fill_null('unknown'),
        ])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('years', nargs='+', type=int)
    parser.add_argument('--archive-dir', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--out', type=Path, default=ROOT / 'model_tables')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    channels, objects = reference_tables(args.archive_dir)
    with tempfile.TemporaryDirectory(prefix='hourly-build-') as temporary:
        temporary = Path(temporary)
        for year in args.years:
            frame = aggregate_year(archive_for(args.archive_dir, year), temporary)
            frame = attach_registry(add_calendar(frame), channels, objects)
            frame = add_target(frame)
            destination = args.out / f'{year}_hourly.parquet'
            frame.write_parquet(destination)
            print(f'{year}: {frame.height:,} строк -> {destination}', flush=True)


if __name__ == '__main__':
    main()
