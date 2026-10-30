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
        await msg.reply_text("⚠️ No helper bot tokens found in PUBLIC_/TESTING_HELPER_BOT_TOKENS.")
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
                    lines.append("• Storage Group: ⚠️ PUBLIC_/TESTING_STORAGE_GROUP_ID not configured")

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
                    lines.append("• Posting Channel: ⚠️ PUBLIC_/TESTING_POSTING_CHANNEL_ID not configured")

        except Exception as exc:
            all_ok = False
            lines.append(f"• Token (…{token[-4:]}): ❌ Unreachable ({html.escape(str(exc))})")

        lines.append("")

    if all_ok:
        lines.append("🎉 <b>All helper bots are correctly configured and have required permissions!</b>")
    else:
        lines.append("⚠️ <b>Issues detected!</b> Please ensure helper bots are added to the storage group and made Administrators with <b>Post Messages</b> and <b>Delete Messages</b> rights in the posting channel.")

    await status_msg.edit_text("\n".join(lines), parse_mode="HTML")



# ---------------------------------------------------------------------------
# Creator-only /publish command to merge test into main and deploy
# ---------------------------------------------------------------------------
async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /publish — Creator-only deployment of test branch to main."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    from modules.database.user_db import is_creator
    if not is_creator(user.id):
        await msg.reply_text(
            "⛔ <b>Access Denied:</b> The <code>/publish</code> command is exclusive to the <b>Creator</b>.",
            parse_mode="HTML",
        )
        return

    from config import bot_name
    text = (
        f"🚀 <b>Publish to Production — {bot_name()} Main Bot</b>\n\n"
        "This will merge the tested & verified <code>test</code> branch into <code>main</code> "
        "and push to both <code>loki main</code> and <code>origin main</code>, triggering "
        "automatic deployment on Render's Public Books Bot service.\n\n"
        "⚠️ <i>Please confirm to proceed with production deployment:</i>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Confirm Publish to Main", callback_data="publish_confirm")],
        [InlineKeyboardButton("⛔ Cancel", callback_data="publish_cancel")],
    ])
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def publish_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles publish confirmation and execution."""
    q = update.callback_query
    user = update.effective_user
    from modules.database.user_db import is_creator
    if not q or not user or not is_creator(user.id):
        if q:
            await q.answer("⛔ Access restricted to Creator only.", show_alert=True)
        return

    await q.answer()
    data = q.data

    if data == "publish_cancel":
        await q.edit_message_text("⛔ <b>Publish cancelled.</b>", parse_mode="HTML")
        return

    if data == "publish_confirm":
        await q.edit_message_text(
            "⏳ <b>Publishing to Production...</b>\n\n"
            "• Merging <code>test</code> → <code>main</code>\n"
            "• Pushing to <code>loki main</code> and <code>origin main</code>...",
            parse_mode="HTML",
        )

        def _do_git_publish():
            import subprocess
            repo_path = os.path.expanduser("~/mastermind")
            if not os.path.isdir(repo_path):
                repo_path = os.getcwd()

            cmds = [
                "git fetch loki main",
                "git checkout main",
                "git pull loki main",
                "git merge test -m \"Merge verified test branch into main via /publish\"",
                "git push loki main",
                "git push origin main",
                "git checkout test",
            ]
            logs = []
            for cmd in cmds:
                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                )
                logs.append(f"$ {cmd}\n{res.stdout}{res.stderr}".strip())
                if res.returncode != 0:
                    subprocess.run("git checkout test", shell=True, cwd=repo_path, capture_output=True)
                    return False, "\n".join(logs)
            return True, "\n".join(logs)

        success, full_log = await asyncio.to_thread(_do_git_publish)

        if success:
            await q.edit_message_text(
                "🎉 <b>Successfully Published to Production!</b>\n\n"
                "✅ Merged <code>test</code> into <code>main</code>\n"
                "✅ Pushed to <code>loki main</code> and <code>origin main</code>\n"
                "⚡ Render Public Books Bot deployment triggered automatically!\n"
                "🔄 Switched back to <code>test</code> branch.",
                parse_mode="HTML",
            )
        else:
            tail = html.escape(full_log[-1200:]) if full_log else "Unknown error"
            await q.edit_message_text(
                f"❌ <b>Publish Failed:</b>\n\n<pre>{tail}</pre>\n\n"
                "<i>Reverted back to test branch safely.</i>",
                parse_mode="HTML",
            )
