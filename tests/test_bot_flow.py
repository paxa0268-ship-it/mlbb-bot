import httpx
import anthropic

from keyboards import BTN_COUNTER, BTN_HERO, BTN_PROFILE, BTN_QUIZ
from tests.conftest import ADMIN, USER, press, say, send_photo, send_sticker, text_reply

QUIZ_JSON = '{"situation":"Lord 20 soniyada chiqadi","options":["Bosish","Qochish","Farm","Gank"],"correct":0,"explanation":"Sababi shu."}'


def api_error(cls, status):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("xato", response=httpx.Response(status, request=req), body=None)


# ---------- start va oddiy suhbat
async def test_start_registers_user_menu_and_notifies_admin(env):
    e = env()
    await say(e, "/start")
    sent = e.session.sent(USER)
    assert "Salom" in sent[0].text and sent[0].reply_markup is not None
    assert (await e.db.get_user(USER))["first_name"] == "Ali"
    assert any("Yangi foydalanuvchi" in t for t in e.session.texts(ADMIN))


async def test_chat_keeps_history_and_formats(env):
    e = env()
    e.ai.return_value = text_reply("**Hayabusa** — assassin\n- tez\n- xavfli")
    await say(e, "Hayabusa kim?")
    msg = e.session.sent(USER)[-1]
    assert "<b>Hayabusa</b>" in msg.text and msg.parse_mode == "HTML"
    await say(e, "Buildi qanaqa?")
    msgs = e.ai.call_args.kwargs["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "Hayabusa kim?"


async def test_history_trimmed_and_starts_with_user(env):
    e = env()  # history_limit=6
    for i in range(8):
        await say(e, f"savol {i}")
    h = e.ctx.ai.histories[USER]
    assert len(h) <= 6 and h[0]["role"] == "user"
    assert [m["role"] for m in h] == ["user", "assistant"] * (len(h) // 2)


async def test_reset_clears_history(env):
    e = env()
    await say(e, "salom")
    await say(e, "/reset")
    assert USER not in e.ctx.ai.histories


# ---------- xatolar
async def test_api_error_keeps_history_clean(env):
    e = env()
    await say(e, "bir")
    e.ai.side_effect = api_error(anthropic.RateLimitError, 429)
    await say(e, "ikki")
    assert "band" in e.session.sent(USER)[-1].text
    assert len(e.ctx.ai.histories[USER]) == 2  # muvaffaqiyatsiz savol qo'shilmadi
    e.ai.side_effect = None
    e.ai.return_value = text_reply("ok")
    await say(e, "uch")
    assert [m["role"] for m in e.ai.call_args.kwargs["messages"]] == ["user", "assistant", "user"]


async def test_auth_error_alerts_admin_once(env):
    e = env()
    e.ai.side_effect = api_error(anthropic.AuthenticationError, 401)
    await say(e, "a")
    await say(e, "b")
    alerts = [t for t in e.session.texts(ADMIN) if "CLAUDE_API_KEY" in t]
    assert len(alerts) == 1  # throttle
    assert "Admin xabardor" in e.session.sent(USER)[-1].text


async def test_connection_and_empty_reply(env):
    e = env()
    e.ai.side_effect = anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))
    await say(e, "a")
    assert "Ping" in e.session.sent(USER)[-1].text
    e.ai.side_effect = None
    e.ai.return_value = text_reply("   ")
    await say(e, "b")
    assert "bo'sh" in e.session.sent(USER)[-1].text


async def test_html_rejected_falls_back_to_plain(env):
    e = env()
    e.session.reject_html = True
    e.ai.return_value = text_reply("**qalin** matn")
    await say(e, "x")
    last = e.session.sent(USER)[-1]
    assert last.text == "qalin matn" and last.parse_mode is None


async def test_long_reply_is_split(env):
    e = env()
    e.ai.return_value = text_reply("\n\n".join("Abzats " + "so'z " * 150 for _ in range(15)))
    await say(e, "uzun")
    msgs = e.session.sent(USER)
    assert len(msgs) >= 2 and all(len(m.text) <= 4096 for m in msgs)


async def test_unhandled_exception_reaches_error_handler(env):
    e = env()

    async def boom(uid):
        raise RuntimeError("baza yiqildi")

    e.db.get_usage = boom
    await say(e, "salom")
    assert "xato ketdi" in e.session.sent(USER)[-1].text
    assert any("RuntimeError" in t for t in e.session.texts(ADMIN))


# ---------- limitlar
async def test_daily_limit(env):
    e = env(daily_limit=2)
    await say(e, "1")
    await say(e, "2")
    await say(e, "3")
    assert "limit" in e.session.sent(USER)[-1].text
    assert e.ai.await_count == 2


async def test_admin_has_no_daily_limit(env):
    e = env(daily_limit=1)
    await say(e, "1", uid=ADMIN)
    await say(e, "2", uid=ADMIN)
    assert e.ai.await_count == 2


async def test_cooldown(env):
    e = env(cooldown_sec=60.0)
    await say(e, "1")
    await say(e, "2")
    assert "Sekinroq" in e.session.sent(USER)[-1].text and e.ai.await_count == 1


# ---------- geroy / counter / meta / tips
async def test_hero_button_flow(env):
    e = env()
    await say(e, BTN_HERO)
    assert "Qaysi geroy" in e.session.sent(USER)[-1].text
    await say(e, "Lancelot")
    prompt = e.ai.call_args.kwargs["messages"][-1]["content"]
    assert "Lancelot" in prompt and "Combo" in prompt
    await say(e, "rahmat")  # rejim tugagan: oddiy suhbat
    assert e.ai.call_args.kwargs["messages"][-1]["content"] == "rahmat"


async def test_hero_and_counter_commands(env):
    e = env()
    await say(e, "/hero Kagura")
    assert "Kagura" in e.ai.call_args.kwargs["messages"][-1]["content"]
    await say(e, "/counter  Fanny ")
    assert "Fanny" in e.ai.call_args.kwargs["messages"][-1]["content"]
    await say(e, BTN_COUNTER)
    assert "Dushman" in e.session.sent(USER)[-1].text


async def test_meta_callback_with_and_without_search(env):
    e = env()
    await say(e, "/meta")
    kb_msg = e.session.sent(USER)[-1]
    assert kb_msg.reply_markup is not None
    await press(e, "meta:gold", 1)
    assert "Gold lane" in e.ai.call_args.kwargs["messages"][-1]["content"]
    assert "tools" not in e.ai.call_args.kwargs
    assert "patch notes" in e.session.sent(USER)[-1].text  # qidiruv yo'q — ogohlantirish

    e2 = env(enable_web_search=True)
    await press(e2, "meta:all", 1)
    assert e2.ai.call_args.kwargs["tools"][0]["name"] == "web_search"


async def test_web_search_falls_back_when_unsupported(env):
    e = env(enable_web_search=True)
    calls = []

    async def fake(**kw):
        calls.append(kw)
        if "tools" in kw:
            raise api_error(anthropic.BadRequestError, 400)
        return text_reply("qidiruvsiz javob")

    e.ctx.ai.client.messages.create = fake
    await press(e, "meta:all", 1)
    assert len(calls) == 2 and "tools" not in calls[1]
    assert e.ctx.ai.web_search_enabled is False
    assert "qidiruvsiz" in e.session.sent(USER)[-1].text


async def test_tips(env):
    e = env()
    await say(e, "/tips")
    await press(e, "tip:farm", 1)
    assert "Farm" in e.ai.call_args.kwargs["messages"][-1]["content"]
    assert e.session.sent(USER)[-1].reply_markup is not None
    n = len(e.session.sent(USER))
    await press(e, "tip:menu", 1)
    assert len(e.session.sent(USER)) == n + 1
    await press(e, "tip:hack", 1)  # noma'lum kalit e'tiborsiz
    assert len(e.session.sent(USER)) == n + 1


# ---------- quiz
async def test_quiz_full_flow(env):
    e = env()
    e.ai.return_value = text_reply(QUIZ_JSON)
    await say(e, BTN_QUIZ)
    q = e.session.sent(USER)[-1]
    assert "Lord" in q.text and q.reply_markup is not None
    quiz = e.ctx.quizzes[USER]
    assert quiz.options[quiz.correct] == "Bosish"

    await press(e, f"qz:{quiz.correct}", quiz.message_id)
    edit = [c for c in e.session.calls if type(c).__name__ == "EditMessageText"][-1]
    assert "To'g'ri" in edit.text and "Sababi shu" in edit.text
    u = await e.db.get_user(USER)
    assert (u["quiz_total"], u["quiz_right"]) == (1, 1)

    await press(e, f"qz:{quiz.correct}", quiz.message_id)  # ikkinchi bosish hisobga olinmaydi
    assert (await e.db.get_user(USER))["quiz_total"] == 1

    await press(e, "qz:next", quiz.message_id)
    assert e.ctx.quizzes[USER] is not quiz and not e.ctx.quizzes[USER].answered


async def test_quiz_wrong_answer(env):
    e = env()
    e.ai.return_value = text_reply(QUIZ_JSON)
    await say(e, "/quiz")
    quiz = e.ctx.quizzes[USER]
    wrong = (quiz.correct + 1) % 4
    await press(e, f"qz:{wrong}", quiz.message_id)
    edit = [c for c in e.session.calls if type(c).__name__ == "EditMessageText"][-1]
    assert "Xato" in edit.text and "❌" in edit.text and "✅" in edit.text
    assert (await e.db.get_user(USER))["quiz_right"] == 0


async def test_quiz_stale_and_foreign_callbacks_ignored(env):
    e = env()
    await press(e, "qz:1", 5)  # savol yo'q
    assert (await e.db.get_user(USER)) is not None  # crash yo'q
    e.ai.return_value = text_reply(QUIZ_JSON)
    await say(e, "/quiz")
    quiz = e.ctx.quizzes[USER]
    await press(e, "qz:1", quiz.message_id + 99)  # boshqa xabar
    assert not quiz.answered


async def test_quiz_bad_json_retries_then_apologizes(env):
    e = env()
    e.ai.side_effect = [text_reply("bu json emas"), text_reply(QUIZ_JSON)]
    await say(e, "/quiz")
    assert USER in e.ctx.quizzes and e.ai.await_count == 2

    e2 = env()
    e2.ai.return_value = text_reply("json emas")
    await say(e2, "/quiz")
    assert "tayyorlay olmadim" in e2.session.sent(USER)[-1].text
    assert USER not in e2.ctx.quizzes


# ---------- profil, id, help
async def test_profile_id_help(env):
    e = env()
    await say(e, BTN_PROFILE)  # /start bosilmagan bo'lsa ham middleware yozadi
    assert "Profil" in e.session.sent(USER)[-1].text or "Ali" in e.session.sent(USER)[-1].text
    await say(e, "/id")
    assert str(USER) in e.session.sent(USER)[-1].text
    await say(e, "/help")
    assert "/broadcast" not in e.session.sent(USER)[-1].text
    await say(e, "/help", uid=ADMIN)
    assert "/broadcast" in e.session.sent(ADMIN)[-1].text


# ---------- rasm va boshqa kontent
async def test_photo_sent_to_claude_as_image(env):
    e = env()
    await send_photo(e, caption="draft shu")
    content = e.ai.call_args.kwargs["messages"][-1]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert "draft shu" in content[1]["text"]
    assert e.ctx.ai.histories[USER][0]["content"].startswith("[Skrinshot")  # tarixga base64 yozilmaydi


async def test_big_photo_rejected(env):
    e = env()
    await send_photo(e, size=9 * 1024 * 1024)
    assert "katta" in e.session.sent(USER)[-1].text and e.ai.await_count == 0


async def test_sticker_and_unknown_command_and_long_text(env):
    e = env()
    await send_sticker(e)
    assert "faqat matn" in e.session.sent(USER)[-1].text
    await say(e, "/nimadir")
    assert "buyruq yo'q" in e.session.sent(USER)[-1].text
    await say(e, "x" * 5000)
    assert len(e.ai.call_args.kwargs["messages"][-1]["content"]) == 2000


# ---------- admin
async def test_admin_stats_and_non_admin_blocked(env):
    e = env()
    await say(e, "salom")
    await say(e, "/stats")
    assert "buyruq yo'q" in e.session.sent(USER)[-1].text
    await say(e, "/stats", uid=ADMIN)
    assert "Statistika" in e.session.sent(ADMIN)[-1].text and "Foydalanuvchilar: 2" in e.session.sent(ADMIN)[-1].text


async def test_broadcast(env):
    e = env()
    await say(e, "salom")
    await say(e, "/broadcast Yangi patch keldi!", uid=ADMIN)
    assert "Yangi patch keldi!" in e.session.texts(USER)
    assert "Yuborildi: 2" in e.session.sent(ADMIN)[-1].text  # USER va ADMIN
    await say(e, "/broadcast", uid=ADMIN)
    assert "Foydalanish" in e.session.sent(ADMIN)[-1].text
    await say(e, "/broadcast hack")  # oddiy user ishlata olmaydi
    assert "hack" not in e.session.texts(ADMIN)


async def test_admin_id_equal_to_bot_id_disables_admin(env):
    e = env(admin_id=999)  # token boshidagi raqam bilan bir xil
    e.ctx.admin_id = None  # bot.py shunday qiladi
    await say(e, "/stats", uid=999)
    assert not any("Statistika" in t for t in e.session.texts())
    assert e.ctx.is_admin(999) is False
