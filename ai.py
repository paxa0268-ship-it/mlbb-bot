"""Claude bilan ishlash: suhbat tarixi, xatolarni tushunarli xabarga aylantirish."""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable

import anthropic
from anthropic import AsyncAnthropic

from config import Config
from prompts import SYSTEM_PROMPT

log = logging.getLogger("ai")

AlertFn = Callable[[str, str], Awaitable[None]]


class AIError(Exception):
    """user_msg — foydalanuvchiga, alert — adminga (bo'lsa) yuboriladi."""

    def __init__(self, user_msg: str, alert: tuple[str, str] | None = None):
        super().__init__(user_msg)
        self.user_msg = user_msg
        self.alert = alert  # (kalit, matn)


def _map_error(exc: Exception) -> AIError:
    msg = str(exc).lower()
    if isinstance(exc, anthropic.AuthenticationError):
        return AIError(
            "⚠️ Botning AI sozlamasida muammo bor. Admin xabardor qilindi, birozdan keyin urinib ko'r.",
            ("auth", "🔑 CLAUDE_API_KEY noto'g'ri yoki o'chirilgan. Yangi kalit oling va botni qayta ishga tushiring."),
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AIError(
            "⚠️ AI xizmatiga ruxsat yo'q. Admin xabardor qilindi.",
            ("perm", f"🚫 Claude API ruxsat bermadi: {exc}"),
        )
    if isinstance(exc, anthropic.NotFoundError):
        return AIError(
            "⚠️ AI modeli topilmadi. Admin xabardor qilindi.",
            ("model", "❓ MODEL nomi noto'g'ri yoki sizning akkauntingizda mavjud emas. .env dagi MODEL ni tekshiring."),
        )
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("🚦 Hozir juda band, 30 soniyadan keyin yana yozib ko'r!")
    if isinstance(exc, anthropic.BadRequestError):
        if "credit balance" in msg or "billing" in msg:
            return AIError(
                "⚠️ AI hisobida muammo bor. Admin xabardor qilindi.",
                ("billing", "💳 Anthropic hisobida balans tugagan. console.anthropic.com → Billing."),
            )
        return AIError("😵 Bu so'rovni qayta ishlay olmadim. Boshqacha yozib ko'r.")
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return AIError("📡 Ping ko'tarilib ketdi 😅 Birozdan keyin yana yozib ko'r!")
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code in (429, 500, 502, 503, 529):
            return AIError("🔥 Claude hozir band. 1 daqiqadan keyin urinib ko'r!")
    return AIError("⚠️ Kutilmagan xato yuz berdi. Birozdan keyin yana urinib ko'r.")


class AIClient:
    def __init__(self, cfg: Config, alert: AlertFn | None = None):
        self.cfg = cfg
        self._alert = alert
        self.client = AsyncAnthropic(api_key=cfg.claude_api_key, max_retries=3, timeout=90.0)
        self._search_ok = cfg.enable_web_search
        self.histories: dict[int, list[dict]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._last_call: dict[int, float] = {}

    # ---------- yordamchilar ----------
    def _lock(self, uid: int) -> asyncio.Lock:
        return self._locks.setdefault(uid, asyncio.Lock())

    def is_busy(self, uid: int) -> bool:
        return self._lock(uid).locked()

    def cooldown_left(self, uid: int) -> float:
        left = self.cfg.cooldown_sec - (time.monotonic() - self._last_call.get(uid, 0.0))
        return max(0.0, left)

    def reset(self, uid: int) -> None:
        self.histories.pop(uid, None)

    @property
    def web_search_enabled(self) -> bool:
        return self._search_ok

    async def _call(self, *, messages: list[dict], system: str, max_tokens: int, search: bool) -> str:
        kwargs: dict = dict(model=self.cfg.model, max_tokens=max_tokens, system=system, messages=messages)
        if search and self._search_ok:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]

        try:
            try:
                res = await self.client.messages.create(**kwargs)
            except anthropic.BadRequestError as exc:
                if "tools" not in kwargs:
                    raise
                # web search akkauntda yoqilmagan bo'lishi mumkin — qidiruvsiz qayta urinamiz
                log.warning("Web search bilan so'rov rad etildi (%s), qidiruvsiz qayta uriniladi", exc)
                kwargs.pop("tools")
                res = await self.client.messages.create(**kwargs)
                self._search_ok = False  # qayta urinish o'tdi => muammo qidiruvda edi
                log.warning("Web search o'chirildi (ENABLE_WEB_SEARCH yoqilgan, lekin akkauntda ishlamayapti)")
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001
            err = _map_error(exc)
            log.error("Claude xatosi (%s): %s", type(exc).__name__, exc)
            if err.alert and self._alert:
                await self._alert(*err.alert)
            raise err from exc

        text = "".join(b.text for b in res.content if getattr(b, "type", None) == "text").strip()
        if not text:
            raise AIError("🤔 Javob bo'sh chiqdi, savolni boshqacha yozib ko'r.")
        return text

    # ---------- ochiq metodlar ----------
    async def chat(
        self,
        uid: int,
        text: str,
        *,
        image: bytes | None = None,
        search: bool = False,
        history_text: str | None = None,
    ) -> str:
        """Tarixli suhbat. Xato bo'lsa tarix o'zgarmaydi (navbat buzilmaydi)."""
        async with self._lock(uid):
            self._last_call[uid] = time.monotonic()
            history = list(self.histories.get(uid, []))

            if image is not None:
                content: str | list = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.standard_b64encode(image).decode(),
                        },
                    },
                    {"type": "text", "text": text},
                ]
            else:
                content = text

            reply = await self._call(
                messages=history + [{"role": "user", "content": content}],
                system=SYSTEM_PROMPT,
                max_tokens=self.cfg.max_tokens,
                search=search,
            )

            history.append({"role": "user", "content": history_text or text})
            history.append({"role": "assistant", "content": reply})
            history = history[-self.cfg.history_limit :]
            while history and history[0]["role"] != "user":
                history.pop(0)
            self.histories[uid] = history
            return reply

    async def one_shot(self, system: str, prompt: str, *, uid: int | None = None, max_tokens: int = 1000) -> str:
        """Tarixsiz alohida so'rov (quiz, maslahat). uid berilsa — foydalanuvchi qulfi ishlatiladi."""
        if uid is None:
            return await self._call(
                messages=[{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens, search=False
            )
        async with self._lock(uid):
            self._last_call[uid] = time.monotonic()
            return await self._call(
                messages=[{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens, search=False
            )

    async def close(self) -> None:
        await self.client.close()
