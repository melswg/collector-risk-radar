import hashlib
import logging
from backend.contracts import PredictResponse


def predict_batch(request):
    logging.warning('STUB: фиктивный прогноз, не ML')
    predictions = []
    for obj in request.objects:
        sufficient = any(c.series.points for c in obj.channels)
        for incident in request.incident_types:
            for horizon in request.horizons_h:
                value = int(hashlib.sha256(f'{obj.object_id}:{incident}:{horizon}:{request.as_of}'.encode()).hexdigest()[:8], 16)/0xffffffff
                predictions.append(dict(object_id=obj.object_id, incident_type=incident, horizon_h=horizon, probability=value if sufficient else None, data_sufficiency='ok' if sufficient else 'insufficient', warnings=['STUB: фиктивный прогноз']))
    return PredictResponse.model_validate(dict(request_id=request.request_id, generated_at=request.as_of, model={'id': 'stub', 'version': '1.0', 'kind': 'stub'}, predictions=predictions))
