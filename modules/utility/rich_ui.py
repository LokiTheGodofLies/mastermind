"""Telegram Bot API 10.3 Rich Formatting & Colorful In-Text Button Engine.

Provides native support for Telegram Bot API 10.3 (August 2026+):
  * `sendRichMessage` and `editMessageText(rich_message=...)` via `InputRichMessage`
  * In-text `<tg-button>` and `<tg-button-row align="center">` components
  * Colorful button styles:
      - `primary` (Blue)
      - `success` (Green)
      - `danger`  (Red)
      - `link`    (Subtle link button)
      - `disabled` (`DisabledButton` / `<tg-button type="disabled">`)
  * Rich HTML elements: `<mark>` pill badges, `<blockquote expandable>`, `<h3>` headings,
    and `<table bordered striped compact>`
  * Automatic fallback to `sendMessage` / `editMessageText` with styled `InlineKeyboardButton`
    (`api_kwargs={"style": ...}`) so every message succeeds across all Telegram clients and mocks.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
    from telegram.error import BadRequest, TelegramError
except ImportError:  # pragma: no cover
    Bot = None  # type: ignore
    Message = None  # type: ignore
    BadRequest = Exception  # type: ignore
    TelegramError = Exception  # type: ignore

    class InlineKeyboardButton:  # type: ignore
        def __init__(self, text, callback_data=None, url=None, api_kwargs=None):
            self.text = text
            self.callback_data = callback_data
            self.url = url
            self.api_kwargs = api_kwargs or {}

    class InlineKeyboardMarkup:  # type: ignore
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

from modules.utility.small_caps import (
    convert as sc_convert,
    convert_markup as sc_markup,
    from_small_caps,
)

logger = logging.getLogger(__name__)


def _sc_allowed(chat_id: Any = None) -> bool:
    """Small caps is applied to every outgoing message except those posted into the Storage
    Group. Storage captions are machine-read (re-indexing, caption edits, `copy_message`
    deliveries), so they must stay as plain data."""
    if chat_id is None:
        return True
    try:
        from config import storage_group_id

        sid = storage_group_id()
        return not (sid and str(chat_id) == str(sid))
    except Exception:  # pragma: no cover - config unavailable
        return True


def _sc_text_call(args: tuple, kwargs: dict, text_pos: int, text_key: str, chat_id: Any):
    """Last step before a text/caption call leaves the bot: small-caps the text and buttons."""
    if not _sc_allowed(chat_id):
        return args, kwargs
    pm = kwargs.get("parse_mode")
    if text_key in kwargs:
        kwargs[text_key] = sc_convert(kwargs[text_key], pm)
    elif len(args) > text_pos:
        args = args[:text_pos] + (sc_convert(args[text_pos], pm),) + args[text_pos + 1:]
    if kwargs.get("reply_markup") is not None:
        kwargs["reply_markup"] = sc_markup(kwargs["reply_markup"])
    return args, kwargs


_PAGE_INDICATOR_RE = re.compile(r"^(?:📄\s*)?\d+\s*/\s*\d+$")

_DANGER_PATTERNS = (
    "⛔",
    "❌",
    "🛑",
    "🚫",
    "🗑",
    "cancel",
    "stop",
    "reject",
    "close menu",
    "delete",
    "ban",
    "pin in chats: ❌",
)

_DANGER_CALLBACKS = (
    "idx_cancel_",
    "idx_rej_",
    "bc_cancel",
    "bc_stop_active",
    "publish_cancel",
    "req_join_no",
    "req_stat_rej_",
    "quiz_ans_no",
)

_SUCCESS_PATTERNS = (
    "✅",
    "📥",
    "🚀",
    "📨",
    "📤",
    "🎉",
    "▶️",
    "🎁",
    "confirm",
    "approve",
    "send all",
    "send broadcast",
    "submit",
    "resume",
    "start verification",
    "join support",
    "generate invite",
    "open search topic",
    "refer",
    "share link",
    "copy link",
    "open in @",
    "start @",
    "receive in pm",
    "view in posting channel",
    "download",
)

_SUCCESS_CALLBACKS = (
    "file_dl_",
    "sa_",
    "idx_apr_",
    "idx_pr_dir_",
    "bc_confirm",
    "bc_resume",
    "publish_confirm",
    "req_sub_",
    "req_stat_done_",
    "quiz_ans_yes",
    "support_start_quiz",
    "generate_group_invite",
)


def is_disabled_button(text: str = "", callback_data: str | None = None, api_kwargs: dict | None = None) -> bool:
    """Returns True if a button represents a non-interactive indicator (e.g. `1/1`, `📄 1/2`, `noop`)."""
    if api_kwargs and "disabled" in api_kwargs:
        return True
    cb = (callback_data or "").strip().lower()
    t = (text or "").strip()
    if cb == "noop" or _PAGE_INDICATOR_RE.match(t):
        return True
    return False


def infer_button_style(
    text: str = "",
    callback_data: str | None = None,
    url: str | None = None,
    explicit_style: str | None = None,
) -> str:
    """Infers the Bot API 10.3 color style (`primary`, `success`, `danger`, `link`) for a button."""
    if explicit_style in ("primary", "success", "danger", "link"):
        return explicit_style

    # Labels that were already converted to small caps are mapped back first so the
    # keyword rules below ("cancel", "confirm", ...) keep working.
    t_low = from_small_caps(text or "").strip().lower()
    cb_low = (callback_data or "").strip().lower()
    url_low = (url or "").strip().lower()

    if t_low.endswith("✅") or "✅ on" in t_low:
        return "success"
    if "❌ off" in t_low:
        return "danger"

    for p in _DANGER_CALLBACKS:
        if cb_low.startswith(p) or cb_low == p:
            return "danger"
    for p in _DANGER_PATTERNS:
        if p in t_low:
            return "danger"

    for p in _SUCCESS_CALLBACKS:
        if cb_low.startswith(p) or cb_low == p:
            return "success"
    for p in _SUCCESS_PATTERNS:
        if p in t_low:
            return "success"

    if url_low and ("?start=dl_" in url_low or "t.me/share/url" in url_low or "?start=ref_" in url_low):
        return "success"

    return "primary"


def styled_button(
    text: str,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    disabled: bool = False,
    copy_text: str | None = None,
    **kwargs: Any,
) -> InlineKeyboardButton:
    """Creates an `InlineKeyboardButton` with Bot API 10.3 `style` (and optional `disabled` / `copy_text`)."""
    api_kw = dict(kwargs.pop("api_kwargs", None) or {})
    resolved_style = infer_button_style(text, callback_data, url, explicit_style=style)
    api_kw["style"] = resolved_style

    if disabled or is_disabled_button(text, callback_data, api_kw):
        api_kw["disabled"] = {}
        if not callback_data and not url and not copy_text:
            callback_data = "noop"

    if copy_text:
        api_kw["copy_text"] = {"text": str(copy_text)}
        return InlineKeyboardButton(text=text, api_kwargs=api_kw, **kwargs)

    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        url=url,
        api_kwargs=api_kw,
        **kwargs,
    )


def style_inline_keyboard(
    markup: InlineKeyboardMarkup | None,
    include_disabled: bool = False,
) -> InlineKeyboardMarkup | None:
    """Returns a copy of `InlineKeyboardMarkup` with colorful Bot API `style` injected into every button."""
    if not markup or not getattr(markup, "inline_keyboard", None):
        return markup

    new_rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for btn in row:
            text = getattr(btn, "text", "")
            cb = getattr(btn, "callback_data", None)
            url = getattr(btn, "url", None)
            orig_api_kw = dict(getattr(btn, "api_kwargs", None) or {})
            style = orig_api_kw.get("style") or infer_button_style(text, cb, url)

            api_kw = dict(orig_api_kw)
            api_kw["style"] = style

            if include_disabled and is_disabled_button(text, cb, orig_api_kw):
                api_kw["disabled"] = {}
                cb = None
            else:
                api_kw.pop("disabled", None)
                if not cb and not url and "copy_text" not in api_kw:
                    cb = "noop"

            new_row.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=cb,
                    url=url,
                    api_kwargs=api_kw,
                )
            )
        if new_row:
            new_rows.append(new_row)
    return InlineKeyboardMarkup(new_rows)


def tg_button_html(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    copy_text: str | None = None,
    style: str | None = None,
    disabled: bool = False,
) -> str:
    """Builds a Bot API 10.3 `<tg-button>` HTML tag."""
    esc_label = html.escape(str(text or ""), quote=False)
    if disabled or is_disabled_button(text, callback_data):
        return f'<tg-button type="disabled">{esc_label}</tg-button>'

    resolved_style = infer_button_style(text, callback_data, url, explicit_style=style)
    style_attr = f' style="{resolved_style}"' if resolved_style else ""

    if copy_text is not None:
        esc_copy = html.escape(str(copy_text), quote=True)
        return f'<tg-button type="copy_text"{style_attr} text="{esc_copy}">{esc_label}</tg-button>'
    if url:
        esc_url = html.escape(str(url), quote=True)
        return f'<tg-button type="url"{style_attr} url="{esc_url}">{esc_label}</tg-button>'
    esc_cb = html.escape(str(callback_data or "noop"), quote=True)
    return f'<tg-button type="callback_data"{style_attr} data="{esc_cb}">{esc_label}</tg-button>'


def tg_button_row_html(buttons_html: list[str], align: str = "center") -> str:
    """Wraps one or more `<tg-button>` strings in a `<tg-button-row>` block."""
    if not buttons_html:
        return ""
    align_attr = f' align="{html.escape(align, quote=True)}"' if align else ""
    return f"<tg-button-row{align_attr}>{''.join(buttons_html)}</tg-button-row>"


def keyboard_to_rich_rows(markup: InlineKeyboardMarkup | None, align: str = "center") -> str:
    """Converts an `InlineKeyboardMarkup` into Bot API 10.3 `<tg-button-row>` blocks."""
    if not markup or not getattr(markup, "inline_keyboard", None):
        return ""

    row_blocks: list[str] = []
    for row in markup.inline_keyboard:
        btn_tags: list[str] = []
        for btn in row:
            text = getattr(btn, "text", "")
            cb = getattr(btn, "callback_data", None)
            url = getattr(btn, "url", None)
            api_kw = dict(getattr(btn, "api_kwargs", None) or {})
            explicit_style = api_kw.get("style")
            copy_obj = api_kw.get("copy_text")
            copy_val = copy_obj.get("text") if isinstance(copy_obj, dict) else None
            disabled = is_disabled_button(text, cb, api_kw)

            btn_tags.append(
                tg_button_html(
                    text,
                    callback_data=cb,
                    url=url,
                    copy_text=copy_val,
                    style=explicit_style,
                    disabled=disabled,
                )
            )
        if btn_tags:
            row_blocks.append(tg_button_row_html(btn_tags, align=align))
    return "\n".join(row_blocks)


def build_rich_html(
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    align: str = "center",
) -> str:
    """Combines rich HTML body text with `<tg-button-row>` blocks from `reply_markup`."""
    base = (text or "").strip()
    kb_html = keyboard_to_rich_rows(reply_markup, align=align)
    if kb_html:
        if base:
            return f"{base}\n\n{kb_html}"
        return kb_html
    return base


_RE_TG_BUTTON_ROW = re.compile(r"<tg-button-row[^>]*>(.*?)</tg-button-row>", re.DOTALL | re.IGNORECASE)
_RE_TG_BUTTON = re.compile(
    r'<tg-button([^>]*)>(.*?)</tg-button>',
    re.DOTALL | re.IGNORECASE,
)
_RE_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def extract_buttons_and_clean_html_for_fallback(
    rich_text: str,
    existing_markup: InlineKeyboardMarkup | None = None,
    small_caps: bool = True,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Converts Bot API 10.3 Rich HTML (`<tg-button-row>`, `<tg-button>`, `<mark>`, `<h3>`)
    into standard Telegram `parse_mode="HTML"` text + styled `InlineKeyboardMarkup`
    if `sendRichMessage` is unavailable or rejected.
    """
    if not rich_text:
        return "", style_inline_keyboard(existing_markup)

    extracted_rows: list[list[InlineKeyboardButton]] = []

    def _parse_button_attrs(attr_str: str, inner_html: str) -> InlineKeyboardButton | None:
        attrs = dict(_RE_ATTR.findall(attr_str or ""))
        btype = (attrs.get("type") or "callback_data").lower()
        bstyle = attrs.get("style")
        clean_label = html.unescape(re.sub(r"<[^>]+>", "", inner_html or "")).strip() or "Button"
        if btype == "disabled":
            return styled_button(clean_label, callback_data="noop", style="primary")
        if btype == "url" and attrs.get("url"):
            return styled_button(clean_label, url=html.unescape(attrs["url"]), style=bstyle)
        if btype == "copy_text" and attrs.get("text"):
            return styled_button(clean_label, copy_text=html.unescape(attrs["text"]), style=bstyle)
        cb = html.unescape(attrs.get("data") or "noop")
        return styled_button(clean_label, callback_data=cb, style=bstyle)

    def _replace_row(match: re.Match) -> str:
        row_inner = match.group(1) or ""
        row_btns: list[InlineKeyboardButton] = []
        for bm in _RE_TG_BUTTON.finditer(row_inner):
            btn = _parse_button_attrs(bm.group(1), bm.group(2))
            if btn is not None:
                row_btns.append(btn)
        if row_btns:
            extracted_rows.append(row_btns)
        return ""

    cleaned = _RE_TG_BUTTON_ROW.sub(_replace_row, rich_text)

    def _replace_inline_btn(match: re.Match) -> str:
        attrs = dict(_RE_ATTR.findall(match.group(1) or ""))
        inner = match.group(2) or ""
        btype = (attrs.get("type") or "").lower()
        if btype == "url" and attrs.get("url"):
            return f'<a href="{attrs["url"]}">{inner}</a>'
        btn = _parse_button_attrs(match.group(1), inner)
        if btn is not None:
            extracted_rows.append([btn])
        return f"<b>{inner}</b>"

    cleaned = _RE_TG_BUTTON.sub(_replace_inline_btn, cleaned)
    if small_caps:
        # Must happen before `<mark>` becomes `<code>`: code spans are deliberately left
        # untouched by the small-caps engine, but badge text should be converted.
        cleaned = sc_convert(cleaned, "HTML")
    cleaned = re.sub(r"<mark>(.*?)</mark>", r"<code>\1</code>", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<h3>(.*?)</h3>", r"<b>\1</b>", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    final_rows: list[list[InlineKeyboardButton]] = list(extracted_rows)
    if existing_markup and getattr(existing_markup, "inline_keyboard", None):
        styled_existing = style_inline_keyboard(existing_markup, include_disabled=False)
        if styled_existing:
            final_rows.extend(styled_existing.inline_keyboard)

    final_markup = InlineKeyboardMarkup(final_rows) if final_rows else None
    return cleaned, final_markup


async def send_rich_message(
    bot: Bot,
    chat_id: int | str,
    html_text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    message_thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    disable_notification: bool | None = None,
    prefer_small_media: bool = False,
) -> Message:
    """Calls Bot API 10.3 `sendRichMessage` directly via `bot._post`."""
    rich_html = build_rich_html(html_text, reply_markup)
    if _sc_allowed(chat_id):
        rich_html = sc_convert(rich_html, "HTML")  # after button styles were inferred
    rich_payload: dict[str, Any] = {"html": rich_html}
    if prefer_small_media:
        rich_payload["prefer_small_media"] = True

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": rich_payload,
    }
    if message_thread_id is not None:
        data["message_thread_id"] = message_thread_id
    if reply_to_message_id is not None:
        data["reply_parameters"] = {"message_id": reply_to_message_id, "allow_sending_without_reply": True}
    if disable_notification is not None:
        data["disable_notification"] = disable_notification

    result = await bot._post("sendRichMessage", data=data)
    return Message.de_json(result, bot)  # type: ignore[return-value]


async def edit_rich_message(
    bot: Bot,
    chat_id: int | str | None,
    message_id: int | None,
    html_text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    prefer_small_media: bool = False,
) -> Message | bool:
    """Calls Bot API 10.3 `editMessageText` with `rich_message` directly via `bot._post`."""
    rich_html = build_rich_html(html_text, reply_markup)
    if _sc_allowed(chat_id):
        rich_html = sc_convert(rich_html, "HTML")  # after button styles were inferred
    rich_payload: dict[str, Any] = {"html": rich_html}
    if prefer_small_media:
        rich_payload["prefer_small_media"] = True

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "rich_message": rich_payload,
    }
    result = await bot._post("editMessageText", data=data)
    if isinstance(result, bool):
        return result
    return Message.de_json(result, bot)  # type: ignore[return-value]


_PATCHED = False


def install_rich_ui_patches() -> None:
    """Installs transparent Bot API 10.3 Rich Message & Colorful Button wrappers on `telegram.Bot`."""
    global _PATCHED
    if _PATCHED or Bot is None or not hasattr(Bot, "send_message"):
        return

    orig_send_message = Bot.send_message
    orig_edit_message_text = Bot.edit_message_text
    orig_edit_reply_markup = getattr(Bot, "edit_message_reply_markup", None)
    orig_send_photo = getattr(Bot, "send_photo", None)
    orig_send_video = getattr(Bot, "send_video", None)
    orig_send_animation = getattr(Bot, "send_animation", None)

    async def _patched_send_message(self: Bot, *args: Any, **kwargs: Any):
        text = kwargs.get("text")
        if text is None and len(args) >= 2:
            text = args[1]
        chat_id = kwargs.get("chat_id")
        if chat_id is None and len(args) >= 1:
            chat_id = args[0]

        parse_mode = kwargs.get("parse_mode")
        reply_markup = kwargs.get("reply_markup")
        has_rich_tags = bool(
            text and ("<tg-button" in text or "<mark>" in text or "<blockquote expandable" in text or "<table" in text)
        )

        if chat_id is not None and text and (has_rich_tags or (reply_markup and parse_mode == "HTML")):
            try:
                reply_to_mid = kwargs.get("reply_to_message_id")
                if reply_to_mid is None and kwargs.get("reply_parameters") is not None:
                    rp = kwargs["reply_parameters"]
                    reply_to_mid = getattr(rp, "message_id", None) if not isinstance(rp, dict) else rp.get("message_id")
                return await send_rich_message(
                    bot=self,
                    chat_id=chat_id,
                    html_text=text,
                    reply_markup=reply_markup,
                    message_thread_id=kwargs.get("message_thread_id"),
                    reply_to_message_id=reply_to_mid,
                    disable_notification=kwargs.get("disable_notification"),
                    prefer_small_media=bool(kwargs.get("disable_web_page_preview")),
                )
            except Exception as rich_exc:
                logger.debug("sendRichMessage fallback to styled sendMessage: %s", rich_exc)

        if text and has_rich_tags:
            clean_text, merged_markup = extract_buttons_and_clean_html_for_fallback(
                text, reply_markup, small_caps=_sc_allowed(chat_id)
            )
            if "text" in kwargs or len(args) < 2:
                kwargs["text"] = clean_text
            else:
                args = (args[0], clean_text) + args[2:]
            kwargs["reply_markup"] = merged_markup
            kwargs["parse_mode"] = "HTML"
        elif reply_markup is not None:
            kwargs["reply_markup"] = style_inline_keyboard(reply_markup, include_disabled=False)

        args, kwargs = _sc_text_call(args, kwargs, 1, "text", chat_id)
        return await orig_send_message(self, *args, **kwargs)

    async def _patched_edit_message_text(self: Bot, *args: Any, **kwargs: Any):
        text = kwargs.get("text")
        if text is None and len(args) >= 1:
            text = args[0]
        chat_id = kwargs.get("chat_id")
        message_id = kwargs.get("message_id")
        parse_mode = kwargs.get("parse_mode")
        reply_markup = kwargs.get("reply_markup")
        has_rich_tags = bool(
            text and ("<tg-button" in text or "<mark>" in text or "<blockquote expandable" in text or "<table" in text)
        )

        if chat_id is not None and message_id is not None and text and (has_rich_tags or (reply_markup and parse_mode == "HTML")):
            try:
                return await edit_rich_message(
                    bot=self,
                    chat_id=chat_id,
                    message_id=message_id,
                    html_text=text,
                    reply_markup=reply_markup,
                    prefer_small_media=bool(kwargs.get("disable_web_page_preview")),
                )
            except Exception as rich_exc:
                if "message is not modified" in str(rich_exc).lower():
                    raise
                logger.debug("editRichMessage fallback to styled editMessageText: %s", rich_exc)

        if text and has_rich_tags:
            clean_text, merged_markup = extract_buttons_and_clean_html_for_fallback(
                text, reply_markup, small_caps=_sc_allowed(chat_id)
            )
            if "text" in kwargs or len(args) < 1:
                kwargs["text"] = clean_text
            else:
                args = (clean_text,) + args[1:]
            kwargs["reply_markup"] = merged_markup
            kwargs["parse_mode"] = "HTML"
        elif reply_markup is not None:
            kwargs["reply_markup"] = style_inline_keyboard(reply_markup, include_disabled=False)

        args, kwargs = _sc_text_call(args, kwargs, 0, "text", chat_id)
        return await orig_edit_message_text(self, *args, **kwargs)

    async def _patched_edit_reply_markup(self: Bot, *args: Any, **kwargs: Any):
        if kwargs.get("reply_markup") is not None:
            kwargs["reply_markup"] = style_inline_keyboard(kwargs["reply_markup"], include_disabled=False)
            if _sc_allowed(kwargs.get("chat_id")):
                kwargs["reply_markup"] = sc_markup(kwargs["reply_markup"])
        return await orig_edit_reply_markup(self, *args, **kwargs)

    def _wrap_media_method(orig_fn):
        async def _wrapped(self: Bot, *args: Any, **kwargs: Any):
            if kwargs.get("reply_markup") is not None:
                kwargs["reply_markup"] = style_inline_keyboard(kwargs["reply_markup"], include_disabled=False)
            chat_id = kwargs.get("chat_id", args[0] if args else None)
            args, kwargs = _sc_text_call(args, kwargs, 99, "caption", chat_id)
            return await orig_fn(self, *args, **kwargs)
        return _wrapped

    def _wrap_callback_answer(orig_fn):
        async def _wrapped(self: Bot, *args: Any, **kwargs: Any):
            # Toast / alert text of `query.answer("...")` (plain text, no parse mode).
            if kwargs.get("text") is not None:
                kwargs["text"] = sc_convert(kwargs["text"])
            elif len(args) > 1:
                args = args[:1] + (sc_convert(args[1]),) + args[2:]
            return await orig_fn(self, *args, **kwargs)
        return _wrapped

    Bot.send_message = _patched_send_message  # type: ignore[assignment]
    Bot.edit_message_text = _patched_edit_message_text  # type: ignore[assignment]
    if orig_edit_reply_markup is not None:
        Bot.edit_message_reply_markup = _patched_edit_reply_markup  # type: ignore[assignment]
    if orig_send_photo is not None:
        Bot.send_photo = _wrap_media_method(orig_send_photo)  # type: ignore[assignment]
    if orig_send_video is not None:
        Bot.send_video = _wrap_media_method(orig_send_video)  # type: ignore[assignment]
    if orig_send_animation is not None:
        Bot.send_animation = _wrap_media_method(orig_send_animation)  # type: ignore[assignment]
    # Captions on documents / audio (e.g. `/log` export) and caption edits.
    for _name in ("send_document", "send_audio", "send_voice", "edit_message_caption"):
        _orig = getattr(Bot, _name, None)
        if _orig is not None:
            setattr(Bot, _name, _wrap_media_method(_orig))
    _orig_answer = getattr(Bot, "answer_callback_query", None)
    if _orig_answer is not None:
        Bot.answer_callback_query = _wrap_callback_answer(_orig_answer)  # type: ignore[assignment]

    _PATCHED = True
