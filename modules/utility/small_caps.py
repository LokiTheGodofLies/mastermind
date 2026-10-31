"""Small Caps text engine for every user-facing string the bot sends.

Design
------
* No small-caps glyphs are typed anywhere in the source code. The glyph table below is
  built from Unicode code points, and all bot strings stay written in normal text.
  Conversion happens once, at the very last moment before a message goes to Telegram
  (see the hooks in `rich_ui.install_rich_ui_patches`).
* Only the 26 Latin letters are converted. Digits, punctuation and emoji are untouched.
* The converter is *markup aware*. It never touches:
    - HTML tags and attributes (`<b>`, `<a href="...">`, `<tg-button data="...">`)
    - HTML entities (`&amp;`, `&#39;`)
    - `<code>` / `<pre>` content (IDs, commands, errors, file names - things people copy)
    - URLs, `t.me/...` links, `tg://` links
    - `@usernames`, `/commands` and `#hashtags` (so they stay tappable and searchable)
* It is idempotent: converting already-converted text changes nothing.
* `from_small_caps()` reverses it, so text a user copies from the bot (for example a book
  title pasted into search) still matches the database.

Device support
--------------
The default glyph set is the one that renders on iOS and Android phones released after
2010 using the system font plus normal font fallback. Two letters have no widely
supported small-cap form, so the safe set keeps them readable:
    q -> U+01EB (lookalike), s and x -> plain lowercase letters.
Environment switches:
    SMALL_CAPS=0            turn the feature off completely (messages go out untouched)
    SMALL_CAPS_EXTENDED=1   also use U+A731 for "s" (needs a newer font, 2012+ phones)
"""
from __future__ import annotations

import os
import re
from typing import Any

# --------------------------------------------------------------------------------------
# Glyph table (code points only, so the source file stays plain ASCII)
# --------------------------------------------------------------------------------------
_CODEPOINTS: dict[str, int] = {
    "a": 0x1D00, "b": 0x0299, "c": 0x1D04, "d": 0x1D05, "e": 0x1D07,
    "f": 0xA730, "g": 0x0262, "h": 0x029C, "i": 0x026A, "j": 0x1D0A,
    "k": 0x1D0B, "l": 0x029F, "m": 0x1D0D, "n": 0x0274, "o": 0x1D0F,
    "p": 0x1D18, "q": 0x01EB, "r": 0x0280, "t": 0x1D1B, "u": 0x1D1C,
    "v": 0x1D20, "w": 0x1D21, "y": 0x028F, "z": 0x1D22,
}
# "s" and "x" are left as plain letters in the safe set.
_EXTENDED_S = 0xA731


def enabled() -> bool:
    return os.environ.get("SMALL_CAPS", "1").strip().lower() not in ("0", "false", "off", "no")


def _build_tables() -> tuple[dict[int, str], dict[int, str]]:
    cps = dict(_CODEPOINTS)
    if os.environ.get("SMALL_CAPS_EXTENDED", "0").strip().lower() in ("1", "true", "on", "yes"):
        cps["s"] = _EXTENDED_S
    fwd: dict[int, str] = {}
    for letter, cp in cps.items():
        fwd[ord(letter)] = chr(cp)
        fwd[ord(letter.upper())] = chr(cp)
    # "s" / "x" stay plain, but uppercase S / X are folded to lowercase so a converted
    # string never mixes a capital S or X with the small-cap letters around it.
    for letter in ("s", "x"):
        if ord(letter.upper()) not in fwd:
            fwd[ord(letter.upper())] = letter
    # Reverse table (accepts both the safe and the extended glyph for "s").
    rev: dict[int, str] = {chr(cp): letter for letter, cp in _CODEPOINTS.items()}
    rev[chr(_EXTENDED_S)] = "s"
    return fwd, {ord(k): v for k, v in rev.items()}


_FWD, _REV = _build_tables()


def to_small_caps(text: str) -> str:
    """Raw letter mapping with no markup awareness. Use `convert()` for bot messages."""
    return text.translate(_FWD) if text else text


def from_small_caps(text: str) -> str:
    """Reverses the conversion (letters come back lowercase). Use it on user input."""
    return text.translate(_REV) if text else text


# --------------------------------------------------------------------------------------
# Protected spans
# --------------------------------------------------------------------------------------
_PLAIN_PROTECT = re.compile(
    r"""
      (?:https?://|tg://|ftp://)\S+                 # absolute links
    | (?<![\w@])(?:www\.|t\.me/|telegram\.me/)\S+   # bare links
    | \b[\w.+-]+@[\w-]+(?:\.[\w-]+)+                # e-mail addresses
    | (?<![\w@])@\w+                                # @usernames
    | (?<![\w/])/[A-Za-z_]\w*(?:/\w+)*              # /commands and /paths
    | (?<![\w&])\#[A-Za-z_]\w*                      # #hashtags
    """,
    re.VERBOSE,
)

_HTML_PROTECT = re.compile(
    r"<(pre|code)\b[^>]*>.*?</\1\s*>"  # code blocks: copied verbatim by people
    r"|<!--.*?-->"
    r"|<[^>]*>"                         # any other tag, attributes included
    r"|&#?\w+;",                        # entities
    re.IGNORECASE | re.DOTALL,
)

_MD_PROTECT = re.compile(r"```.*?```|`[^`\n]*`|\]\([^)\n]*\)", re.DOTALL)


def _convert_plain_segment(text: str) -> str:
    out: list[str] = []
    pos = 0
    for m in _PLAIN_PROTECT.finditer(text):
        out.append(to_small_caps(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(to_small_caps(text[pos:]))
    return "".join(out)


def _convert_with(pattern: re.Pattern, text: str) -> str:
    out: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(_convert_plain_segment(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_convert_plain_segment(text[pos:]))
    return "".join(out)


def convert_html(text: str) -> str:
    """Small-caps for Telegram HTML (and Bot API 10.3 rich HTML) strings."""
    return _convert_with(_HTML_PROTECT, text) if text else text


def convert_markdown(text: str) -> str:
    """Small-caps for legacy Markdown / MarkdownV2 strings."""
    return _convert_with(_MD_PROTECT, text) if text else text


def convert_plain(text: str) -> str:
    """Small-caps for text sent without a parse mode."""
    return _convert_plain_segment(text) if text else text


def convert(text: Any, parse_mode: Any = None) -> Any:
    """Converts `text` according to the Telegram `parse_mode` it will be sent with.

    Non-string values and empty strings are returned unchanged. When the feature is
    switched off (`SMALL_CAPS=0`) the text is returned unchanged as well.
    """
    if not isinstance(text, str) or not text or not enabled():
        return text
    mode = str(getattr(parse_mode, "value", parse_mode) or "").lower()
    if mode == "html":
        return convert_html(text)
    if mode.startswith("markdown"):
        return convert_markdown(text)
    return convert_plain(text)


# --------------------------------------------------------------------------------------
# Inline keyboards
# --------------------------------------------------------------------------------------
def convert_markup(markup: Any) -> Any:
    """Returns a copy of an `InlineKeyboardMarkup` whose button labels are small caps.

    Callback data, URLs, `copy_text`, styles and every other button field are preserved.
    Reply keyboards and non-keyboard objects are returned unchanged.
    """
    if markup is None or not enabled() or not getattr(markup, "inline_keyboard", None):
        return markup
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ImportError:  # pragma: no cover
        return markup

    rows = []
    changed = False
    for row in markup.inline_keyboard:
        new_row = []
        for btn in row:
            label = getattr(btn, "text", None)
            new_label = convert_plain(label) if isinstance(label, str) else label
            if new_label == label:
                new_row.append(btn)
                continue
            data = btn.to_dict()
            data["text"] = new_label
            new_row.append(InlineKeyboardButton.de_json(data, None))
            changed = True
        rows.append(new_row)
    return InlineKeyboardMarkup(rows) if changed else markup
