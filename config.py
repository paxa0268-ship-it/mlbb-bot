"""Sozlamalar: hamma narsa muhit o'zgaruvchilaridan (.env yoki hosting paneli) o'qiladi."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


class ConfigError(Exception):
    """Sozlamalarda xato bo'lsa ko'tariladi (xabar foydalanuvchiga ko'rsatiladi)."""


@dataclass(frozen=True)
class Config:
    telegram_token: str
    claude_api_key: str
    admin_id: int | None
    model: str
    max_tokens: int
    history_limit: int
    cooldown_sec: float
    daily_limit: int
    enable_web_search: bool
    notify_new_users: bool
    db_path: str
    log_level: str

    @property
    def token_bot_id(self) -> int:
        """Tokenning boshidagi raqam — bu BOTNING o'z ID si."""
        return int(self.telegram_token.split(":", 1)[0])


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip().strip('"').strip("'")


def _int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} butun son bo'lishi kerak, hozir: {raw!r}")


def _float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} son bo'lishi kerak, hozir: {raw!r}")


def _bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ha"}


def load_config() -> Config:
    token = _env("TELEGRAM_TOKEN") or _env("BOT_TOKEN")
    if not token:
        raise ConfigError("TELEGRAM_TOKEN topilmadi. @BotFather dan olgan tokeningizni .env ga yozing.")
    if not TOKEN_RE.match(token):
        raise ConfigError("TELEGRAM_TOKEN formati noto'g'ri. U '123456789:AAxxxxxxxx...' ko'rinishida bo'lishi kerak.")

    api_key = _env("CLAUDE_API_KEY") or _env("ANTHROPIC_API_KEY")
    if not api_key:
        raise ConfigError(
            "CLAUDE_API_KEY topilmadi. https://console.anthropic.com/ saytidan API kalit oling "
            "va .env faylga CLAUDE_API_KEY=sk-ant-... deb yozing."
        )

    admin_raw = _env("ADMIN_ID")
    admin_id: int | None = None
    if admin_raw:
        try:
            admin_id = int(admin_raw)
        except ValueError:
            raise ConfigError(f"ADMIN_ID butun son bo'lishi kerak, hozir: {admin_raw!r}")

    return Config(
        telegram_token=token,
        claude_api_key=api_key,
        admin_id=admin_id,
        model=_env("MODEL", "claude-sonnet-5-5"),
        max_tokens=_int("MAX_TOKENS", 1200),
        history_limit=max(2, _int("HISTORY_LIMIT", 12)),
        cooldown_sec=_float("COOLDOWN_SEC", 2.0),
        daily_limit=_int("DAILY_LIMIT", 60),
        enable_web_search=_bool("ENABLE_WEB_SEARCH", False),
        notify_new_users=_bool("NOTIFY_NEW_USERS", True),
        db_path=_env("DB_PATH", "bot.db"),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
    )
