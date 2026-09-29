"""Отдельный процесс: long polling команд Telegram-бота + повтор доставки уведомлений.

Не запускается внутри основного web-процесса (см. deploy/compose.yaml, профиль telegram),
чтобы polling не конфликтовал с несколькими репликами API. Для production предпочтителен
webhook (POST /api/v1/telegram/webhook) — этот процесс нужен для локальной разработки и
как ретрай-цикл очереди доставки в окружениях без webhook.
"""
import logging
import time
from backend.db import Session
from backend.notifications import commands, service, telegram

log = logging.getLogger(__name__)
POLL_IDLE_SECONDS = 2
ERROR_BACKOFF_SECONDS = 5


def sweep_deliveries() -> None:
    try:
        with Session.begin() as session:
            sent = service.dispatch_pending(session)
        if sent:
            log.info('Отправлено уведомлений: %s', sent)
    except Exception:
        log.exception('Ошибка обработки очереди доставки')


def poll_once(offset: int | None) -> int | None:
    try:
        updates = telegram.get_updates(offset, timeout=10)
    except telegram.TelegramDeliveryError as exc:
        log.warning('Ошибка получения обновлений Telegram: %s', exc.code)
        time.sleep(ERROR_BACKOFF_SECONDS)
        return offset
    for update in updates:
        offset = update['update_id'] + 1
        try:
            with Session.begin() as session:
                commands.handle_update(session, update)
        except Exception:
            log.exception('Ошибка обработки обновления Telegram %s', update.get('update_id'))
    if not updates:
        time.sleep(POLL_IDLE_SECONDS)
    return offset


def run_forever() -> None:
    if not telegram.enabled():
        raise SystemExit('TELEGRAM_NOTIFICATIONS_ENABLED=false или не задан TELEGRAM_BOT_TOKEN')
    offset = None
    while True:
        sweep_deliveries()
        offset = poll_once(offset)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_forever()
