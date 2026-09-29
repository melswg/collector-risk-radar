"""Постановка чрезвычайных уведомлений в очередь доставки и повторные попытки отправки.

Создание уведомления (Record kind='notification') и его доставка в Telegram — разные операции:
недоступность Telegram не должна влиять на создание события или прогноза.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from sqlalchemy import select
from backend.db import NotificationDelivery, Object, Record, TelegramLink, now, utc
from backend.notifications import telegram

log = logging.getLogger(__name__)

LINK_TOKEN_TTL_MINUTES = 10
# Позиция = число уже сделанных неудачных попыток; индекс задержки перед следующей.
RETRY_DELAYS_SECONDS = [0, 60, 300]
MAX_ATTEMPTS = len(RETRY_DELAYS_SECONDS)

RISK_NAMES = {'high': 'Критический', 'medium': 'Повышенный', 'low': 'Низкий', 'normal': 'Норма', 'insufficient': 'Недостаточно данных'}
INCIDENT_NAMES = {'fire': 'Пожар', 'flood': 'Подтопление', 'sensor_failure': 'Отказ датчика', 'intrusion_false_alarm': 'Ложная сработка', 'intrusion': 'Несанкционированный доступ'}


def format_message(session, notification: Record) -> tuple[str, str | None]:
    data = notification.data
    obj = session.get(Object, notification.object_id) if notification.object_id else None
    lines = [
        '🚨 ЧРЕЗВЫЧАЙНОЕ СООБЩЕНИЕ',
        'Объект: ' + (f'{obj.name} ({obj.tag})' if obj else str(notification.object_id or 'не указан')),
        'Тип: ' + INCIDENT_NAMES.get(data.get('incident_type'), str(data.get('incident_type'))),
        'Уровень: ' + RISK_NAMES.get(data.get('risk'), str(data.get('risk'))),
    ]
    if isinstance(data.get('probability'), (int, float)):
        lines.append(f'Вероятность: {round(data["probability"]*100)}%')
    lines += ['Время: ' + utc(notification.ts).strftime('%d.%m.%Y %H:%M UTC'), 'Статус: Требуется внимание сотрудника.']
    text = '\n'.join(lines)
    base = os.getenv('APP_PUBLIC_URL', '').rstrip('/')
    url = f'{base}/?prediction={data["prediction_id"]}' if base and data.get('prediction_id') else None
    return text, url


def queue_deliveries(session, notification: Record) -> list[NotificationDelivery]:
    """Идемпотентно ставит доставки в очередь. Не делает сетевых вызовов."""
    if not telegram.enabled():
        return []
    created = []
    for link in session.scalars(select(TelegramLink).where(TelegramLink.enabled.is_(True))):
        delivery_id = 'del:' + hashlib.sha256(f'{notification.id}:{link.username}:telegram'.encode()).hexdigest()[:24]
        if session.get(NotificationDelivery, delivery_id):
            continue
        delivery = NotificationDelivery(id=delivery_id, notification_id=notification.id, object_id=notification.object_id, username=link.username, channel='telegram', chat_id=link.chat_id, status='pending')
        session.add(delivery)
        created.append(delivery)
    return created


def due(delivery: NotificationDelivery, at) -> bool:
    if delivery.status == 'pending':
        return True
    if delivery.status != 'retry':
        return False
    index = min(delivery.attempts, len(RETRY_DELAYS_SECONDS) - 1)
    return (at - utc(delivery.updated_at)).total_seconds() >= RETRY_DELAYS_SECONDS[index]


def attempt_delivery(session, delivery: NotificationDelivery) -> None:
    notification = session.get(Record, delivery.notification_id)
    if notification is None:
        delivery.status, delivery.error_code, delivery.error_message = 'cancelled', 'notification_missing', 'Событие удалено'
        return
    text, url = format_message(session, notification)
    try:
        telegram.send_message(delivery.chat_id, text, url)
    except telegram.TelegramDeliveryError as exc:
        delivery.attempts += 1
        delivery.error_code, delivery.error_message = exc.code, str(exc)
        delivery.status = 'retry' if delivery.attempts < MAX_ATTEMPTS else 'failed'
        log.warning('Не доставлено уведомление %s получателю %s: код=%s попытка=%s', delivery.notification_id, delivery.username, exc.code, delivery.attempts)
        return
    delivery.status, delivery.sent_at, delivery.error_code, delivery.error_message = 'accepted', now(), None, None


def dispatch_pending(session, limit: int = 20) -> int:
    at = now()
    candidates = session.scalars(select(NotificationDelivery).where(NotificationDelivery.status.in_(('pending', 'retry'))).order_by(NotificationDelivery.created_at).limit(max(limit * 3, limit))).all()
    sent = 0
    for delivery in candidates:
        if sent >= limit:
            break
        if not due(delivery, at):
            continue
        delivery.status = 'sending'
        session.flush()
        attempt_delivery(session, delivery)
        session.flush()
        sent += 1
    return sent


def create_link_token(session, username: str) -> str:
    token = secrets.token_urlsafe(32)
    session.add(Record(id='telegram-link-token:' + token, kind='telegram_link_token', data={'username': username, 'expires_at': (now() + timedelta(minutes=LINK_TOKEN_TTL_MINUTES)).isoformat(), 'used': False}))
    return token


def consume_link_token(session, token: str) -> str | None:
    row = session.get(Record, 'telegram-link-token:' + token)
    if row is None or row.data.get('used') or utc(datetime.fromisoformat(row.data['expires_at'])) < now():
        return None
    row.data = {**row.data, 'used': True}
    return row.data['username']


def link_bind(session, username: str, chat_id: str) -> TelegramLink:
    other = session.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id, TelegramLink.username != username))
    if other is not None:
        session.delete(other)
        session.flush()
    link = session.get(TelegramLink, username)
    if link is None:
        link = TelegramLink(username=username, chat_id=chat_id, enabled=True)
        session.add(link)
    else:
        link.chat_id, link.enabled = chat_id, True
    return link
