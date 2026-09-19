"""HTTP, ограниченные повторы, автоматический circuit breaker и fallback."""
import hashlib
import importlib.metadata
import logging
import os
import threading
import time
import httpx
from backend.contracts import PredictRequest, PredictResponse, validate_response
from backend.prediction_providers.base import PredictionProvider
from backend.prediction_providers.rules import RulesProvider

log = logging.getLogger(__name__)

class HttpMlProvider(PredictionProvider):
    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv('ML_URL', 'http://localhost:8100')).rstrip('/')
        self.client = httpx.Client(timeout=float(os.getenv('ML_TIMEOUT_SECONDS', '5')), headers={'Authorization': 'Bearer ' + os.getenv('ML_SERVICE_TOKEN', '')}, verify=os.getenv('ML_CA_FILE') or True)
        if os.getenv('ENVIRONMENT') == 'production' and not self.url.startswith('https://'):
            raise ValueError('В промышленном режиме ML требует TLS')

    def call(self, method, path, body=None):
        for attempt in range(3):
            try:
                response = self.client.request(method, self.url + '/v1' + path, json=body)
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                if attempt == 2:
                    raise
                time.sleep(0.05 * 2**attempt)
        raise RuntimeError('Исчерпаны попытки')

    def predict(self, request):
        response = PredictResponse.model_validate(self.call('POST', '/predict', request.model_dump(mode='json')))
        validate_response(request, response)
        return response

    def health(self):
        return self.call('GET', '/health')

    def list_models(self):
        return self.call('GET', '/models')

    def start_training(self, job_spec):
        return self.call('POST', '/train/jobs', job_spec)

    def get_job(self, job_id):
        return self.call('GET', '/train/jobs/' + job_id)

    def activate(self, model_id):
        return self.call('POST', '/models/' + model_id + '/activate')

    def shadow(self, model_id):
        return self.call('POST', '/models/' + model_id + '/shadow')

class ProviderRouter(PredictionProvider):
    def __init__(self):
        self.rules = RulesProvider()
        self.remote = HttpMlProvider()
        self.mode = os.getenv('ML_MODE', 'rules')
        self.open_until = 0.0
        self.degraded = False
        self.calls = self.fallbacks = self.contract_errors = 0
        self.latency = 0.0
        self.lock = threading.RLock()
        self.cache = {}

    def predict(self, request: PredictRequest) -> PredictResponse:
        with self.lock:
            key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
            cached = self.cache.get(request.request_id)
            if cached:
                if cached[0] != key:
                    raise ValueError('request_id уже использован для другого запроса')
                return cached[1]
            start = time.monotonic()
            self.calls += 1
            if self.mode in ('rules', 'shadow'):
                response = self.rules.predict(request)
            elif self.mode == 'plugin':
                name = os.environ['ML_PLUGIN']
                entries = importlib.metadata.entry_points(group='moscollector.prediction_providers')
                entry = next(e for e in entries if e.name == name)
                response = PredictResponse.model_validate(entry.load()().predict(request))
                validate_response(request, response)
            elif self.mode in ('http', 'ensemble'):
                try:
                    if time.monotonic() < self.open_until:
                        raise ConnectionError('Circuit breaker открыт')
                    response = self.remote.predict(request)
                    if self.mode == 'ensemble':
                        baseline = self.rules.predict(request)
                        scores = {(p.object_id, p.incident_type, p.horizon_h): p.probability for p in baseline.predictions}
                        for p in response.predictions:
                            rule = scores[(p.object_id, p.incident_type, p.horizon_h)]
                            if p.probability is not None and rule is not None and abs(p.probability-rule) > 0.5:
                                p.warnings.append('Расхождение модели и правил более 0.5')
                    self.degraded = False
                    self.open_until = 0
                except (httpx.HTTPError, ValueError, ConnectionError) as exc:
                    self.contract_errors += int(isinstance(exc, ValueError))
                    if not isinstance(exc, ConnectionError):
                        self.open_until = time.monotonic() + float(os.getenv('ML_BREAKER_SECONDS', '15'))
                    self.fallbacks += 1
                    self.degraded = True
                    log.warning('ML fallback: %s', type(exc).__name__)
                    response = self.rules.predict(request)
                    for p in response.predictions:
                        p.warnings.append('Деградированный режим: ML недоступен')
            else:
                raise ValueError('Неизвестный ML_MODE')
            self.latency = time.monotonic() - start
            if len(self.cache) >= 2048:
                self.cache.pop(next(iter(self.cache)))
            self.cache[request.request_id] = (key, response)
            return response

    def predict_shadow(self, request):
        try:
            return self.remote.predict(request) if self.mode == 'shadow' else None
        except (httpx.HTTPError, ValueError) as exc:
            log.warning('Ошибка теневой модели: %s', type(exc).__name__)
            return None

    def health(self):
        return dict(status='degraded' if self.degraded else 'ready', mode=self.mode, contract_version='1.0', degraded=self.degraded, calls=self.calls, fallback_count=self.fallbacks, fallback_ratio=self.fallbacks/max(self.calls, 1), latency_seconds=self.latency, contract_errors=self.contract_errors)

    def list_models(self):
        if self.mode == 'rules':
            return self.rules.list_models()
        try:
            return self.rules.list_models() + self.remote.list_models()
        except httpx.HTTPError:
            return self.rules.list_models()

    def start_training(self, job_spec):
        return self.remote.start_training(job_spec)

    def get_job(self, job_id):
        return self.remote.get_job(job_id)

    def activate(self, model_id):
        return self.remote.activate(model_id)

    def shadow(self, model_id):
        return self.remote.shadow(model_id)
