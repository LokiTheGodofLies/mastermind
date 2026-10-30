import asyncio
import html
import io
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import ContextTypes
except ImportError:
    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None, url=None):
            self.text = text
            self.callback_data = callback_data
            self.url = url
    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
    Update = object
    Bot = object
    class ContextTypes:
        DEFAULT_TYPE = object

from config import (
    bot_name,
    helper_bot_tokens,
    posting_channel_id,
    storage_group_id,
)
from modules.database.user_db import is_admin_or_owner, is_creator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper Bot Audit Command (/checkhelpers)
# ---------------------------------------------------------------------------
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
        await msg.reply_text("⚠️ No helper bot tokens configured in PUBLIC_/TESTING_HELPER_BOT_TOKENS.")
        return

    storage_id = storage_group_id()
    chan_id = posting_channel_id()

    status_msg = await msg.reply_text("🔍 Auditing configured helper bots...")
    lines = [f"🤖 <b>Helper Bots Permission Audit ({len(tokens)} configured)</b>\n"]

    all_ok = True
    for i, token in enumerate(tokens, 1):
        try:
            hbot = Bot(token)
            me = await hbot.get_me()
            username = me.username or f"Helper #{i}"
            lines.append(f"<b>{i}. @{username} (ID: <code>{me.id}</code>)</b>")

            if storage_id:
                try:
                    sm = await hbot.get_chat_member(int(storage_id), me.id)
                    if sm.status in ("member", "administrator", "creator"):
                        lines.append("• Storage Group: ✅ Present")
                    else:
                        all_ok = False
                        lines.append(f"• Storage Group: ❌ Not a member (status: {sm.status})")
                except Exception as exc:
                    all_ok = False
                    lines.append(f"• Storage Group: ❌ Error ({html.escape(str(exc))})")
            else:
                lines.append("• Storage Group: ⚠️ PUBLIC_/TESTING_STORAGE_GROUP_ID not configured")

            if chan_id:
                try:
                    pm = await hbot.get_chat_member(int(chan_id), me.id)
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
# Creator-Only /publish Command (Production Deploy)
# ---------------------------------------------------------------------------
async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /publish — Creator-only deployment of test branch to main."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    if not is_creator(user.id):
        await msg.reply_text(
            "⛔ <b>Access Denied:</b> The <code>/publish</code> command is exclusive to the <b>Creator</b>.",
            parse_mode="HTML",
        )
        return

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


# ---------------------------------------------------------------------------
# Creator-Only Terminal / Shell Executor (/sh, /term)
# ---------------------------------------------------------------------------
async def sh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes bash shell commands directly from Telegram (Creator Only)."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    if not is_creator(user.id):
        await msg.reply_text("⛔ <b>Access Denied:</b> Shell commands are exclusive to the <b>Creator</b>.", parse_mode="HTML")
        return

    cmd = " ".join(context.args).strip() if context.args else ""
    if not cmd:
        await msg.reply_text(
            "💻 <b>Creator Shell Terminal</b>\n\n"
            "<b>Usage:</b> <code>/sh &lt;command&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/sh git status</code>\n"
            "• <code>/sh git log -1 --oneline</code>\n"
            "• <code>/sh python3 -m compileall .</code>\n"
            "• <code>/sh df -h</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await msg.reply_text(f"⏳ <b>Running:</b> <code>{html.escape(cmd)}</code>...", parse_mode="HTML")

    def _exec():
        repo_path = os.path.expanduser("~/mastermind")
        if not os.path.isdir(repo_path):
            repo_path = os.getcwd()

        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=120,
        )
        return res.returncode, res.stdout, res.stderr

    try:
        code, stdout, stderr = await asyncio.to_thread(_exec)
        out = (stdout + stderr).strip()
        if not out:
            out = f"(Process exited with return code {code})"

        if len(out) > 3500:
            bio = io.BytesIO(out.encode("utf-8"))
            bio.name = "output.txt"
            await status_msg.delete()
            await msg.reply_document(
                document=bio,
                caption=f"💻 <b>Command:</b> <code>{html.escape(cmd)}</code>\n<b>Exit Code:</b> <code>{code}</code>",
                parse_mode="HTML",
            )
        else:
            await status_msg.edit_text(
                f"💻 <b>Command:</b> <code>{html.escape(cmd)}</code>\n\n<pre>{html.escape(out)}</pre>",
                parse_mode="HTML",
            )
    except subprocess.TimeoutExpired:
        await status_msg.edit_text(f"⏱ <b>Command timed out (120s limit):</b> <code>{html.escape(cmd)}</code>", parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Execution Error:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Creator-Only In-Chat Code Updater (/update)
# ---------------------------------------------------------------------------
async def update_zip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows Creator to send or reply to a .zip archive to update the bot in-chat."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    if not is_creator(user.id):
        await msg.reply_text("⛔ <b>Access Denied:</b> Bot updates are exclusive to the <b>Creator</b>.", parse_mode="HTML")
        return

    doc = getattr(msg, "document", None)
    if not doc and msg.reply_to_message:
        doc = getattr(msg.reply_to_message, "document", None)

    if not doc:
        context.user_data["awaiting_update_zip"] = True
        await msg.reply_text(
            "📦 <b>In-Chat Bot Code Updater</b>\n\n"
            "Please send or forward the updated <code>.zip</code> file to this chat now.\n"
            "The bot will unpack it, compile-verify the code, commit, and push to GitHub automatically!",
            parse_mode="HTML",
        )
        return

    await _process_update_zip(update, context, doc)


async def handle_update_zip_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Catches document uploads when awaiting an update zip from Creator."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or not is_creator(user.id):
        return False

    if context.user_data.get("awaiting_update_zip"):
        doc = getattr(msg, "document", None)
        if doc and (doc.file_name or "").lower().endswith(".zip"):
            context.user_data.pop("awaiting_update_zip", None)
            await _process_update_zip(update, context, doc)
            return True
    return False


async def _process_update_zip(update: Update, context: ContextTypes.DEFAULT_TYPE, doc):
    msg = update.effective_message
    fn = doc.file_name or "update.zip"

    if not fn.lower().endswith(".zip"):
        await msg.reply_text("❌ Please send a valid <code>.zip</code> archive.", parse_mode="HTML")
        return

    status_msg = await msg.reply_text(f"⏳ <b>Downloading {html.escape(fn)}...</b>", parse_mode="HTML")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        tmp_zip = os.path.join(tempfile.gettempdir(), f"update_{doc.file_unique_id}.zip")
        await tg_file.download_to_drive(tmp_zip)

        await status_msg.edit_text("📦 <b>Unpacking and verifying code...</b>", parse_mode="HTML")

        repo_path = os.path.expanduser("~/mastermind")
        if not os.path.isdir(repo_path):
            repo_path = os.getcwd()

        def _unpack_and_test():
            tmp_dir = os.path.join(tempfile.gettempdir(), f"mm_up_{doc.file_unique_id}")
            os.makedirs(tmp_dir, exist_ok=True)
            with zipfile.ZipFile(tmp_zip, "r") as z:
                z.extractall(tmp_dir)

            src_dir = tmp_dir
            subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, d))]
            if len(subdirs) == 1 and "mastermind" in os.path.basename(subdirs[0]).lower():
                src_dir = subdirs[0]

            for root, dirs, files in os.walk(src_dir):
                rel = os.path.relpath(root, src_dir)
                dest_root = os.path.join(repo_path, rel) if rel != "." else repo_path
                os.makedirs(dest_root, exist_ok=True)
                for f in files:
                    shutil.copy2(os.path.join(root, f), os.path.join(dest_root, f))

            shutil.rmtree(tmp_dir, ignore_errors=True)
            try:
                os.remove(tmp_zip)
            except Exception:
                pass

            res = subprocess.run(
                "python3 -m compileall .",
                shell=True,
                capture_output=True,
                text=True,
                cwd=repo_path,
            )
            if res.returncode != 0:
                return False, f"Compilation failed with errors:\n{res.stdout}\n{res.stderr}"

            git_res = subprocess.run(
                "git status --porcelain",
                shell=True,
                capture_output=True,
                text=True,
                cwd=repo_path,
            )
            has_changes = bool(git_res.stdout.strip())

            push_log = ""
            if has_changes:
                subprocess.run("git add -A", shell=True, capture_output=True, cwd=repo_path)
                commit_res = subprocess.run(
                    'git commit -m "feat: in-chat auto-update via /update"',
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                )
                push_log += commit_res.stdout + "\n"

                gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
                if gh_token:
                    push_url_loki = f"https://{gh_token}@github.com/LokiTheGodofLies/mastermind.git"
                    push_url_orig = f"https://{gh_token}@github.com/mastermindmayankofficial/mastermind.git"
                    p1 = subprocess.run(f"git push {push_url_loki} test", shell=True, capture_output=True, text=True, cwd=repo_path)
                    p2 = subprocess.run(f"git push {push_url_orig} test", shell=True, capture_output=True, text=True, cwd=repo_path)
                    push_log += f"Loki Push: {p1.stdout}{p1.stderr}\nOrigin Push: {p2.stdout}{p2.stderr}\n"
                else:
                    p1 = subprocess.run("git push loki test", shell=True, capture_output=True, text=True, cwd=repo_path)
                    p2 = subprocess.run("git push origin test", shell=True, capture_output=True, text=True, cwd=repo_path)
                    push_log += f"Loki Push: {p1.stdout}{p1.stderr}\nOrigin Push: {p2.stdout}{p2.stderr}\n"

            return True, push_log

        ok, log = await asyncio.to_thread(_unpack_and_test)
        if ok:
            gh_token_status = (
                "✅ Pushed to GitHub automatically!"
                if os.environ.get("GITHUB_TOKEN")
                else "ℹ️ Code updated and verified with 0 errors! (Add GITHUB_TOKEN to Render Environment Variables for automatic git push)."
            )
            await status_msg.edit_text(
                "🎉 <b>Bot Updated Successfully!</b>\n\n"
                "• Code unpacked and verified with <code>compileall</code>.\n"
                f"• {gh_token_status}\n\n"
                f"<pre>{html.escape(log[-800:]) if log else 'All files compiled successfully with 0 errors.'}</pre>",
                parse_mode="HTML",
            )
        else:
            await status_msg.edit_text(
                f"❌ <b>Update Failed:</b>\n\n<pre>{html.escape(log[-1000:])}</pre>",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.exception("In-chat update error: %s", e)
        await status_msg.edit_text(
            f"❌ <b>Error processing update:</b> <code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
        )
