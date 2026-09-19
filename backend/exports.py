"""Parquet, манифест и отчёты. Истина хранится отдельно от признаков."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
import pandas as pd
from sqlalchemy import select
from backend.db import Channel, Decision, Event, Object, Prediction, Record, now, serialize
from backend.settings import DATA


def export_dataset(session):
    identity = 'ds-'+str(uuid4())
    folder = DATA/'exports'/identity
    folder.mkdir(parents=True)
    tables = {'objects': [serialize(o) for o in session.scalars(select(Object))], 'channels': [serialize(c) for c in session.scalars(select(Channel))], 'events': [serialize(e) for e in session.scalars(select(Event))], 'decisions': [serialize(d) for d in session.scalars(select(Decision))]}
    for name, kind in [('labels_incident', 'label'), ('planned_works', 'work'), ('weather', 'weather')]:
        tables[name] = [dict(id=r.id, object_id=r.object_id, **r.data) for r in session.scalars(select(Record).where(Record.kind == kind))]
    labels = tables['labels_incident']
    tables['labels_false_alarm'] = [r for r in labels if r['incident_type'] == 'intrusion_false_alarm']
    tables['labels_sensor_failure'] = [r for r in labels if r['incident_type'] == 'sensor_failure']
    tables['labels_incident'] = [r for r in labels if r['incident_type'] in ('fire', 'flood', 'intrusion')]
    events = pd.DataFrame(tables['events'])
    if not events.empty:
        events['ts'] = pd.to_datetime(events['ts'], utc=True)
        for interval, name in [('5min', 'channel_agg_5m'), ('1h', 'channel_agg_1h')]:
            grouped = events.groupby(['channel_id', pd.Grouper(key='ts', freq=interval)])['value'].agg(['min', 'max', 'mean', 'std', 'first', 'last', 'count']).reset_index()
            grouped['missing_fraction'] = (1-grouped['count']/(1 if interval == '5min' else 12)).clip(0, 1)
            tables[name] = grouped.to_dict('records')
    tables['alarms'] = [r for r in tables['events'] if r['severity'] == 'warning']
    from backend.context import ContextBuilder
    tables['sensor_health'] = []
    for obj in tables['objects']:
        context = ContextBuilder(session).build([obj['id']], now()).objects[0]
        tables['sensor_health'].extend(dict(channel_id=c.channel_id, as_of=now().isoformat(), **c.health) for c in context.channels)
    from backend.analytics import label_window
    from backend.ingestion import parse_date
    coverages = {r.object_id: r.data for r in session.scalars(select(Record).where(Record.kind == 'coverage'))}
    tables['label_windows'] = []
    for p in session.scalars(select(Prediction)):
        cover = coverages.get(p.object_id)
        if cover:
            times = [parse_date(r['start_ts']) for r in labels if r['object_id'] == p.object_id and r['incident_type'] == p.incident_type]
            tables['label_windows'].append(dict(object_id=p.object_id, as_of=p.as_of, horizon_h=p.horizon_h, incident_type=p.incident_type, label=label_window(p.as_of, p.horizon_h, times, parse_date(cover['to']))))
    manifest = dict(schema_version='1.0', software_version='1.0.0', dataset_id=identity, timezone='UTC', synthetic=bool(coverages) and all(c.get('synthetic', False) for c in coverages.values()), seed=2026 if coverages and all(c.get('synthetic', False) for c in coverages.values()) else None, created_at=now().isoformat(), period={'from': str(events.ts.min()) if not events.empty else None, 'to': str(events.ts.max()) if not events.empty else None}, files={})
    for name, rows in tables.items():
        frame = pd.DataFrame(rows)
        for column in frame.columns:
            if any(isinstance(v, (dict, list)) for v in frame[column]):
                frame[column] = frame[column].map(lambda v: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v)
        path = folder/f'{name}.parquet'
        frame.to_parquet(path, index=False)
        manifest['files'][path.name] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (folder/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    session.add(Record(id=identity, kind='dataset', data={'manifest': manifest, 'path': str(folder)}))
    return {'id': identity, 'manifest': manifest, 'path': str(folder)}


def pdf_rows(path, title, rows):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape
    candidates = [os.getenv('PDF_FONT', ''), '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf']
    font = next((p for p in candidates if p and Path(p).exists()), None)
    if not font:
        raise ValueError('Установите кириллический шрифт и задайте PDF_FONT')
    pdfmetrics.registerFont(TTFont('ReportFont', font))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'ReportFont'
    story = [Paragraph(escape(title), styles['Title']), Spacer(1, 15), Paragraph('Синтетическое демо. Решение принимает диспетчер.', styles['Normal'])]
    for row in rows:
        story += [Spacer(1, 10), Paragraph(escape(json.dumps(row, ensure_ascii=False, default=str)), styles['Normal'])]
    SimpleDocTemplate(str(path)).build(story)


def create_report(session, kind, format):
    if kind not in ('predictions', 'repairs'):
        raise ValueError('Виды отчётов: predictions, repairs')
    rows = [serialize(p) for p in session.scalars(select(Prediction).where(Prediction.role == 'active').limit(500))] if kind == 'predictions' else [serialize(r) for r in session.scalars(select(Record).where(Record.kind.in_(['work', 'recommendation'])).limit(500))]
    path = DATA/f'report-{uuid4()}.{format}'
    if format == 'pdf':
        pdf_rows(path, 'Прогнозы' if kind == 'predictions' else 'Работы и рекомендации', rows)
    else:
        from openpyxl import Workbook
        wb = Workbook()
        sheet = wb.active
        sheet.title = 'Отчёт'
        if rows:
            sheet.append(list(rows[0]))
            for row in rows:
                sheet.append([str(v) if isinstance(v, (dict, list)) else v for v in row.values()])
            sheet.freeze_panes = 'A2'
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = 24
        wb.save(path)
    return path
