"""Claude javobini (Markdown) Telegram HTML formatiga xavfsiz o'tkazish va uzun matnni bo'lish."""
from __future__ import annotations

import html
import re

TG_LIMIT = 4096
CHUNK = 3500  # HTML teglari qo'shilganda ham 4096 dan oshmasligi uchun zaxira bilan

_PH = "\ue000"


def md_to_html(text: str) -> str:
    stash: list[str] = []

    def keep(markup: str) -> str:
        stash.append(markup)
        return f"{_PH}{len(stash) - 1}{_PH}"

    # 1) kod bloklari va inline kod — tegilmasin
    text = re.sub(
        r"```(?:[A-Za-z0-9_+-]*\n)?(.*?)```",
        lambda m: keep(f"<pre>{html.escape(m.group(1).strip(chr(10)))}</pre>"),
        text,
        flags=re.S,
    )
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)

    # 2) qolgan hamma narsani escape
    text = html.escape(text, quote=False)

    # 3) sarlavhalar, ro'yxatlar, bold, italic
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^([ \t]*)[-*+•][ \t]+", r"\1• ", text, flags=re.M)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"^[ \t]*([-*_]){3,}[ \t]*$", "──────────", text, flags=re.M)

    # 4) stashni qaytarish
    return re.sub(f"{_PH}(\\d+){_PH}", lambda m: stash[int(m.group(1))], text)


def plain(text: str) -> str:
    """HTML ishlamay qolsa — markdown belgilarsiz oddiy matn."""
    text = re.sub(r"```[A-Za-z0-9_+-]*\n", "", text)
    return text.replace("```", "").replace("**", "").replace("__", "").replace("`", "")


def split_text(text: str, limit: int = CHUNK) -> list[str]:
    """Matnni abzats/qator chegarasida bo'ladi."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    parts: list[str] = []
    current = ""
    for block in re.split(r"(\n\n)", text):
        if len(current) + len(block) <= limit:
            current += block
            continue
        if current.strip():
            parts.append(current.strip())
        current = ""
        if len(block) <= limit:
            current = block
            continue
        # juda uzun abzats: qatorlar bo'yicha, keyin qattiq kesish
        for line in block.split("\n"):
            while len(line) > limit:
                cut = line.rfind(" ", 0, limit)
                cut = cut if cut > limit // 2 else limit
                parts.append(line[:cut].strip())
                line = line[cut:]
            if len(current) + len(line) + 1 > limit:
                if current.strip():
                    parts.append(current.strip())
                current = ""
            current += line + "\n"
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p]
