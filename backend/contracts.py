"""Типизированный контракт v1.0; неизвестные поля разрешены для совместимости."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Incident = Literal['fire', 'flood', 'intrusion_false_alarm', 'sensor_failure']

class ContractModel(BaseModel):
    model_config = ConfigDict(extra='allow')

class Series(ContractModel):
    granularity: str = 'PT5M'
    points: list[tuple[datetime, float | None]] = Field(default_factory=list)

class ChannelContext(ContractModel):
    channel_id: int
    type_id: int
    type_code: str
    series: Series
    health: dict = Field(default_factory=dict)

class ObjectContext(ContractModel):
    object_id: str = Field(min_length=1)
    tag: str
    hierarchy: list[str] = Field(default_factory=list)
    geo: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)
    channels: list[ChannelContext]
    recent_alarms: list[dict] = Field(default_factory=list)
    planned_works: list[dict] = Field(default_factory=list)
    maintenance: dict = Field(default_factory=dict)
    weather: dict = Field(default_factory=dict)

class Options(ContractModel):
    return_explanations: bool = True
    return_analogs: bool = False
    what_if: dict[Literal['weather.forecast.precip_mm_delta'], float] | None = None

class PredictRequest(ContractModel):
    contract_version: Literal['1.0'] = '1.0'
    request_id: str = Field(min_length=1, max_length=128)
    as_of: datetime
    horizons_h: list[int] = Field(default_factory=lambda: [24], min_length=1, max_length=8)
    incident_types: list[Incident] = Field(default_factory=lambda: ['fire', 'flood', 'intrusion_false_alarm', 'sensor_failure'], min_length=1)
    objects: list[ObjectContext] = Field(max_length=50)
    options: Options = Field(default_factory=Options)

    @field_validator('as_of')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
            raise ValueError('Требуется UTC с часовым поясом')
        return value

    @field_validator('horizons_h')
    @classmethod
    def horizons(cls, value):
        if any(h < 1 or h > 720 for h in value) or len(value) != len(set(value)):
            raise ValueError('Уникальные горизонты от 1 до 720 часов')
        return value

    @model_validator(mode='after')
    def unique_objects(self):
        ids = [o.object_id for o in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError('Повтор объекта')
        for obj in self.objects:
            for channel in obj.channels:
                for ts, _ in channel.series.points:
                    if ts.tzinfo is None or ts > self.as_of:
                        raise ValueError('Ряд содержит будущее или дату без часового пояса')
            for w in obj.weather.get('forecast', []):
                if datetime.fromisoformat(w['published_at'].replace('Z', '+00:00')) > self.as_of:
                    raise ValueError('Прогноз погоды опубликован после as_of')
        return self

class ModelInfo(ContractModel):
    id: str
    version: str
    kind: Literal['rules', 'ml', 'stub']

class PredictionItem(ContractModel):
    object_id: str
    incident_type: Incident
    horizon_h: int = Field(ge=1, le=720)
    probability: float | None = Field(default=None, ge=0, le=1)
    data_sufficiency: Literal['ok', 'insufficient']
    explanation: dict = Field(default_factory=dict)
    analogs: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    alarm_ref: str | None = None

    @model_validator(mode='after')
    def sufficient_probability(self):
        if self.data_sufficiency == 'ok' and self.probability is None:
            raise ValueError('Для достаточных данных нужна вероятность')
        return self

class ObjectError(ContractModel):
    object_id: str
    code: str
    message: str

class PredictResponse(ContractModel):
    contract_version: Literal['1.0'] = '1.0'
    request_id: str
    model: ModelInfo
    generated_at: datetime
    predictions: list[PredictionItem]
    errors: list[ObjectError] = Field(default_factory=list)

class TrainJob(ContractModel):
    contract_version: Literal['1.0'] = '1.0'
    job_id: str = Field(min_length=1)
    incident_types: list[Incident]
    horizons_h: list[int]
    data: dict
    params: dict = Field(default_factory=dict)
    activate_on_success: bool = False


def validate_response(request: PredictRequest, response: PredictResponse) -> None:
    if response.request_id != request.request_id:
        raise ValueError('Несовпадение request_id')
    expected = {(o.object_id, t, h) for o in request.objects for t in request.incident_types for h in request.horizons_h}
    seen = set()
    errors = {e.object_id for e in response.errors}
    if errors - {o.object_id for o in request.objects}:
        raise ValueError('Неизвестные объекты в ошибках')
    for p in response.predictions:
        key = (p.object_id, p.incident_type, p.horizon_h)
        if key not in expected or key in seen or p.object_id in errors:
            raise ValueError('Неизвестный или дублированный прогноз')
        seen.add(key)
    if any(key not in seen and key[0] not in errors for key in expected):
        raise ValueError('Неполный пакет прогнозов')
