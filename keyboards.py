from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from prompts import LANES, TIP_CATEGORIES

BTN_HERO = "🦸‍♂️ Geroy o'rganish"
BTN_META = "🔥 Hozirgi Meta"
BTN_QUIZ = "🎮 Vaziyatli O'yin (Test)"
BTN_TIPS = "💡 Pro Maslahatlar"
BTN_COUNTER = "⚔️ Counter-Pick (Kimga kim?)"
BTN_PROFILE = "👤 Profilim"

MENU_BUTTONS = {BTN_HERO, BTN_META, BTN_QUIZ, BTN_TIPS, BTN_COUNTER, BTN_PROFILE}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HERO), KeyboardButton(text=BTN_META)],
            [KeyboardButton(text=BTN_QUIZ), KeyboardButton(text=BTN_TIPS)],
            [KeyboardButton(text=BTN_COUNTER), KeyboardButton(text=BTN_PROFILE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Geroy nomini yoz yoki savol ber...",
    )


def quiz_kb() -> InlineKeyboardMarkup:
    letters = "ABCD"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=letters[i], callback_data=f"qz:{i}") for i in range(4)]]
    )


def quiz_next_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Yana savol", callback_data="qz:next")]])


def tips_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"tip:{key}")] for key, title in TIP_CATEGORIES.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tip_again_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Yana shu mavzu", callback_data=f"tip:{key}"),
                InlineKeyboardButton(text="📚 Boshqa mavzu", callback_data="tip:menu"),
            ]
        ]
    )


def meta_kb() -> InlineKeyboardMarkup:
    items = list(LANES.items())
    rows = []
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text=t, callback_data=f"meta:{k}") for k, t in items[i : i + 2]])
    return InlineKeyboardMarkup(inline_keyboard=rows)
