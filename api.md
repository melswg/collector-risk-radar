# API

### Работающий сценарий прогноза по каналу

Эти методы указаны в актуальном README и описании подключения модели.

| Метод | Назначение |
| --- | --- |
| `PUT /api/v1/sensors/{id}/ml-passport` | Сохранить паспорт зарегистрированного канала. Выполняет аналитик. |
| `POST /api/v1/ingest/events` | Загрузить события канала. |
| `POST /api/v1/predictions/ml-channel/run` | Рассчитать прогноз. Доступен диспетчеру или аналитику. |
| `GET /api/v1/predictions/{id}` | Прочитать сохранённый прогноз. |
| `POST /api/v1/predictions/{id}/decision` | Сохранить решение по прогнозу. |
| `POST /api/v1/demo/ml-channel` | Создать искусственный пример и вызвать настоящую модель. |

Пример запроса после создания демонстрационного канала:

```json
{
  "channel_id": 990001
}
```

В запросе также можно указать `as_of`. Полные схемы паспорта и решения в использованных файлах Markdown не приведены.

В прогнозе сохраняются сведения об объекте и канале, время среза и расчёта, горизонт, вероятность и источник модели. Точное расположение полей в JSON этот перечень не задаёт.

### Остальные методы из спецификации

Ниже приведён API, описанный в спецификации. Пути указаны относительно `/api/v1`. В текущих отчётах не подтверждена отдельная проверка каждого метода.

| Задача | Методы |
| --- | --- |
| Вход | `POST /auth/login`, `GET /auth/me`. |
| Приём событий | `POST /ingest/events`, `POST /ingest/ods-journal`. |
| Импорт файлов | `POST /import/files`, `GET /import/jobs/{id}`. |
| Объекты и оборудование | `GET /equipment`, `POST /registry/equipment/sync`, `GET /objects`, `GET /objects/{id}`, `GET /objects/geojson`. |
| Датчики | `GET /sensors/{id}/health`, `GET /sensors/{id}/series`. |
| Прогнозы | `GET /predictions`, `GET /predictions/{id}`, `POST /predictions/run`, `POST /predictions/{id}/decision`, `GET /predictions/{id}/analogs`, `POST /predictions/what-if`. |
| Журнал событий | `GET /events`. |
| Рекомендации | `GET /recommendations`, `PATCH /recommendations/{id}`, `POST /recommendations/{id}/draft-order`. |
| Проверка качества | `GET /evaluation/metrics`, `POST /evaluation/backtest`, `POST /evaluation/validate-upload`, `GET /evaluation/model-comparison`. |
| Работа с моделями | `GET /ml/status`, `GET /ml/models`, `POST /ml/train`, `GET /ml/jobs/{id}`, `POST /ml/models/{id}/activate`, `POST /ml/models/{id}/shadow`. |
| Выгрузки | `POST /datasets/export`, `GET /datasets/{id}`, `POST /feedback/export`. |
| Аналитика | `GET /analytics/incident-stats`, `GET /analytics/seasonality`. |
| Уведомления | `GET /notifications/stream`, вариант с SSE. |
| Отчёты | `GET /reports/{type}?format=pdf` или `format=xlsx`. |
| Настройки | `GET /settings`, `PUT /settings`. |
| Администрирование | `GET /admin/users`, `GET /admin/audit`. |

В спецификации также названы `/health` и `/metrics`. Их полный адрес нужно уточнять на запущенном стенде. Наличие метода обучения в этом списке не означает, что настоящее обучение уже подключено.

### API отдельного сервиса модели

Для внешнего сервиса ранее подготовлено описание обмена версии `1.0`.

| Метод | Назначение |
| --- | --- |
| `GET /v1/health` | Проверка состояния сервиса. |
| `GET /v1/models` | Список моделей и версий. |
| `POST /v1/predict` | Расчёт по объектам. |
| `POST /v1/predict/jobs` | Создание пакетного задания. |
| `GET /v1/predict/jobs/{id}` | Получение его состояния. |
| `POST /v1/train/jobs` | Создание задания обучения. |
| `GET /v1/train/jobs/{id}` | Получение его состояния. |
| `POST /v1/models/{id}/activate` | Активация модели. |
| `POST /v1/models/{id}/shadow` | Перевод в режим сравнения без участия в рабочих решениях. |

В описании предусмотрены сервисная авторизация, пакет до 50 объектов, время в UTC и запрет передачи будущих данных. Заглушка обозначается как `stub`. Повторный `request_id` с другим содержимым должен вернуть ошибку `409`.

Этот API отличается от подключённого прогноза по одному каналу. Запуск шаблона внешнего сервиса не заменяет вызов модели `incident_24h.cbm`.

[Все разделы](README.md)
