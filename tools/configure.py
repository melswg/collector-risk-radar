"""Однократная генерация секретов стенда; существующий .env сохраняется."""
from pathlib import Path
import secrets

path = Path('.env')
if not path.exists():
    text = Path('.env.example').read_text()
    while 'GENERATE_WITH_MAKE_CONFIGURE' in text:
        text = text.replace('GENERATE_WITH_MAKE_CONFIGURE', secrets.token_urlsafe(32), 1)
    path.write_text(text)
    path.chmod(0o600)
    print('Создан .env с независимыми случайными секретами. Демо-пароль находится в DEMO_PASSWORD.')
else:
    print('.env уже существует, секреты сохранены.')
