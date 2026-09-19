"""RBAC, ограниченная JWT-сессия, LDAP и отдельный демонстрационный режим."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from backend.db import Session, User, now

ROLES = ['dispatcher', 'analyst', 'manager', 'technician', 'admin']
_SECRET = os.getenv('JWT_SECRET') or secrets.token_urlsafe(48)
if os.getenv('ENVIRONMENT') == 'production' and not os.getenv('JWT_SECRET'):
    raise RuntimeError('В production требуется JWT_SECRET')


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def login(username, password):
    if os.getenv('AUTH_MODE', 'demo') == 'ldap':
        from ldap3 import Server, Connection, Tls
        from ldap3.utils.conv import escape_filter_chars
        import ssl
        host = os.environ['LDAP_HOST']
        server = Server(host, use_ssl=True, tls=Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=os.getenv('LDAP_CA_FILE')), connect_timeout=5)
        with Connection(server, user=os.environ['LDAP_BIND_DN'], password=os.environ['LDAP_BIND_PASSWORD'], auto_bind=True) as conn:
            conn.search(os.environ['LDAP_BASE_DN'], f'(uid={escape_filter_chars(username)})', attributes=['memberOf'])
            if len(conn.entries) != 1:
                raise HTTPException(401, 'Неверные учётные данные')
            entry = conn.entries[0]
            groups = str(entry.memberOf) if 'memberOf' in entry else ''
            role = next((r for r in reversed(ROLES) if f'cn={r},' in groups), 'technician')
            with Connection(server, user=entry.entry_dn, password=password, auto_bind=True):
                user = {'username': username, 'role': role}
    else:
        with Session() as session:
            record = session.get(User, username)
            if record is None or not hmac.compare_digest(password_hash(password, record.password_hash.split(':')[0]), record.password_hash):
                raise HTTPException(401, 'Неверные учётные данные')
            user = {'username': username, 'role': record.role}
    token = jwt.encode({**user, 'exp': now()+timedelta(hours=1), 'iat': now(), 'iss': 'moscollector'}, _SECRET, algorithm='HS256')
    return token, user


def current_user(request: Request):
    token = request.cookies.get('session') or request.headers.get('Authorization', '').removeprefix('Bearer ')
    try:
        payload = jwt.decode(token, _SECRET, algorithms=['HS256'], issuer='moscollector')
        if payload['role'] not in ROLES:
            raise ValueError('Роль')
        request.state.username = payload['username']
        return payload
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, 'Требуется вход')


def require(*roles):
    def check(user=Depends(current_user)):
        if user['role'] not in roles and user['role'] != 'admin':
            raise HTTPException(403, 'Недостаточно прав')
        return user
    return check


def seed_users(session):
    password = os.getenv('DEMO_PASSWORD')
    if not password or len(password) < 12:
        raise ValueError('Задайте DEMO_PASSWORD длиной не менее 12 символов')
    for role in ROLES:
        if session.get(User, role) is None:
            session.add(User(username=role, role=role, password_hash=password_hash(password)))
