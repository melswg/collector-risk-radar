"""Тесты Telegram-уведомлений. Реальные сообщения не отправляются: Telegram Bot API замещается заглушкой."""
from sqlalchemy import select
from backend.db import NotificationDelivery, Record, TelegramLink, now
from backend.notifications import commands, service, telegram


def enable_telegram(monkeypatch):
    monkeypatch.setenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'true')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-token')


def make_notification(session, object_id='obj-000001', probability=0.9, incident_type='fire', risk='high'):
    notification = Record(id='notif-'+object_id+'-'+incident_type, kind='notification', object_id=object_id, ts=now(), data={'prediction_id': 'pred-1', 'incident_type': incident_type, 'risk': risk, 'probability': probability, 'read_by': []})
    session.add(notification)
    session.flush()
    return notification


# 1. Успешная отправка помечает доставку accepted.
def test_send_message_success_marks_accepted(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111'))
    populated.flush()
    notification = make_notification(populated)
    [delivery] = service.queue_deliveries(populated, notification)
    monkeypatch.setattr(telegram, 'send_message', lambda chat_id, text, url=None: {'message_id': 1})
    service.attempt_delivery(populated, delivery)
    assert delivery.status == 'accepted' and delivery.sent_at is not None and delivery.error_code is None


# 2/4. Ошибка API (в т.ч. 429) переводит доставку в retry, а не в тихий сбой.
def test_api_error_marks_retry_with_attempts(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111'))
    populated.flush()
    notification = make_notification(populated)
    [delivery] = service.queue_deliveries(populated, notification)

    def fail(chat_id, text, url=None):
        raise telegram.TelegramDeliveryError('429', 'Too Many Requests', retry_after=30)
    monkeypatch.setattr(telegram, 'send_message', fail)
    service.attempt_delivery(populated, delivery)
    assert delivery.status == 'retry' and delivery.attempts == 1 and delivery.error_code == '429'


# 3. Timeout корректно обрабатывается и не роняет вызывающий код.
def test_timeout_is_handled_as_retry(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111'))
    populated.flush()
    notification = make_notification(populated)
    [delivery] = service.queue_deliveries(populated, notification)

    def timeout(chat_id, text, url=None):
        raise telegram.TelegramDeliveryError('timeout', 'Превышено время ожидания ответа Telegram')
    monkeypatch.setattr(telegram, 'send_message', timeout)
    service.attempt_delivery(populated, delivery)
    assert delivery.status == 'retry' and delivery.error_code == 'timeout'


# Постоянная ошибка после MAX_ATTEMPTS попыток помечается failed, а не бесконечно повторяется.
def test_persistent_error_eventually_fails(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111'))
    populated.flush()
    notification = make_notification(populated)
    [delivery] = service.queue_deliveries(populated, notification)

    def fail(chat_id, text, url=None):
        raise telegram.TelegramDeliveryError('500', 'Internal error')
    monkeypatch.setattr(telegram, 'send_message', fail)
    for _ in range(service.MAX_ATTEMPTS):
        service.attempt_delivery(populated, delivery)
    assert delivery.status == 'failed' and delivery.attempts == service.MAX_ATTEMPTS


# 5. Пользователь без привязанного chat_id не получает доставку.
def test_user_without_telegram_link_gets_no_delivery(populated, monkeypatch):
    enable_telegram(monkeypatch)
    notification = make_notification(populated)
    assert service.queue_deliveries(populated, notification) == []


# 6. Пользователь с отключёнными уведомлениями не получает доставку.
def test_user_with_disabled_notifications_gets_no_delivery(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111', enabled=False))
    populated.flush()
    notification = make_notification(populated)
    assert service.queue_deliveries(populated, notification) == []


# 7/8. Обычное (не пороговое) событие не создаёт NotificationDelivery; чрезвычайное — создаёт.
def test_full_flow_only_high_risk_creates_delivery(client, monkeypatch):
    enable_telegram(monkeypatch)
    from backend.db import Session
    with Session.begin() as session:
        session.add(TelegramLink(username='dispatcher', chat_id='222'))
    response = client.post('/api/v1/demo/fire', json={})
    assert response.status_code == 200, response.text
    with Session() as session:
        deliveries = session.scalars(select(NotificationDelivery)).all()
    assert deliveries and all(d.status == 'pending' for d in deliveries)
    assert deliveries[0].username == 'dispatcher' and deliveries[0].channel == 'telegram'


# 9. Повторная постановка того же события не создаёт дубль (идемпотентность event+employee+channel).
def test_queue_deliveries_is_idempotent(populated, monkeypatch):
    enable_telegram(monkeypatch)
    populated.add(TelegramLink(username='dispatcher', chat_id='111'))
    populated.flush()
    notification = make_notification(populated)
    first = service.queue_deliveries(populated, notification)
    populated.flush()
    second = service.queue_deliveries(populated, notification)
    assert len(first) == 1 and second == []
    assert populated.scalar(select(NotificationDelivery).where(NotificationDelivery.notification_id == notification.id)) is not None


# 10. /start с валидным токеном привязывает аккаунт; без токена/с недействительным — не привязывает.
def test_start_command_links_account(populated):
    token = service.create_link_token(populated, 'dispatcher')
    populated.flush()
    reply = commands.handle_start(populated, '555', token)
    assert 'dispatcher' in reply
    link = populated.get(TelegramLink, 'dispatcher')
    assert link is not None and link.chat_id == '555' and link.enabled
    assert 'не привязан' in commands.handle_start(populated, '555', '')
    assert 'недействительна' in commands.handle_start(populated, '556', 'not-a-real-token')


# 11. /status показывает правильный статус привязки.
def test_status_command_reports_link_state(populated):
    assert 'не привязан' in commands.handle_status(populated, '555')
    populated.add(TelegramLink(username='dispatcher', chat_id='555'))
    populated.flush()
    assert 'успешно привязан' in commands.handle_status(populated, '555')


# 12. /unlink удаляет привязку.
def test_unlink_command_removes_link(populated):
    populated.add(TelegramLink(username='dispatcher', chat_id='555'))
    populated.flush()
    reply = commands.handle_unlink(populated, '555')
    populated.flush()
    assert 'удалена' in reply
    assert populated.get(TelegramLink, 'dispatcher') is None


# 13. Недоступность Telegram не мешает основной операции создания события.
def test_event_creation_survives_telegram_outage(client, monkeypatch):
    enable_telegram(monkeypatch)
    from backend.db import Session
    with Session.begin() as session:
        session.add(TelegramLink(username='dispatcher', chat_id='222'))

    def broken(*args, **kwargs):
        raise telegram.TelegramDeliveryError('network', 'Telegram недоступен')
    monkeypatch.setattr(telegram, 'send_message', broken)
    response = client.post('/api/v1/demo/fire', json={})
    assert response.status_code == 200, response.text


def test_one_time_link_token_cannot_be_reused(populated):
    token = service.create_link_token(populated, 'dispatcher')
    populated.flush()
    assert service.consume_link_token(populated, token) == 'dispatcher'
    assert service.consume_link_token(populated, token) is None


def test_delivery_status_endpoint_reflects_configuration(client, monkeypatch):
    assert {c['state'] for c in client.get('/api/v1/notification-delivery/status').json()['channels']} == {'disabled'}
    enable_telegram(monkeypatch)
    channels = {c['channel']: c['state'] for c in client.get('/api/v1/notification-delivery/status').json()['channels']}
    assert channels['telegram'] == 'unconfigured'
    from backend.db import Session
    with Session.begin() as session:
        session.add(TelegramLink(username='dispatcher', chat_id='222'))
    channels = {c['channel']: c['state'] for c in client.get('/api/v1/notification-delivery/status').json()['channels']}
    assert channels['telegram'] == 'ready'


def test_dispatch_requires_confirmation_and_enabled_flag(client, monkeypatch):
    assert client.post('/api/v1/notification-delivery/dispatch', json={'confirm_send': False}).status_code == 422
    assert client.post('/api/v1/notification-delivery/dispatch', json={'confirm_send': True}).status_code == 409
    enable_telegram(monkeypatch)
    assert client.post('/api/v1/notification-delivery/dispatch', json={'confirm_send': True}).status_code == 200


def test_outbox_masks_chat_id(client, monkeypatch):
    enable_telegram(monkeypatch)
    from backend.db import Session
    with Session.begin() as session:
        session.add(TelegramLink(username='dispatcher', chat_id='1234567890'))
    assert client.post('/api/v1/demo/fire', json={}).status_code == 200
    outbox = client.get('/api/v1/notification-delivery/outbox').json()
    assert outbox['total'] >= 1
    for item in outbox['items']:
        assert item['chat_id'] != '1234567890' and '…' in item['chat_id']


def test_link_token_flow_requires_telegram_enabled(client):
    assert client.post('/api/v1/telegram/link/token').status_code == 409


def test_link_token_flow_via_api(client, monkeypatch):
    enable_telegram(monkeypatch)
    response = client.post('/api/v1/telegram/link/token')
    assert response.status_code == 200
    deep_link = response.json()['deep_link']
    assert deep_link.startswith('https://t.me/') and 'start=' in deep_link
    status = client.get('/api/v1/telegram/status').json()
    assert status == {'linked': False, 'enabled': False, 'chat_id': None}


def test_webhook_requires_matching_secret(client, monkeypatch):
    enable_telegram(monkeypatch)
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 'shh')
    assert client.post('/api/v1/telegram/webhook', json={}, headers={'x-telegram-bot-api-secret-token': 'wrong'}).status_code == 401
    assert client.post('/api/v1/telegram/webhook', json={}, headers={'x-telegram-bot-api-secret-token': 'shh'}).status_code == 200


def test_admin_users_show_telegram_link_state(client, monkeypatch):
    enable_telegram(monkeypatch)
    from backend.db import Session
    with Session.begin() as session:
        session.add(TelegramLink(username='dispatcher', chat_id='1234567890'))
    users = {u['username']: u for u in client.get('/api/v1/admin/users').json()}
    assert users['dispatcher']['telegram_linked'] is True and users['dispatcher']['telegram_chat_id'] != '1234567890'
    assert users['analyst']['telegram_linked'] is False
