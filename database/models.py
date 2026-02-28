"""
📦 Модели базы данных — SQLAlchemy 2.0 async
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, Text,
    ForeignKey, Float, Enum as SAEnum, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class PlanEnum(str, enum.Enum):
    free      = "free"
    basic     = "basic"
    pro       = "pro"
    unlimited = "unlimited"


class MessageTypeEnum(str, enum.Enum):
    text   = "text"
    image  = "image"
    voice  = "voice"
    file   = "file"


class TransactionTypeEnum(str, enum.Enum):
    subscription = "subscription"
    topup        = "topup"
    refund       = "refund"
    referral     = "referral"
    bonus        = "bonus"


# ── Пользователи ──────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:               Mapped[int]            = mapped_column(BigInteger, primary_key=True)
    username:         Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    first_name:       Mapped[str]            = mapped_column(String(64), default="")
    last_name:        Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    language_code:    Mapped[str]            = mapped_column(String(8), default="ru")

    # Подписка
    plan:             Mapped[PlanEnum]       = mapped_column(SAEnum(PlanEnum), default=PlanEnum.free)
    plan_expires:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_admin:         Mapped[bool]           = mapped_column(Boolean, default=False)
    is_banned:        Mapped[bool]           = mapped_column(Boolean, default=False)
    ban_reason:       Mapped[Optional[str]]  = mapped_column(String(256), nullable=True)

    # Счётчики дня
    today_messages:   Mapped[int]            = mapped_column(Integer, default=0)
    today_images:     Mapped[int]            = mapped_column(Integer, default=0)
    today_voice:      Mapped[int]            = mapped_column(Integer, default=0)
    last_reset:       Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Общая статистика
    total_messages:   Mapped[int]            = mapped_column(Integer, default=0)
    total_images:     Mapped[int]            = mapped_column(Integer, default=0)
    total_voice:      Mapped[int]            = mapped_column(Integer, default=0)
    total_spent:      Mapped[float]          = mapped_column(Float, default=0.0)

    # Реферальная система
    referrer_id:      Mapped[Optional[int]]  = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    referral_count:   Mapped[int]            = mapped_column(Integer, default=0)
    referral_bonus:   Mapped[int]            = mapped_column(Integer, default=0)  # бонусные сообщения

    # Настройки
    ai_personality:   Mapped[str]            = mapped_column(String(32), default="default")
    language:         Mapped[str]            = mapped_column(String(8), default="ru")
    voice_enabled:    Mapped[bool]           = mapped_column(Boolean, default=True)
    notifications:    Mapped[bool]           = mapped_column(Boolean, default=True)
    tts_voice:        Mapped[str]            = mapped_column(String(64), default="ru-RU-Standard-A")

    # Даты
    created_at:       Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:       Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity:    Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Связи
    messages:     "Mapped[list[Message]]"     = relationship("Message", back_populates="user", lazy="select")
    transactions: "Mapped[list[Transaction]]" = relationship("Transaction", back_populates="user", lazy="select")
    presets:      "Mapped[list[Preset]]"      = relationship("Preset", back_populates="user", lazy="select")
    referrals:    "Mapped[list[User]]"        = relationship("User", foreign_keys=[referrer_id], lazy="select")

    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_plan", "plan"),
        Index("ix_users_referrer", "referrer_id"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} plan={self.plan}>"

    @property
    def display_name(self) -> str:
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"User {self.id}"

    @property
    def is_plan_active(self) -> bool:
        if self.plan == PlanEnum.free:
            return True
        if self.plan_expires is None:
            return False
        return self.plan_expires > datetime.utcnow()


# ── Сообщения / история диалогов ──────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id:          Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:     Mapped[int]             = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    role:        Mapped[str]             = mapped_column(String(16))          # user / assistant
    content:     Mapped[str]             = mapped_column(Text)
    msg_type:    Mapped[MessageTypeEnum] = mapped_column(SAEnum(MessageTypeEnum), default=MessageTypeEnum.text)
    tokens_used: Mapped[int]             = mapped_column(Integer, default=0)
    model_used:  Mapped[str]             = mapped_column(String(64), default="")
    latency_ms:  Mapped[int]             = mapped_column(Integer, default=0)  # время ответа в мс
    created_at:  Mapped[datetime]        = mapped_column(DateTime, default=datetime.utcnow)

    user: "Mapped[User]" = relationship("User", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_user_id", "user_id"),
        Index("ix_messages_created_at", "created_at"),
    )


# ── Транзакции / платежи ──────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    id:               Mapped[int]                   = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:          Mapped[int]                   = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    transaction_type: Mapped[TransactionTypeEnum]   = mapped_column(SAEnum(TransactionTypeEnum))
    plan:             Mapped[Optional[str]]         = mapped_column(String(16), nullable=True)
    amount_usd:       Mapped[float]                 = mapped_column(Float, default=0.0)
    amount_rub:       Mapped[float]                 = mapped_column(Float, default=0.0)
    days:             Mapped[int]                   = mapped_column(Integer, default=30)
    payment_method:   Mapped[Optional[str]]         = mapped_column(String(32), nullable=True)
    payment_id:       Mapped[Optional[str]]         = mapped_column(String(128), nullable=True)
    status:           Mapped[str]                   = mapped_column(String(16), default="pending")
    note:             Mapped[Optional[str]]         = mapped_column(String(256), nullable=True)
    created_at:       Mapped[datetime]              = mapped_column(DateTime, default=datetime.utcnow)
    admin_id:         Mapped[Optional[int]]         = mapped_column(BigInteger, nullable=True)  # кто выдал

    user: "Mapped[User]" = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_status", "status"),
    )


# ── Пресеты / персоналити ─────────────────────────────────────────────────────

class Preset(Base):
    __tablename__ = "presets"

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:     Mapped[int]            = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name:        Mapped[str]            = mapped_column(String(64))
    prompt:      Mapped[str]            = mapped_column(Text)
    is_active:   Mapped[bool]           = mapped_column(Boolean, default=False)
    created_at:  Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    user: "Mapped[User]" = relationship("User", back_populates="presets")

    __table_args__ = (
        Index("ix_presets_user_id", "user_id"),
    )


# ── Глобальные настройки бота ─────────────────────────────────────────────────

class BotSetting(Base):
    __tablename__ = "bot_settings"

    key:        Mapped[str]  = mapped_column(String(64), primary_key=True)
    value:      Mapped[str]  = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Системные промпты ─────────────────────────────────────────────────────────

class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id:          Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    key:         Mapped[str]   = mapped_column(String(64), unique=True)  # default, coder, creative...
    name:        Mapped[str]   = mapped_column(String(64))
    emoji:       Mapped[str]   = mapped_column(String(8), default="🤖")
    prompt:      Mapped[str]   = mapped_column(Text)
    is_premium:  Mapped[bool]  = mapped_column(Boolean, default=False)  # только для платных
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Статистика бота (агрегированная) ─────────────────────────────────────────

class BotStats(Base):
    __tablename__ = "bot_stats"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    date:             Mapped[datetime] = mapped_column(DateTime)
    new_users:        Mapped[int]      = mapped_column(Integer, default=0)
    active_users:     Mapped[int]      = mapped_column(Integer, default=0)
    total_messages:   Mapped[int]      = mapped_column(Integer, default=0)
    total_images:     Mapped[int]      = mapped_column(Integer, default=0)
    total_voice:      Mapped[int]      = mapped_column(Integer, default=0)
    revenue_usd:      Mapped[float]    = mapped_column(Float, default=0.0)
    new_subscribers:  Mapped[int]      = mapped_column(Integer, default=0)
