# Технологии

| Часть проекта | Технологии, указанные в документации |
| --- | --- |
| Сервер | Python, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. |
| Локальная база | SQLite. |
| Целевая база | PostgreSQL 15. В требованиях допускается PostgreSQL 12+, но все версии отдельно не проверялись. |
| Интерфейс | React, TypeScript, Vite. |
| Карта | В журнале работ описаны MapLibre и OpenFreeMap. В ранних вариантах использовались Leaflet и OpenStreetMap. |
| Графики | Recharts. |
| Модель | CatBoost и калибровка isotonic. Для запуска нужны зависимости из `requirements-inference.txt`, включая scikit-learn. |
| Работа с данными | В спецификации указаны pandas, PyArrow и Parquet. Для повторной калибровки нужен polars. |
| Фоновые задачи | Redis, планировщик и обработчик задач. В спецификации указаны APScheduler и Redis Streams. |
| Развёртывание | Docker Compose, nginx, Makefile. |
| Проверки | pytest, ruff, тесты Node и сборка TypeScript/Vite. |
| Корпоративный вход | Предусмотрен LDAP/AD. |
| Шрифты | Golos Text и Unbounded. В документации интерфейса указаны локальные файлы и лицензии OFL. |



[Все разделы](README.md)
