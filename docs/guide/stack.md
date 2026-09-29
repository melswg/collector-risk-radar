# Технологии

| Часть проекта | Технологии |
| --- | --- |
| Сервер | Python, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. |
| Локальная база | SQLite. |
| Целевая база | PostgreSQL 15. |
| Интерфейс | React, TypeScript, Vite. |
| Карта | MapLibre и OpenFreeMap. |
| Графики | Recharts. |
| Модель | CatBoost и калибровка isotonic. Для запуска нужны зависимости из `requirements-inference.txt`, включая scikit-learn. |
| Работа с данными | В спецификации указаны pandas, PyArrow и Parquet. Для повторной калибровки нужен polars. |
| Фоновые задачи | Redis, планировщик и обработчик задач. В спецификации указаны APScheduler и Redis Streams. |
| Развёртывание | Docker Compose, nginx, Makefile. |
| Проверки | pytest, ruff, тесты Node и сборка TypeScript/Vite. |
| Корпоративный вход | LDAP/AD; в демонстрационном стенде используется OpenLDAP. |
| Шрифты | Golos Text и Unbounded. В документации интерфейса указаны локальные файлы и лицензии OFL. |

Версии зависимостей указаны в [requirements.txt](../../requirements.txt), [requirements-inference.txt](../../ml-заново/requirements-inference.txt) и [frontend/package.json](../../frontend/package.json).

[Все разделы](README.md)
