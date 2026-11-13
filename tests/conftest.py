import itertools
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, File, Message, PhotoSize, Update, User

from config import Config
from context import Context
from db import Database
from handlers import UserTracker, router

ADMIN = 777
USER = 555
_ids = itertools.count(1000)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.reject_html = False

    async def close(self):
        pass

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b"\xff\xd8fakejpeg"

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "SendMessage" and self.reject_html and method.parse_mode == "HTML":
            raise TelegramBadRequest(method=method, message="Bad Request: can't parse entities")
        self.calls.append(method)
        if name == "GetMe":
            return User(id=999, is_bot=True, first_name="Bot", username="mlbb_test_bot")
        if name == "SendMessage":
            return Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=method.chat_id, type="private"), text=method.text)
        if name == "GetFile":
            return File(file_id="f", file_unique_id="u", file_path="photos/x.jpg")
        return True

    # yordamchilar
    def sent(self, to=None):
        return [c for c in self.calls if isinstance(c, SendMessage) and (to is None or c.chat_id == to)]

    def texts(self, to=None):
        return [c.text for c in self.sent(to)]


def make_cfg(tmp_path, **over):
    base = dict(
        telegram_token="999:" + "A" * 35,
        claude_api_key="sk-ant-test",
        admin_id=ADMIN,
        model="claude-sonnet-5-5",
        max_tokens=500,
        history_limit=6,
        cooldown_sec=0.0,
        daily_limit=50,
        enable_web_search=False,
        notify_new_users=True,
        db_path=str(tmp_path / "t.db"),
        log_level="INFO",
    )
    base.update(over)
    return Config(**base)


def text_reply(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def env(tmp_path):
    def build(**over):
        cfg = make_cfg(tmp_path, **over)
        session = FakeSession()
        bot = Bot(token=cfg.telegram_token, session=session)
        db = Database(cfg.db_path)
        ctx = Context(cfg=cfg, bot=bot, db=db, admin_id=cfg.admin_id)
        ctx.ai.client.messages.create = AsyncMock(return_value=text_reply("Javob 👍"))
        dp = Dispatcher(ctx=ctx)
        dp.update.outer_middleware(UserTracker())
        router._parent_router = None  # test: har safar yangi Dispatcher
        dp.include_router(router)
        return SimpleNamespace(cfg=cfg, session=session, bot=bot, db=db, ctx=ctx, dp=dp, ai=ctx.ai.client.messages.create)

    return build


def _user(uid):
    return User(id=uid, is_bot=False, first_name="Ali", username="ali")


def _msg(uid, **kw):
    return Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=_user(uid), **kw)


async def say(e, text, uid=USER):
    await e.dp.feed_update(e.bot, Update(update_id=next(_ids), message=_msg(uid, text=text)))


async def send_photo(e, caption=None, uid=USER, size=1000):
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=10, height=10, file_size=size)]
    await e.dp.feed_update(e.bot, Update(update_id=next(_ids), message=_msg(uid, photo=photo, caption=caption)))


async def send_sticker(e, uid=USER):
    from aiogram.types import Sticker

    st = Sticker(file_id="s", file_unique_id="su", type="regular", width=1, height=1, is_animated=False, is_video=False)
    await e.dp.feed_update(e.bot, Update(update_id=next(_ids), message=_msg(uid, sticker=st)))


async def press(e, data, message_id, uid=USER):
    cb = CallbackQuery(
        id=str(next(_ids)), from_user=_user(uid), chat_instance="ci", data=data,
        message=Message(message_id=message_id, date=datetime.now(), chat=Chat(id=uid, type="private"), text="x"),
    )
    await e.dp.feed_update(e.bot, Update(update_id=next(_ids), callback_query=cb))
