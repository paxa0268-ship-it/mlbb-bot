"""MLBB Murabbiy boti — kirish nuqtasi.  Ishga tushirish:  python bot.py"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.types import BotCommand, BotCommandScopeChat

from config import ConfigError, load_config
from context import Context
from db import Database
from handlers import UserTracker, router

log = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="start", description="Botni boshlash"),
    BotCommand(command="menu", description="Menyuni ochish"),
    BotCommand(command="hero", description="Geroy qo'llanmasi"),
    BotCommand(command="counter", description="Counter-pick"),
    BotCommand(command="meta", description="Hozirgi meta"),
    BotCommand(command="quiz", description="Vaziyatli o'yin testi"),
    BotCommand(command="tips", description="Pro maslahatlar"),
    BotCommand(command="profile", description="Profilim"),
    BotCommand(command="reset", description="Suhbatni tozalash"),
    BotCommand(command="id", description="Mening ID raqamim"),
    BotCommand(command="help", description="Yordam"),
]
ADMIN_COMMANDS = COMMANDS + [
    BotCommand(command="stats", description="Statistika (admin)"),
    BotCommand(command="broadcast", description="Hammaga xabar (admin)"),
]


async def connect(bot: Bot):
    """Telegramga ulanadi (tarmoq xatosida qayta urinadi)."""
    for attempt in range(1, 6):
        try:
            return await bot.get_me()
        except TelegramUnauthorizedError:
            log.critical("❌ Telegram tokeni noto'g'ri yoki bekor qilingan. @BotFather dan yangisini oling.")
            raise SystemExit(1)
        except TelegramNetworkError as exc:
            log.warning("Telegramga ulanib bo'lmadi (%d/5): %s", attempt, exc)
            await asyncio.sleep(3 * attempt)
    log.critical("❌ Telegramga ulanib bo'lmadi. Internetni tekshiring.")
    raise SystemExit(1)


async def main() -> None:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"❌ Sozlama xatosi: {exc}", file=sys.stderr)
        raise SystemExit(1)

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    bot = Bot(token=cfg.telegram_token)
    me = await connect(bot)

    admin_id = cfg.admin_id
    if admin_id is not None and admin_id == me.id:
        log.error(
            "⚠️ ADMIN_ID (%s) — bu botning o'z ID si (tokenning boshidagi raqam)! "
            "Bot o'ziga xabar yubora olmaydi. O'z ID ingizni bilish uchun botga /id yozing "
            "va ADMIN_ID ni shunga almashtiring. Hozircha admin funksiyalari o'chiq.",
            admin_id,
        )
        admin_id = None
    elif admin_id is None:
        log.warning("ADMIN_ID berilmagan — admin funksiyalari o'chiq. Botga /id yozib ID ingizni bilib oling.")

    db = Database(cfg.db_path)
    ctx = Context(cfg=cfg, bot=bot, db=db, admin_id=admin_id)

    dp = Dispatcher(ctx=ctx)
    dp.update.outer_middleware(UserTracker())
    dp.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands(COMMANDS)
        if admin_id:
            try:
                await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
            except Exception as exc:  # noqa: BLE001
                log.warning("Admin buyruqlarini o'rnatib bo'lmadi: %s", exc)

        log.info("✅ @%s ishga tushdi | model=%s | web_search=%s", me.username, cfg.model, ctx.ai.web_search_enabled)
        await ctx.notify_admin(f"✅ @{me.username} ishga tushdi\nModel: {cfg.model}")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await ctx.ai.close()
        db.close()
        await bot.session.close()
        log.info("Bot to'xtadi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
