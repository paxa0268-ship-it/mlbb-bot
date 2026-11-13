import pytest

from config import ConfigError, load_config
from db import Database
from formatting import md_to_html, plain, split_text
from handlers import parse_quiz, rank_title


# ---------- formatting
def test_bold_italic_bullets_headers():
    out = md_to_html("# Sarlavha\n**qalin** va *kursiv*\n- bir\n* ikki")
    assert "<b>Sarlavha</b>" in out
    assert "<b>qalin</b>" in out and "<i>kursiv</i>" in out
    assert "• bir" in out and "• ikki" in out


def test_html_is_escaped():
    out = md_to_html("a < b & c > d <script>")
    assert "&lt;" in out and "&amp;" in out and "<script>" not in out


def test_code_untouched():
    out = md_to_html("`**x**` va\n```py\na < b\n```")
    assert "<code>**x**</code>" in out
    assert "<pre>a &lt; b</pre>" in out


def test_plain_strips_markers():
    assert plain("**a** `b` ```x```") == "a b x"


def test_split_text_limits_and_content():
    text = "\n\n".join(f"Abzats {i} " + "so'z " * 120 for i in range(30))
    parts = split_text(text, 3500)
    assert len(parts) > 1 and all(len(p) <= 3500 for p in parts)
    assert "Abzats 0" in parts[0] and "Abzats 29" in parts[-1]


def test_split_huge_single_line():
    parts = split_text("x" * 10000, 3500)
    assert all(len(p) <= 3500 for p in parts) and sum(len(p) for p in parts) == 10000


def test_split_empty():
    assert split_text("   ") == []


# ---------- config
def test_config_errors(monkeypatch):
    for k in ["TELEGRAM_TOKEN", "BOT_TOKEN", "CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_ID"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("config.load_dotenv", lambda: None, raising=False)
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN"):
        load_config()
    monkeypatch.setenv("TELEGRAM_TOKEN", "bad")
    with pytest.raises(ConfigError, match="formati"):
        load_config()
    monkeypatch.setenv("TELEGRAM_TOKEN", "123456789:" + "A" * 35)
    with pytest.raises(ConfigError, match="CLAUDE_API_KEY"):
        load_config()
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-x")
    monkeypatch.setenv("ADMIN_ID", "abc")
    with pytest.raises(ConfigError, match="ADMIN_ID"):
        load_config()
    monkeypatch.setenv("ADMIN_ID", "42")
    cfg = load_config()
    assert cfg.admin_id == 42 and cfg.token_bot_id == 123456789 and cfg.model


# ---------- quiz parsing
GOOD = '{"situation":"S","options":["a","b","c","d"],"correct":1,"explanation":"E"}'


def test_parse_quiz_keeps_correct_after_shuffle():
    for _ in range(30):
        q = parse_quiz("```json\n" + GOOD + "\n```")
        assert q and q.options[q.correct] == "b"


@pytest.mark.parametrize(
    "raw",
    [
        "yo'q",
        "{broken",
        '{"situation":"S","options":["a","b","c"],"correct":1,"explanation":"E"}',
        '{"situation":"S","options":["a","b","c","d"],"correct":4,"explanation":"E"}',
        '{"situation":"S","options":["a","b","c","d"],"correct":true,"explanation":"E"}',
        '{"situation":"","options":["a","b","c","d"],"correct":1,"explanation":"E"}',
        "[1,2]",
    ],
)
def test_parse_quiz_rejects_bad(raw):
    assert parse_quiz(raw) is None


def test_rank():
    assert "Warrior" in rank_title(2, 2)
    assert "Mythical" in rank_title(10, 9)


# ---------- db
async def test_db(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    assert await db.upsert_user(1, "a", "A") is True
    assert await db.upsert_user(1, "a", "A") is False
    assert await db.inc_usage(1) == 1 and await db.inc_usage(1) == 2
    assert await db.get_usage(1) == 2 and await db.get_usage(99) == 0
    await db.add_quiz_result(1, True)
    await db.add_quiz_result(1, False)
    u = await db.get_user(1)
    assert (u["quiz_total"], u["quiz_right"], u["requests"]) == (2, 1, 2)
    await db.mark_blocked(1)
    assert await db.broadcast_targets() == []
    assert (await db.stats())["blocked"] == 1
    await db.upsert_user(1, "a", "A")  # qayta yozsa blok bekor bo'ladi
    assert await db.broadcast_targets() == [1]
