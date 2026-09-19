"""Правила являются некалиброванной базовой линией, а не ML."""
import math
import numpy as np
from backend.contracts import PredictRequest, PredictResponse
from backend.prediction_providers.base import PredictionProvider
from backend.settings import config

class RulesProvider(PredictionProvider):
    def __init__(self):
        self.rules = config('rules')

    def health(self):
        return {'status': 'ready', 'contract_version': '1.0', 'kind': 'rules'}

    def list_models(self):
        return [dict(id='deterministic-rules', version=self.rules['version'], kind='rules', status='active', incident_types=['fire', 'flood', 'intrusion_false_alarm', 'sensor_failure'], horizons_h=[24, 72], trained_at=None, metrics={}, data_manifest_id=None)]

    def predict(self, request: PredictRequest) -> PredictResponse:
        predictions = []
        for obj in request.objects:
            series = {}
            health = []
            for c in obj.channels:
                series.setdefault(c.type_code, []).extend(float(v) for _, v in c.series.points if v is not None)
                health.append(c.health)
            temp = np.asarray(series.get('temperature', []))
            baseline = temp[:-12] if len(temp) > 12 else temp
            median = float(np.median(baseline)) if len(baseline) else 20.0
            mad = max(float(np.median(np.abs(baseline-median))) * 1.4826, 2.0) if len(baseline) else 2.0
            z = max(0, (float(temp[-1]) - median) / mad) if len(temp) else 0
            slope = max(0, float(temp[-1]-temp[-min(12, len(temp))]) / max(1, min(12, len(temp))-1)) if len(temp) else 0
            alarms = obj.recent_alarms
            last_alarm = alarms[-1] if alarms else None
            weather = obj.weather.get('forecast', [])
            delta = (request.options.what_if or {}).get('weather.forecast.precip_mm_delta', 0)
            precip = max(0, sum(float(w.get('precip_mm', 0)) for w in weather) + delta)
            pumps = series.get('pump', [])
            freq = float(np.count_nonzero(np.diff(pumps[-24:]) > 0)) / 3 if len(pumps) > 1 else 0
            indicators = {
                'fire': dict(temp_z=min(z, 8), temp_slope=min(slope, 5), smoke=max(series.get('smoke', [0])[-12:]), gas=max(series.get('gas', [0])[-12:]), fan_off=1-min(series.get('fan', [1])[-12:])),
                'flood': dict(pump_frequency=freq, phase_loss=1-min(series.get('phase', [1])[-12:]), precip=precip, flood_history=obj.maintenance.get('flood_history', 0)),
                'intrusion_false_alarm': dict(expected=int(bool(last_alarm and last_alarm.get('expected'))), repeats=min(8, len(alarms)), unhealthy=int(any(h.get('status') != 'ok' for h in health)), isolated=int(len({a.get('channel_id') for a in alarms}) <= 1), daytime=int(6 <= (request.as_of.hour+3)%24 < 22)),
                'sensor_failure': {key: max([float(h.get(key, 0)) for h in health] or [0]) for key in ['flatline', 'dropout_rate', 'chatter', 'noise_ratio', 'drift']},
            }
            for incident in request.incident_types:
                required = {'fire': ['temperature', 'smoke'], 'flood': ['pump'], 'sensor_failure': list(series), 'intrusion_false_alarm': ['movement', 'contact-unlock-norm']}[incident]
                sufficient = any(len(series.get(k, [])) >= 2 for k in required) and (incident != 'intrusion_false_alarm' or last_alarm is not None)
                factors = [dict(feature=k, value=float(v), contribution=round(float(v)*self.rules[incident][k], 4), direction='up') for k, v in indicators[incident].items()]
                score = self.rules['bias'] + sum(f['contribution'] for f in factors)
                probability = round(1/(1+math.exp(-max(-30, min(30, score)))), 6) if sufficient else None
                for horizon in request.horizons_h:
                    predictions.append(dict(object_id=obj.object_id, incident_type=incident, horizon_h=horizon, probability=probability, data_sufficiency='ok' if sufficient else 'insufficient', explanation={'top_factors': sorted(factors, key=lambda x: abs(x['contribution']), reverse=True)} if request.options.return_explanations else {}, warnings=['Вероятность правил не калибрована на реальных данных'], alarm_ref=last_alarm.get('id') if last_alarm and incident == 'intrusion_false_alarm' else None))
        return PredictResponse.model_validate(dict(request_id=request.request_id, model={'id': 'deterministic-rules', 'version': self.rules['version'], 'kind': 'rules'}, generated_at=request.as_of, predictions=predictions))
