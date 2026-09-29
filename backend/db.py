"""Транзакционное хранилище. Даты сохраняются в UTC."""
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from backend.settings import DATABASE_URL

class Base(DeclarativeBase):
    """Базовая схема SQLAlchemy."""


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

class Object(Base):
    __tablename__ = 'objects'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    tag: Mapped[str] = mapped_column(String, unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

class Channel(Base):
    __tablename__ = 'channels'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_id: Mapped[str] = mapped_column(ForeignKey('objects.id'), index=True)
    type_id: Mapped[int] = mapped_column(Integer)
    type_code: Mapped[str] = mapped_column(String)

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey('channels.id'), index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey('objects.id'), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    expected: Mapped[bool] = mapped_column(default=False)
    event: Mapped[str] = mapped_column(String, default='Норма')
    severity: Mapped[str] = mapped_column(String, default='normal')
    raw: Mapped[dict] = mapped_column(JSON, default=dict)

class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    object_id: Mapped[str | None] = mapped_column(String, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)

class Prediction(Base):
    __tablename__ = 'predictions'
    __table_args__ = (UniqueConstraint('request_id', 'object_id', 'incident_type', 'horizon_h', 'role'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey('objects.id'), index=True)
    incident_type: Mapped[str] = mapped_column(String, index=True)
    horizon_h: Mapped[int] = mapped_column(Integer)
    probability: Mapped[float | None] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    model_version: Mapped[str] = mapped_column(String)
    model_kind: Mapped[str] = mapped_column(String)
    contract_version: Mapped[str] = mapped_column(String, default='1.0')
    role: Mapped[str] = mapped_column(String, default='active', index=True)
    data_sufficiency: Mapped[str] = mapped_column(String)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

class Decision(Base):
    __tablename__ = 'decisions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    prediction_id: Mapped[str] = mapped_column(ForeignKey('predictions.id'), index=True)
    username: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    reason_version: Mapped[str] = mapped_column(String, default='1.0')
    comment: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String, default='monitoring')
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    username: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    status: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON, default=dict)

class User(Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)

class TelegramLink(Base):
    """Привязка Telegram-аккаунта к сотруднику. Без FK на users: в LDAP-режиме строки users нет."""
    __tablename__ = 'telegram_links'
    username: Mapped[str] = mapped_column(String, primary_key=True)
    chat_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class NotificationDelivery(Base):
    """Журнал доставки чрезвычайных уведомлений во внешние каналы (Telegram и далее)."""
    __tablename__ = 'notification_deliveries'
    __table_args__ = (UniqueConstraint('notification_id', 'username', 'channel'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    notification_id: Mapped[str] = mapped_column(ForeignKey('records.id'), index=True)
    object_id: Mapped[str | None] = mapped_column(String, index=True)
    username: Mapped[str] = mapped_column(String, index=True)
    channel: Mapped[str] = mapped_column(String, default='telegram')
    chat_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def init_db() -> None:
    Base.metadata.create_all(engine)


def serialize(row) -> dict:
    return {c.name: (utc(v).isoformat() if isinstance(v := getattr(row, c.name), datetime) else v) for c in row.__table__.columns}
