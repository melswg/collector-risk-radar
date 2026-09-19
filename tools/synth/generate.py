"""Воспроизводимая синтетика: редкие инциденты, сезонность и отдельная истина."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from backend.ingestion import TYPES


def generate(output: Path, objects=12, years=1, seed=2026, step_hours=24):
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    end = datetime(2026, 9, 19, 0, tzinfo=timezone.utc)
    start = end-timedelta(days=365*years)
    registry, channels, events, labels, weather, works, ods = [], [], [], [], [], [], []
    for i in range(objects):
        obj = f'obj-{i+1:06d}'
        registry.append(dict(id=obj, name=f'Коллектор {i+1:03d}', tag=f'МК-{1+i//20}.{i+1}.1', lat=55.65+(i%20)*0.01, lon=37.45+(i//20)*0.025+(i%5)*0.018, meta=json.dumps({'commissioned_year': 1980+i%40, 'criticality': 1+i%3, 'object_type': 'collector_section', 'last_service_at': (end-timedelta(days=90+i*10)).isoformat()}, ensure_ascii=False)))
        for type_id, code in TYPES.items():
            channels.append(dict(id=i*100+type_id, object_id=obj, type_id=type_id, type_code=code))
        incident_times = []
        for year in range(years):
            for incident in ['fire', 'flood', 'intrusion', 'sensor_failure']:
                ts = start+timedelta(days=year*365+int(rng.integers(10, 350)), hours=12)
                incident_times.append((incident, ts))
                label = dict(id=f'label-{i}-{year}-{incident}', object_id=obj, incident_type=incident, start_ts=ts.isoformat(), end_ts=(ts+timedelta(hours=2)).isoformat(), source='synthetic_truth')
                labels.append(label)
                ods.append({**label, 'decision': 'dispatch', 'reason': 'confirmed_signals'})
        work_start = end-timedelta(days=3)
        works.append(dict(id=f'wo-{i}', object_id=obj, status='approved', **{'from': work_start.isoformat(), 'to': (work_start+timedelta(hours=8)).isoformat()}, kind='inspection', published_at=(work_start-timedelta(days=3)).isoformat()))
        times = {start+timedelta(hours=h) for h in range(0, int((end-start).total_seconds()/3600)+1, step_hours)}
        # Плотные окна предвестников сохраняют динамику при компактной дальней истории.
        for _, ts in incident_times:
            times.update(ts+timedelta(minutes=m) for m in range(-360, 61, 5))
        times.update(end+timedelta(minutes=m) for m in range(-24*60, 1, 5))
        for ti, ts in enumerate(sorted(times)):
            seasonal = 15+8*math.sin(2*math.pi*ts.timetuple().tm_yday/365)
            temp = seasonal+2*math.sin(ts.hour/24*2*math.pi)+rng.normal(0, 0.4)+(ts.year-start.year)*0.15
            incident = next(((k, (target-ts).total_seconds()/3600) for k, target in incident_times if -1 <= (target-ts).total_seconds()/3600 <= 6), None)
            rain = max(0, rng.normal(0.3, 0.8))
            values = {2: 0, 3: 1, 4: 0, 5: int(rng.random()<0.015), 6: 0, 7: int(rng.random()<0.08), 8: 1, 9: 1, 12: temp}
            if incident:
                kind, remaining = incident
                strength = max(0, 1-remaining/6)
                if kind == 'fire':
                    values[12] += strength*50
                    values[4] = int(remaining < 2)
                elif kind == 'flood':
                    rain = 6+strength*8
                    values[7], values[9] = ti%2, int(remaining > 2)
                elif kind == 'intrusion':
                    values[2], values[5] = int(ti%3 == 0), int(ti%2 == 0)
                else:
                    values[12] += strength*12+rng.normal(0, 3*strength)
            for type_id, value in values.items():
                if rng.random() < 0.008:
                    continue
                event_id = f'e-{i}-{ti}-{type_id}'
                events.append(dict(id=event_id, channel_id=i*100+type_id, type_id=type_id, value=round(value, 3), ts=ts.isoformat()))
                if type_id == 5 and value and not incident:
                    labels.append(dict(id='false-'+event_id, object_id=obj, incident_type='intrusion_false_alarm', start_ts=ts.isoformat(), end_ts=ts.isoformat(), alarm_ref=event_id, is_false=True, reason='animal' if ti%2 else 'sensor_fault', source='synthetic_truth'))
            if ts.minute == 0:
                weather.append(dict(object_id=obj, ts=ts.isoformat(), temp_c=round(seasonal, 2), humidity=80 if rain > 5 else 65, precip_mm=round(rain, 2), pressure_hpa=1000 if rain > 5 else 1015, kind='observed', published_at=ts.isoformat()))
                weather.append(dict(object_id=obj, ts=(ts+timedelta(hours=3)).isoformat(), temp_c=round(seasonal, 2), humidity=80, precip_mm=round(rain, 2), pressure_hpa=1010, kind='forecast', published_at=ts.isoformat()))
    frames = dict(objects=registry, channels=channels, events=events, labels=labels, weather=weather, planned_works=works, ods=ods)
    manifest = dict(schema_version='1.0', software_version='1.0.0', synthetic=True, seed=seed, timezone='UTC', period={'from': start.isoformat(), 'to': end.isoformat()}, sampling={'background_hours': step_hours, 'incident_minutes': 5, 'note': 'Компактная история с плотными окнами, не непрерывный промышленный поток'}, files={})
    for name, rows in frames.items():
        frame = pd.DataFrame(rows)
        path = output / f'{name}.parquet'
        frame.to_parquet(path, index=False)
        frame.to_csv(output/f'{name}.csv', index=False, sep=';', decimal=',')
        manifest['files'][path.name] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    # Грязный тестовый файл вынесен из чистых витрин.
    dirty = pd.DataFrame(events[:100])
    dirty.loc[0, 'value'] = '25,00'
    dirty.loc[1, 'ts'] = 'ошибка даты'
    pd.concat([dirty, dirty.iloc[:2]]).to_csv(output/'dirty_events.csv', index=False, sep=';')
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('data/synthetic-small'))
    parser.add_argument('--preset', choices=['small', 'large'], default='small')
    parser.add_argument('--seed', type=int, default=2026)
    args = parser.parse_args()
    print(json.dumps(generate(args.output, objects=120 if args.preset == 'large' else 12, years=12 if args.preset == 'large' else 1, seed=args.seed), ensure_ascii=False, indent=2))
