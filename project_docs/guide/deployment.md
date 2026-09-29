# Docker и запуск стенда

Из корня проекта:

```bash
make configure
make up
```

Загрузка демонстрационных данных:

```bash
make seed
```

Состав стенда, порты, образы и тома заданы в [deploy/compose.yaml](../../deploy/compose.yaml). Команды запуска находятся в [Makefile](../../Makefile).

Резервная копия PostgreSQL создаётся командой `make backup` в `data/backups/backup.dump`. Команда `make restore` восстанавливает эту копию с заменой существующих объектов базы данных.

[Все разделы](README.md)
