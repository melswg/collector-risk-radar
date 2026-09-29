"""Обработка команд Telegram-бота. Используется и webhook-эндпоинтом, и процессом polling."""
import logging
from sqlalchemy import select
from backend.db import TelegramLink
from backend.notifications import service, telegram

log = logging.getLogger(__name__)

HELP_TEXT = ('Доступные команды:\n'
             '/start — привязать Telegram к аккаунту сотрудника\n'
             '/status — показать статус привязки\n'
             '/unlink — отвязать Telegram от аккаунта\n'
             '/help — показать это сообщение')

NOT_LINKED_TEXT = ('Ваш Telegram пока не привязан к аккаунту сотрудника. Для привязки необходимо пройти '
                    'процедуру идентификации: войдите в веб-приложение «Москоллектор» под своей учётной записью '
                    'и запросите ссылку привязки в настройках уведомлений.')


def handle_start(session, chat_id: str, token: str) -> str:
    if not token:
        return NOT_LINKED_TEXT
    username = service.consume_link_token(session, token)
    if not username:
        return 'Ссылка для привязки недействительна или её срок истёк. Запросите новую ссылку в веб-приложении.'
    service.link_bind(session, username, chat_id)
    return f'Telegram успешно привязан к аккаунту сотрудника «{username}».'


def handle_status(session, chat_id: str) -> str:
    link = session.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id))
    if link is None:
        return 'Telegram не привязан к аккаунту сотрудника.'
    if not link.enabled:
        return f'Telegram привязан к аккаунту «{link.username}», но уведомления отключены в веб-приложении.'
    return f'Telegram успешно привязан к вашему аккаунту сотрудника («{link.username}»).'


def handle_unlink(session, chat_id: str) -> str:
    link = session.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id))
    if link is None:
        return 'Telegram не привязан к аккаунту сотрудника.'
    session.delete(link)
    return 'Привязка Telegram удалена. Уведомления больше не отправляются.'


def handle_update(session, update: dict) -> None:
    """Валидирует и обрабатывает один Telegram Update. Некорректные апдейты тихо игнорируются."""
    if not isinstance(update, dict):
        return
    message = update.get('message')
    if not isinstance(message, dict):
        return
    chat = message.get('chat')
    text = message.get('text')
    if not isinstance(chat, dict) or not isinstance(text, str) or not text.startswith('/'):
        return
    chat_id = str(chat.get('id') or '')
    if not chat_id:
        return
    command, _, arg = text.strip().partition(' ')
    command = command.split('@')[0].lower()
    handlers = {'/start': lambda: handle_start(session, chat_id, arg.strip()), '/status': lambda: handle_status(session, chat_id), '/unlink': lambda: handle_unlink(session, chat_id), '/help': lambda: HELP_TEXT}
    reply = handlers.get(command, lambda: 'Неизвестная команда.\n\n' + HELP_TEXT)()
    try:
        telegram.send_message(chat_id, reply)
    except telegram.TelegramDeliveryError:
        log.warning('Не удалось отправить ответ на команду %s', command)
