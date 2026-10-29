import html
import logging
from telegram import Bot, Update
from telegram.ext import ContextTypes

from config import (
    helper_bot_tokens,
    posting_channel_id,
    storage_group_id,
)
from modules.database.user_db import is_admin_or_owner

logger = logging.getLogger(__name__)


async def checkhelpers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command (/checkhelpers) to audit helper bot presence and permissions."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin_or_owner(user.id):
        if msg:
            await msg.reply_text("⛔ Unauthorized. Only administrators can use /checkhelpers.")
        return

    tokens = helper_bot_tokens()
    if not tokens:
        await msg.reply_text("⚠️ No helper bot tokens found in HELPER_BOT_TOKENS.")
        return

    storage_id = storage_group_id()
    posting_id = posting_channel_id()

    status_msg = await msg.reply_text("🔍 Auditing helper bots presence and permissions...")

    lines = ["🤖 <b>Helper Bots Permissions Audit</b>\n"]
    all_ok = True

    for idx, token in enumerate(tokens, 1):
        lines.append(f"<b>Helper Bot #{idx}:</b>")
        try:
            async with Bot(token) as hb:
                me = await hb.get_me()
                uname = f"@{me.username}" if me.username else "No username"
                lines.append(f"• Identity: ✅ {html.escape(me.first_name)} ({uname}) [<code>{me.id}</code>]")

                # 1. Storage Group Check
                if storage_id:
                    try:
                        sm = await hb.get_chat_member(int(storage_id), me.id)
                        if sm.status in ("administrator", "creator", "member"):
                            lines.append(f"• Storage Group: ✅ Present ({sm.status})")
                        else:
                            all_ok = False
                            lines.append(f"• Storage Group: ❌ Not a member (status: {sm.status})")
                    except Exception as exc:
                        all_ok = False
                        lines.append(f"• Storage Group: ❌ Not accessible ({html.escape(str(exc))})")
                else:
                    lines.append("• Storage Group: ⚠️ STORAGE_GROUP_ID not configured")

                # 2. Posting Channel Check
                if posting_id:
                    try:
                        pm = await hb.get_chat_member(int(posting_id), me.id)
                        if pm.status in ("administrator", "creator"):
                            can_post = getattr(pm, "can_post_messages", True)
                            can_delete = getattr(pm, "can_delete_messages", True)
                            perms_detail = []
                            if can_post:
                                perms_detail.append("Post: ✅")
                            else:
                                perms_detail.append("Post: ❌")
                                all_ok = False
                            if can_delete:
                                perms_detail.append("Delete: ✅")
                            else:
                                perms_detail.append("Delete: ❌")
                                all_ok = False
                            lines.append(f"• Posting Channel: ✅ Admin ({', '.join(perms_detail)})")
                        else:
                            all_ok = False
                            lines.append(f"• Posting Channel: ❌ Not admin (status: {pm.status}) — must be Admin with Post & Delete rights")
                    except Exception as exc:
                        all_ok = False
                        lines.append(f"• Posting Channel: ❌ Not accessible ({html.escape(str(exc))})")
                else:
                    lines.append("• Posting Channel: ⚠️ POSTING_CHANNEL_ID not configured")

        except Exception as exc:
            all_ok = False
            lines.append(f"• Token (…{token[-4:]}): ❌ Unreachable ({html.escape(str(exc))})")

        lines.append("")

    if all_ok:
        lines.append("🎉 <b>All helper bots are correctly configured and have required permissions!</b>")
    else:
        lines.append("⚠️ <b>Issues detected!</b> Please ensure helper bots are added to the storage group and made Administrators with <b>Post Messages</b> and <b>Delete Messages</b> rights in the posting channel.")

    await status_msg.edit_text("\n".join(lines), parse_mode="HTML")
