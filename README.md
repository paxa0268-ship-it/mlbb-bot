# 🎮 MLBB Murabbiy — Telegram bot

Mobile Legends: Bang Bang bo'yicha o'zbek tilidagi AI murabbiy (aiogram 3 + Claude).

## Imkoniyatlar
- 🦸‍♂️ **Geroy qo'llanmasi** — rol, combo, build, emblem/spell, counter, pro tip (`/hero Kagura`)
- ⚔️ **Counter-pick** — dushman geroyiga qarshi nima olish (`/counter Fanny`)
- 🔥 **Meta** — lane bo'yicha tugmalar bilan (`/meta`); `ENABLE_WEB_SEARCH=true` bo'lsa internetdan yangi ma'lumot oladi
- 🎮 **Vaziyatli o'yin testi** — Claude real vaziyat tuzadi, A/B/C/D tugmalar, tushuntirish, ball va daraja (`/quiz`)
- 💡 **Pro maslahatlar** — 5 mavzu, "yana" tugmasi bilan (`/tips`)
- 📸 **Skrinshot tahlili** — draft, build yoki o'yin natijasi rasmini yuboring
- 👤 **Profil** — daraja, test natijasi, kunlik limit
- 🧠 Suhbat xotirasi (oxirgi xabarlar), `/reset` bilan tozalanadi
- 🛡 Himoya: spamga qarshi kutish vaqti, kunlik limit, xatolarda tushunarli javob, uzun javobni bo'lib yuborish, Markdown xato bersa oddiy matnga o'tish
- 🔐 Admin: `/stats`, `/broadcast matn`, muhim xatolar (API kalit, balans, model) haqida avtomatik ogohlantirish

## Ishga tushirish (kompyuterda)
```bash
pip install -r requirements.txt
# .env faylni oching va CLAUDE_API_KEY ni yozing
python bot.py
```
Python 3.10+ kerak.

## ⚠️ Birinchi sozlash
1. **CLAUDE_API_KEY** — https://console.anthropic.com/ dan oling va `.env` ga yozing.
2. **ADMIN_ID** — tokenning boshidagi raqam (`8508474204`) botning o'z ID si, shaxsiy chat ID emas.
   Botni ishga tushirib, unga `/id` deb yozing, chiqqan raqamni `ADMIN_ID` ga qo'ying va qayta ishga tushiring.
3. **Xavfsizlik** — token chatda ochiq yozilgan bo'lsa, @BotFather → `/revoke` bilan yangisini oling va `.env` dagi `TELEGRAM_TOKEN` ni almashtiring. `.env` ni hech qachon GitHub'ga yuklamang (`.gitignore` da bor).

## Hostingga joylash
- **Railway / Render / Heroku**: kodni yuklang, `Procfile` (`worker: python bot.py`) ishlatiladi. `.env` dagi o'zgaruvchilarni panelning *Variables* bo'limiga kiriting.
- **Docker**: `docker build -t mlbb-bot . && docker run -d --restart=always --env-file .env mlbb-bot`
- **VPS**: `systemd` yoki `pm2`/`screen` bilan `python bot.py`.
- Bitta token bilan faqat **bitta** nusxa ishlashi kerak, aks holda `Conflict: terminated by other getUpdates` xatosi chiqadi.
- Statistika `bot.db` (SQLite) da saqlanadi. Hosting fayllarni o'chirib yuborsa (Heroku), `DB_PATH` ni doimiy diskka qo'ying.

## Sozlamalar (.env)
| O'zgaruvchi | Izoh | Standart |
|---|---|---|
| `TELEGRAM_TOKEN` | @BotFather tokeni | — |
| `CLAUDE_API_KEY` | Anthropic API kaliti | — |
| `ADMIN_ID` | Sizning Telegram ID ingiz | bo'sh |
| `MODEL` | Claude modeli | `claude-sonnet-5-5` |
| `MAX_TOKENS` | Javob uzunligi chegarasi | 1200 |
| `HISTORY_LIMIT` | Xotirada saqlanadigan xabarlar soni | 12 |
| `COOLDOWN_SEC` | So'rovlar orasidagi minimal pauza | 2 |
| `DAILY_LIMIT` | Foydalanuvchiga kunlik so'rovlar | 60 |
| `ENABLE_WEB_SEARCH` | Meta uchun internet qidiruvi | false |
| `NOTIFY_NEW_USERS` | Yangi foydalanuvchi haqida adminga xabar | true |

## Testlar
```bash
pip install -r requirements-dev.txt
pytest
```
47 ta test: formatlash, sozlamalar, baza, suhbat, xatolar, quiz, limitlar, rasm, admin.

## Fayllar
`bot.py` (kirish) · `handlers.py` (barcha buyruq/tugmalar) · `ai.py` (Claude) · `prompts.py` · `formatting.py` · `db.py` · `config.py` · `context.py` · `keyboards.py`
