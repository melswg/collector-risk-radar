"""Тонкий клиент Telegram Bot API. Токен только из окружения, ни в логах, ни в исходниках."""
import logging
import os
import httpx

# Telegram сама зашивает токен в URL (/bot<TOKEN>/method — это её контракт API, не наш выбор).
# httpx по умолчанию логирует полный URL запроса на уровне INFO; глушим это здесь, а не только
# у вызывающего кода, чтобы токен не утёк в лог независимо от того, как настроено логирование
# в конкретном процессе (API, telegram_bot, будущий вызывающий код).
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


class TelegramDeliveryError(Exception):
    """Ошибка обращения к Telegram Bot API. code/retry_after не содержат токена."""

    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def enabled() -> bool:
    return os.getenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'false').lower() == 'true' and bool(os.getenv('TELEGRAM_BOT_TOKEN'))


def bot_username() -> str:
    return os.getenv('TELEGRAM_BOT_USERNAME', 'collector_risk_radar_aletrs_bot')


def mask_chat_id(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    return chat_id[:2] + '…' + chat_id[-2:] if len(chat_id) > 4 else '…' + chat_id[-1:]


def _client(timeout: float) -> httpx.Client:
    base = os.getenv('TELEGRAM_API_BASE_URL', 'https://api.telegram.org').rstrip('/')
    token = os.environ['TELEGRAM_BOT_TOKEN']
    return httpx.Client(base_url=f'{base}/bot{token}', timeout=timeout)


def call(method: str, payload: dict, timeout: float = 10.0) -> dict:
    """POST к Bot API. Токен виден только внутри httpx.Client (base_url), не в аргументах и не в исключениях."""
    try:
        with _client(timeout) as client:
            response = client.post('/' + method, json=payload)
    except httpx.TimeoutException as exc:
        raise TelegramDeliveryError('timeout', 'Превышено время ожидания ответа Telegram') from exc
    except httpx.TransportError as exc:
        raise TelegramDeliveryError('network', 'Telegram недоступен') from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise TelegramDeliveryError(str(response.status_code), 'Telegram вернул некорректный ответ') from exc
    if not body.get('ok'):
        retry_after = (body.get('parameters') or {}).get('retry_after')
        raise TelegramDeliveryError(str(body.get('error_code', response.status_code)), body.get('description', 'Ошибка Telegram API'), retry_after)
    return body['result']


def send_message(chat_id: str, text: str, url: str | None = None) -> dict:
    payload = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if url:
        payload['reply_markup'] = {'inline_keyboard': [[{'text': 'Открыть событие', 'url': url}]]}
    return call('sendMessage', payload)


def get_updates(offset: int | None, timeout: int = 25) -> list[dict]:
    payload = {'timeout': timeout, 'allowed_updates': ['message']}
    if offset is not None:
        payload['offset'] = offset
    return call('getUpdates', payload, timeout=timeout + 10)
