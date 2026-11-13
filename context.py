"""Ilova holati: bot, baza, AI, admin xabarnomalari."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ai import AIClient
from config import Config
from db import Database

log = logging.getLogger("ctx")


@dataclass
class Quiz:
    situation: str
    options: list[str]
    correct: int
    explanation: str
    message_id: int = 0
    answered: bool = False


@dataclass
class Context:
    cfg: Config
    bot: Bot
    db: Database
    admin_id: int | None
    ai: AIClient = field(init=False)
    quizzes: dict[int, Quiz] = field(default_factory=dict)
    modes: dict[int, str] = field(default_factory=dict)  # "hero" | "counter"
    _alert_times: dict[str, float] = field(default_factory=dict)
    _admin_warned: bool = False

    def __post_init__(self) -> None:
        self.ai = AIClient(self.cfg, alert=self.alert)

    def is_admin(self, uid: int | None) -> bool:
        return self.admin_id is not None and uid == self.admin_id

    async def notify_admin(self, text: str) -> bool:
        if self.admin_id is None:
            log.info("ADMIN xabari (admin sozlanmagan): %s", text)
            return False
        try:
            await self.bot.send_message(self.admin_id, text, parse_mode=None)
            return True
        except TelegramAPIError as exc:
            if not self._admin_warned:
                self._admin_warned = True
                log.warning(
                    "Adminga xabar yuborib bo'lmadi (%s). Admin botga /start bosganiga va "
                    "ADMIN_ID to'g'riligiga ishonch hosil qiling (/id buyrug'i bilan bilib oling).",
                    exc,
                )
            return False

    async def alert(self, key: str, text: str, *, every: float = 600.0) -> None:
        """Bir xil ogohlantirishni har 10 daqiqada ko'pi bilan bir marta yuboradi."""
        now = time.monotonic()
        if now - self._alert_times.get(key, -every) < every:
            return
        self._alert_times[key] = now
        await self.notify_admin(f"🚨 {text}")

    def remember_quiz(self, uid: int, quiz: Quiz) -> None:
        if len(self.quizzes) > 5000:
            self.quizzes.pop(next(iter(self.quizzes)))
        self.quizzes[uid] = quiz
