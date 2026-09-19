"""Адаптеры заказчика имеют только GET; записи в сторонние системы отсутствуют."""
import json
from datetime import timedelta
from pathlib import Path
import httpx
from backend.db import now

class ReadOnlyAdapter:
    def __init__(self, url: str | None = None, token: str = '', path: str | None = None):
        self.url, self.token, self.path = url, token, path

    def fetch(self, params: dict | None = None) -> list[dict]:
        if self.path:
            return json.loads(Path(self.path).read_text())
        if not self.url:
            raise ValueError('Не настроен адрес или файл источника')
        with httpx.Client(timeout=10) as client:
            response = client.get(self.url, params=params, headers={'Authorization': f'Bearer {self.token}'})
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data['items']

class SmvuAdapter(ReadOnlyAdapter):
    """Чтение событий СМВУ."""

class OdsJournalAdapter(ReadOnlyAdapter):
    """Чтение обезличенных записей ОДС."""

class EquipmentRegistryAdapter(ReadOnlyAdapter):
    """Чтение объектов и оборудования."""

class WorkOrdersAdapter(ReadOnlyAdapter):
    """Чтение статусов работ."""

class WeatherAdapter:
    def __init__(self):
        self.cache = {}

    def fetch(self, lat: float, lon: float) -> dict:
        key, timestamp = (lat, lon), now()
        cached = self.cache.get(key)
        if cached and timestamp-cached['fetched_at'] < timedelta(minutes=30):
            return {**cached, 'cached': True}
        try:
            response = httpx.get('https://api.open-meteo.com/v1/forecast', params={'latitude': lat, 'longitude': lon, 'hourly': 'temperature_2m,relative_humidity_2m,precipitation,surface_pressure', 'past_days': 1, 'forecast_days': 3, 'timezone': 'UTC'}, timeout=8)
            response.raise_for_status()
            hourly = response.json()['hourly']
            rows = [dict(ts=t+'+00:00', temp_c=hourly['temperature_2m'][i], humidity=hourly['relative_humidity_2m'][i], precip_mm=hourly['precipitation'][i], pressure_hpa=hourly['surface_pressure'][i], published_at=timestamp.isoformat(), kind='observed' if t <= timestamp.isoformat()[:16] else 'forecast') for i, t in enumerate(hourly['time'])]
            result = dict(items=rows, fetched_at=timestamp, stale=False, source='Open-Meteo')
            self.cache[key] = result
            return result
        except (httpx.HTTPError, KeyError, ValueError):
            return {**cached, 'stale': True} if cached else dict(items=[], fetched_at=timestamp, stale=True, source='unavailable')
