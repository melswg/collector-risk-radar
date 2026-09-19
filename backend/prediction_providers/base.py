from abc import ABC, abstractmethod
from backend.contracts import PredictRequest, PredictResponse

class NotSupported(RuntimeError):
    """Операция не поддерживается данным провайдером."""

class PredictionProvider(ABC):
    @abstractmethod
    def predict(self, request: PredictRequest) -> PredictResponse:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[dict]:
        raise NotImplementedError

    def start_training(self, job_spec: dict) -> dict:
        raise NotSupported('Обучение отсутствует у этого провайдера')

    def get_job(self, job_id: str) -> dict:
        raise NotSupported('Задания отсутствуют у этого провайдера')

    def activate(self, model_id: str) -> dict:
        raise NotSupported('Активация отсутствует у этого провайдера')

    def shadow(self, model_id: str) -> dict:
        raise NotSupported('Теневой реестр отсутствует у этого провайдера')
