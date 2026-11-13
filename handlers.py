"""Barcha handlerlar: buyruqlar, menyu tugmalari, quiz, maslahatlar, rasm tahlili, admin."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import random

from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart, Filter
from aiogram.types import CallbackQuery, ErrorEvent, LinkPreviewOptions, Message
from aiogram.utils.chat_action import ChatActionSender

from ai import AIError
from context import Context, Quiz
from formatting import TG_LIMIT, md_to_html, plain, split_text
from keyboards import (
    BTN_COUNTER,
    BTN_HERO,
    BTN_META,
    BTN_PROFILE,
    BTN_QUIZ,
    BTN_TIPS,
    main_menu,
    meta_kb,
    quiz_kb,
    quiz_next_kb,
    tip_again_kb,
    tips_kb,
)
from prompts import (
    COUNTER_PROMPT,
    HERO_PROMPT,
    LANES,
    META_PROMPT,
    PHOTO_DEFAULT,
    QUIZ_LEVELS,
    QUIZ_PROMPT,
    QUIZ_SYSTEM,
    QUIZ_TOPICS,
    TIP_AUDIENCES,
    TIP_CATEGORIES,
    TIP_PROMPT,
)

log = logging.getLogger("handlers")
router = Router(name="main")

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
MAX_INPUT = 2000
MAX_PHOTO_BYTES = 5 * 1024 * 1024


# ============================================================ yordamchilar
class IsAdmin(Filter):
    async def __call__(self, message: Message, ctx: Context) -> bool:
        return bool(message.from_user) and ctx.is_admin(message.from_user.id)


class UserTracker(BaseMiddleware):
    """Har bir yangilanishda foydalanuvchini bazaga yozadi, yangi bo'lsa adminga xabar beradi."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        ctx: Context | None = data.get("ctx")
        if user and ctx and not user.is_bot:
            try:
                is_new = await ctx.db.upsert_user(user.id, user.username, user.first_name)
                if is_new and ctx.cfg.notify_new_users and not ctx.is_admin(user.id):
                    uname = f"@{user.username}" if user.username else "username yo'q"
                    await ctx.notify_admin(f"🆕 Yangi foydalanuvchi: {user.full_name} ({uname}), ID: {user.id}")
            except Exception:  # noqa: BLE001 — baza xatosi botni to'xtatmasin
                log.exception("Foydalanuvchini saqlashda xato")
        return await handler(event, data)


async def safe_send(ctx: Context, chat_id: int, text_md: str, markup=None) -> None:
    """HTML bilan yuboradi; Telegram rad etsa — oddiy matn bilan."""
    html_text = md_to_html(text_md)
    if len(html_text) <= TG_LIMIT:
        for _ in range(2):
            try:
                await ctx.bot.send_message(
                    chat_id, html_text, parse_mode=ParseMode.HTML, reply_markup=markup, link_preview_options=NO_PREVIEW
                )
                return
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramBadRequest as exc:
                log.warning("HTML qabul qilinmadi (%s) — oddiy matn yuboriladi", exc)
                break

    parts = split_text(plain(text_md), 3900) or ["…"]
    for i, part in enumerate(parts):
        await ctx.bot.send_message(
            chat_id,
            part,
            parse_mode=None,
            reply_markup=markup if i == len(parts) - 1 else None,
            link_preview_options=NO_PREVIEW,
        )


async def send_long(ctx: Context, chat_id: int, text: str, *, markup=None, footer: str | None = None) -> None:
    chunks = split_text(text) or ["…"]
    if footer:
        chunks[-1] += f"\n\n{footer}"
    for i, chunk in enumerate(chunks):
        await safe_send(ctx, chat_id, chunk, markup if i == len(chunks) - 1 else None)


async def check_quota(ctx: Context, uid: int) -> str | None:
    """Foydalanuvchi hozir so'rov yubora oladimi? Yo'q bo'lsa — sababi matni."""
    if ctx.ai.is_busy(uid):
        return "⏳ Oldingi savolingga javob yozyapman, ozgina kut!"
    if ctx.ai.cooldown_left(uid) > 0:
        return "🐢 Sekinroq, bro! 2-3 soniya kutib, qayta yoz."
    if not ctx.is_admin(uid) and await ctx.db.get_usage(uid) >= ctx.cfg.daily_limit:
        return f"🛑 Bugungi limit ({ctx.cfg.daily_limit} ta so'rov) tugadi. Ertaga yana davom etamiz! 🎮"
    return None


async def ai_reply(
    ctx: Context,
    chat_id: int,
    uid: int,
    text: str,
    *,
    image: bytes | None = None,
    search: bool = False,
    history_text: str | None = None,
    markup=None,
    footer: str | None = None,
) -> None:
    problem = await check_quota(ctx, uid)
    if problem:
        await ctx.bot.send_message(chat_id, problem, parse_mode=None)
        return
    async with ChatActionSender.typing(bot=ctx.bot, chat_id=chat_id):
        try:
            reply = await ctx.ai.chat(uid, text, image=image, search=search, history_text=history_text)
        except AIError as err:
            if err.alert:
                await ctx.alert(*err.alert)
            await ctx.bot.send_message(chat_id, err.user_msg, parse_mode=None)
            return
    await ctx.db.inc_usage(uid)
    await send_long(ctx, chat_id, reply, markup=markup, footer=footer)


def clean_name(raw: str | None) -> str:
    return " ".join((raw or "").split())[:60]


def rank_title(total: int, right: int) -> str:
    if total < 5:
        return "🪖 Warrior (kamida 5 ta test yech)"
    pct = right / total * 100
    if pct >= 85:
        return "👑 Mythical Glory"
    if pct >= 70:
        return "💎 Mythic"
    if pct >= 55:
        return "🏆 Legend"
    if pct >= 40:
        return "⚜️ Epic"
    return "🥈 Grandmaster"


HELP_TEXT = (
    "🎮 <b>MLBB Murabbiy — nima qila olaman?</b>\n\n"
    "🦸‍♂️ <b>Geroy o'rganish</b> — geroy nomini yoz: rol, combo, build, counter\n"
    "⚔️ <b>Counter-Pick</b> — dushman geroyiga qarshi nima olish\n"
    "🔥 <b>Hozirgi Meta</b> — lane bo'yicha kuchli geroylar\n"
    "🎮 <b>Vaziyatli O'yin</b> — real o'yin vaziyatlari bo'yicha test\n"
    "💡 <b>Pro Maslahatlar</b> — mavzu bo'yicha tiplar\n"
    "📸 <b>Skrinshot</b> yubor — draft, build yoki o'yin natijasini tahlil qilaman\n"
    "💬 Yoki shunchaki savol yoz — murabbiy javob beradi\n\n"
    "<b>Buyruqlar:</b>\n"
    "/hero <i>nom</i> · /counter <i>nom</i> · /meta · /quiz · /tips\n"
    "/profile · /reset (suhbatni tozalash) · /id · /help"
)

ADMIN_HELP = (
    "\n\n🔐 <b>Admin:</b>\n"
    "/stats — statistika\n"
    "/broadcast <i>matn</i> — hammaga xabar yuborish"
)


# ============================================================ asosiy buyruqlar
@router.message(CommandStart())
async def cmd_start(msg: Message, ctx: Context) -> None:
    uid = msg.from_user.id
    ctx.ai.reset(uid)
    ctx.modes.pop(uid, None)
    name = html.escape(msg.from_user.first_name or "bro")
    await msg.answer(
        f"Salom, <b>{name}</b>! 👋\n\n"
        "Men — MLBB bo'yicha shaxsiy murabbiyingman. Geroy, build, counter, meta — hammasini "
        "gamer tilida tushuntiraman.\n\n"
        "Geroy nomini yoz yoki pastdagi menyudan tanla 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(msg: Message, ctx: Context) -> None:
    text = HELP_TEXT + (ADMIN_HELP if ctx.is_admin(msg.from_user.id) else "")
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(msg: Message) -> None:
    await msg.answer("Menyu 👇", reply_markup=main_menu())


@router.message(Command("reset"))
async def cmd_reset(msg: Message, ctx: Context) -> None:
    ctx.ai.reset(msg.from_user.id)
    ctx.modes.pop(msg.from_user.id, None)
    await msg.answer("🧹 Suhbat tozalandi. Yangi sahifadan boshlaymiz!")


@router.message(Command("id"))
async def cmd_id(msg: Message) -> None:
    await msg.answer(
        f"🆔 Sizning ID: <code>{msg.from_user.id}</code>\nChat ID: <code>{msg.chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("profile"))
@router.message(F.text == BTN_PROFILE)
async def cmd_profile(msg: Message, ctx: Context) -> None:
    uid = msg.from_user.id
    ctx.modes.pop(uid, None)
    user = await ctx.db.get_user(uid)
    if not user:
        await msg.answer("Avval /start bos 🙂")
        return
    used = await ctx.db.get_usage(uid)
    limit = "∞" if ctx.is_admin(uid) else str(ctx.cfg.daily_limit)
    total, right = user["quiz_total"], user["quiz_right"]
    pct = f"{right / total * 100:.0f}%" if total else "—"
    await msg.answer(
        f"👤 <b>{html.escape(user['first_name'] or 'Profil')}</b>\n\n"
        f"🏅 Daraja: {rank_title(total, right)}\n"
        f"🎮 Test: {right}/{total} to'g'ri ({pct})\n"
        f"💬 Jami savollar: {user['requests']}\n"
        f"⚡ Bugungi limit: {used}/{limit}\n"
        f"📅 Qo'shilgan: {user['joined_at'][:10]}",
        parse_mode=ParseMode.HTML,
    )


# ============================================================ geroy / counter / meta
async def run_hero(msg: Message, ctx: Context, name: str) -> None:
    await ai_reply(
        ctx, msg.chat.id, msg.from_user.id,
        HERO_PROMPT.format(name=name), history_text=f"Geroy qo'llanmasi: {name}",
    )


async def run_counter(msg: Message, ctx: Context, name: str) -> None:
    await ai_reply(
        ctx, msg.chat.id, msg.from_user.id,
        COUNTER_PROMPT.format(name=name), history_text=f"Counter qo'llanmasi: {name}",
    )


@router.message(Command("hero"))
async def cmd_hero(msg: Message, ctx: Context, command: CommandObject) -> None:
    name = clean_name(command.args)
    if name:
        await run_hero(msg, ctx, name)
    else:
        await ask_hero(msg, ctx)


@router.message(F.text == BTN_HERO)
async def ask_hero(msg: Message, ctx: Context) -> None:
    ctx.modes[msg.from_user.id] = "hero"
    await msg.answer("🦸‍♂️ Qaysi geroy kerak? Nomini yoz (masalan: <i>Hayabusa</i>, <i>Lancelot</i>, <i>Kagura</i>).",
                     parse_mode=ParseMode.HTML)


@router.message(Command("counter"))
async def cmd_counter(msg: Message, ctx: Context, command: CommandObject) -> None:
    name = clean_name(command.args)
    if name:
        await run_counter(msg, ctx, name)
    else:
        await ask_counter(msg, ctx)


@router.message(F.text == BTN_COUNTER)
async def ask_counter(msg: Message, ctx: Context) -> None:
    ctx.modes[msg.from_user.id] = "counter"
    await msg.answer("⚔️ Dushman qaysi geroyni olgan? Nomini yoz, kimga qarshi nima olishni aytaman.")


@router.message(Command("meta"))
@router.message(F.text == BTN_META)
async def cmd_meta(msg: Message, ctx: Context) -> None:
    ctx.modes.pop(msg.from_user.id, None)
    await msg.answer("🔥 Qaysi lane bo'yicha meta kerak?", reply_markup=meta_kb())


@router.callback_query(F.data.startswith("meta:"))
async def cb_meta(cb: CallbackQuery, ctx: Context) -> None:
    key = cb.data.split(":", 1)[1]
    await cb.answer()
    if key not in LANES or not cb.message:
        return
    lane = "" if key == "all" else f" ({LANES[key]} uchun)"
    footer = None if ctx.ai.web_search_enabled else "ℹ️ Meta tez o'zgaradi — patch notes bilan solishtirib ko'r."
    await ai_reply(
        ctx, cb.message.chat.id, cb.from_user.id,
        META_PROMPT.format(lane=lane), search=True, history_text=f"Meta so'rovi{lane}", footer=footer,
    )


# ============================================================ pro maslahatlar
@router.message(Command("tips"))
@router.message(F.text == BTN_TIPS)
async def cmd_tips(msg: Message, ctx: Context) -> None:
    ctx.modes.pop(msg.from_user.id, None)
    await msg.answer("💡 Qaysi mavzuda maslahat kerak?", reply_markup=tips_kb())


@router.callback_query(F.data.startswith("tip:"))
async def cb_tip(cb: CallbackQuery, ctx: Context) -> None:
    key = cb.data.split(":", 1)[1]
    await cb.answer()
    if not cb.message:
        return
    chat_id, uid = cb.message.chat.id, cb.from_user.id
    if key == "menu":
        await ctx.bot.send_message(chat_id, "💡 Qaysi mavzuda maslahat kerak?", reply_markup=tips_kb())
        return
    if key not in TIP_CATEGORIES:
        return
    problem = await check_quota(ctx, uid)
    if problem:
        await ctx.bot.send_message(chat_id, problem, parse_mode=None)
        return
    async with ChatActionSender.typing(bot=ctx.bot, chat_id=chat_id):
        try:
            reply = await ctx.ai.one_shot(
                "Sen MLBB bo'yicha o'zbek murabbiysan. Gamer tilida, qisqa va aniq yoz. Jadval ishlatma.",
                TIP_PROMPT.format(category=TIP_CATEGORIES[key], audience=random.choice(TIP_AUDIENCES)),
                uid=uid,
                max_tokens=700,
            )
        except AIError as err:
            if err.alert:
                await ctx.alert(*err.alert)
            await ctx.bot.send_message(chat_id, err.user_msg, parse_mode=None)
            return
    await ctx.db.inc_usage(uid)
    await send_long(ctx, chat_id, reply, markup=tip_again_kb(key))


# ============================================================ vaziyatli o'yin (quiz)
def parse_quiz(raw: str) -> Quiz | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    situation = str(data.get("situation", "")).strip()
    explanation = str(data.get("explanation", "")).strip()
    options, correct = data.get("options"), data.get("correct")
    if not situation or not explanation:
        return None
    if not isinstance(options, list) or len(options) != 4:
        return None
    if not all(isinstance(o, str) and o.strip() for o in options):
        return None
    if isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct <= 3:
        return None
    order = list(range(4))
    random.shuffle(order)  # LLM to'g'ri javobni ko'pincha bir joyga qo'yadi — aralashtiramiz
    return Quiz(
        situation=situation,
        options=[options[i].strip() for i in order],
        correct=order.index(correct),
        explanation=explanation,
    )


def render_quiz(quiz: Quiz, chosen: int | None = None) -> str:
    lines = ["🎮 <b>Vaziyatli o'yin</b>", "", html.escape(quiz.situation), ""]
    for i, opt in enumerate(quiz.options):
        mark = ""
        if chosen is not None:
            if i == quiz.correct:
                mark = " ✅"
            elif i == chosen:
                mark = " ❌"
        lines.append(f"<b>{'ABCD'[i]})</b> {html.escape(opt)}{mark}")
    if chosen is None:
        lines += ["", "Tanla 👇"]
    else:
        verdict = "✅ <b>To'g'ri!</b>" if chosen == quiz.correct else "❌ <b>Xato!</b>"
        lines += ["", verdict, html.escape(quiz.explanation)]
    return "\n".join(lines)


async def send_quiz(ctx: Context, chat_id: int, uid: int) -> None:
    problem = await check_quota(ctx, uid)
    if problem:
        await ctx.bot.send_message(chat_id, problem, parse_mode=None)
        return
    quiz: Quiz | None = None
    async with ChatActionSender.typing(bot=ctx.bot, chat_id=chat_id):
        try:
            for _ in range(2):
                raw = await ctx.ai.one_shot(
                    QUIZ_SYSTEM,
                    QUIZ_PROMPT.format(topic=random.choice(QUIZ_TOPICS), level=random.choice(QUIZ_LEVELS)),
                    uid=uid,
                    max_tokens=1000,
                )
                quiz = parse_quiz(raw)
                if quiz:
                    break
        except AIError as err:
            if err.alert:
                await ctx.alert(*err.alert)
            await ctx.bot.send_message(chat_id, err.user_msg, parse_mode=None)
            return
    if not quiz:
        await ctx.bot.send_message(chat_id, "🤔 Savol tayyorlay olmadim, yana bir bor bos.", parse_mode=None)
        return
    await ctx.db.inc_usage(uid)
    sent = await ctx.bot.send_message(chat_id, render_quiz(quiz), parse_mode=ParseMode.HTML, reply_markup=quiz_kb())
    quiz.message_id = sent.message_id
    ctx.remember_quiz(uid, quiz)


@router.message(Command("quiz"))
@router.message(F.text == BTN_QUIZ)
async def cmd_quiz(msg: Message, ctx: Context) -> None:
    ctx.modes.pop(msg.from_user.id, None)
    await send_quiz(ctx, msg.chat.id, msg.from_user.id)


@router.callback_query(F.data.regexp(r"^qz:[0-3]$"))
async def cb_quiz_answer(cb: CallbackQuery, ctx: Context) -> None:
    uid = cb.from_user.id
    quiz = ctx.quizzes.get(uid)
    if not cb.message or not quiz or quiz.answered or quiz.message_id != cb.message.message_id:
        await cb.answer("Bu savol eskirgan. Yangisini ol! 🔄", show_alert=False)
        return
    chosen = int(cb.data.split(":")[1])
    quiz.answered = True
    correct = chosen == quiz.correct
    await ctx.db.add_quiz_result(uid, correct)
    await cb.answer("✅ To'g'ri!" if correct else "❌ Xato!")
    try:
        await ctx.bot.edit_message_text(
            render_quiz(quiz, chosen),
            chat_id=cb.message.chat.id,
            message_id=cb.message.message_id,
            parse_mode=ParseMode.HTML,
            reply_markup=quiz_next_kb(),
        )
    except TelegramBadRequest as exc:
        log.warning("Quiz xabarini tahrirlab bo'lmadi: %s", exc)


@router.callback_query(F.data == "qz:next")
async def cb_quiz_next(cb: CallbackQuery, ctx: Context) -> None:
    await cb.answer()
    if not cb.message:
        return
    try:  # eski savoldagi tugmani olib tashlaymiz (qayta bosilmasin)
        await ctx.bot.edit_message_reply_markup(
            chat_id=cb.message.chat.id, message_id=cb.message.message_id, reply_markup=None
        )
    except TelegramBadRequest:
        pass
    await send_quiz(ctx, cb.message.chat.id, cb.from_user.id)


# ============================================================ admin
@router.message(Command("stats"), IsAdmin())
async def cmd_stats(msg: Message, ctx: Context) -> None:
    s = await ctx.db.stats()
    pct = f"{s['quiz_right'] / s['quiz_total'] * 100:.0f}%" if s["quiz_total"] else "—"
    await msg.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {s['users']} (bloklagan: {s['blocked']})\n"
        f"🟢 Bugun faol: {s['active_today']}\n"
        f"💬 Bugungi so'rovlar: {s['requests_today']}\n"
        f"📈 Jami so'rovlar: {s['requests_total']}\n"
        f"🎮 Quiz: {s['quiz_right']}/{s['quiz_total']} ({pct})\n\n"
        f"🤖 Model: <code>{html.escape(ctx.cfg.model)}</code>\n"
        f"🌐 Web search: {'yoqilgan' if ctx.ai.web_search_enabled else 'o`chiq'}",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("broadcast"), IsAdmin())
async def cmd_broadcast(msg: Message, ctx: Context, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await msg.answer("Foydalanish: /broadcast <matn>")
        return
    targets = await ctx.db.broadcast_targets()
    await msg.answer(f"📣 {len(targets)} ta foydalanuvchiga yuborilmoqda...")
    ok = fail = 0
    for uid in targets:
        try:
            await ctx.bot.send_message(uid, text, parse_mode=None)
            ok += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
            try:
                await ctx.bot.send_message(uid, text, parse_mode=None)
                ok += 1
            except TelegramAPIError:
                fail += 1
        except TelegramForbiddenError:
            await ctx.db.mark_blocked(uid)
            fail += 1
        except TelegramAPIError:
            fail += 1
        await asyncio.sleep(0.05)  # Telegram limiti: ~30 xabar/soniya
    await msg.answer(f"✅ Yuborildi: {ok}\n❌ Yetmadi: {fail}")


# ============================================================ rasm tahlili
@router.message(F.photo, F.chat.type == ChatType.PRIVATE)
async def on_photo(msg: Message, ctx: Context) -> None:
    uid = msg.from_user.id
    ctx.modes.pop(uid, None)
    photo = msg.photo[-1]
    if photo.file_size and photo.file_size > MAX_PHOTO_BYTES:
        await msg.answer("🖼 Rasm juda katta (5 MB dan oshmasin). Kichikroq skrinshot yubor.")
        return
    problem = await check_quota(ctx, uid)
    if problem:
        await msg.answer(problem)
        return
    buf = await ctx.bot.download(photo)
    data = buf.read() if buf else b""
    if not data:
        await msg.answer("😕 Rasmni yuklab ololmadim, qayta yubor.")
        return
    caption = clean_name(msg.caption)[:500] if msg.caption else ""
    prompt = f"{PHOTO_DEFAULT}\n\nFoydalanuvchi izohi: {caption}" if caption else PHOTO_DEFAULT
    await ai_reply(ctx, msg.chat.id, uid, prompt, image=data, history_text=f"[Skrinshot yuborildi] {caption}".strip())


# ============================================================ oddiy matn
@router.message(F.text.startswith("/"))
async def unknown_command(msg: Message) -> None:
    await msg.answer("🤷 Bunday buyruq yo'q. /help ni bos.")


@router.message(F.text, F.chat.type == ChatType.PRIVATE)
async def on_text(msg: Message, ctx: Context) -> None:
    uid = msg.from_user.id
    text = (msg.text or "").strip()
    if not text:
        return
    if len(text) > MAX_INPUT:
        text = text[:MAX_INPUT]
        await msg.answer(f"✂️ Xabar uzun ekan, birinchi {MAX_INPUT} belgisini oldim.")
    mode = ctx.modes.pop(uid, None)
    if mode == "hero":
        await run_hero(msg, ctx, clean_name(text))
    elif mode == "counter":
        await run_counter(msg, ctx, clean_name(text))
    else:
        await ai_reply(ctx, msg.chat.id, uid, text)


@router.message(F.chat.type == ChatType.PRIVATE)
async def on_other(msg: Message) -> None:
    await msg.answer("📎 Hozircha faqat matn va skrinshot (rasm) qabul qilaman 🙂")


# ============================================================ global xato ushlagich
@router.errors()
async def on_error(event: ErrorEvent, ctx: Context) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramForbiddenError):
        log.info("Foydalanuvchi botni bloklagan: %s", exc)
        return True
    log.error("Handlerda xato", exc_info=exc)
    await ctx.alert(f"err:{type(exc).__name__}", f"Botda xato: {type(exc).__name__}: {str(exc)[:300]}", every=300)
    msg = event.update.message
    cb = event.update.callback_query
    chat_id = msg.chat.id if msg else (cb.message.chat.id if cb and cb.message else None)
    if chat_id:
        try:
            await ctx.bot.send_message(chat_id, "⚠️ Nimadir xato ketdi. Birozdan keyin qayta urinib ko'r.", parse_mode=None)
        except TelegramAPIError:
            pass
    return True
