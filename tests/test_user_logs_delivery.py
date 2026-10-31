"""Offline tests (build 20261101): new-user logs, referral table + name fix, <br> line breaks,
PM-only delivery cards + combined Send All table, /index callback parsing + job persistence."""
import asyncio, os, re, sys, tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp()
os.environ["USERS_DB_PATH"] = os.path.join(_TMP, "users.db")
os.environ.setdefault("CREATOR_ID", "1")
os.environ.setdefault("BOT_MODE", "testing")
os.environ.setdefault("TESTING_LOGGER_GROUP_ID", "-1004293995714")
os.environ.setdefault("TESTING_USER_LOG_TOPIC_ID", "589")
os.environ.setdefault("TESTING_BOT_TOKEN", "9185254121:AAFakeMainToken")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from telegram import InlineKeyboardMarkup
from telegram.error import BadRequest
from modules.database import user_db as udb
from modules.log import startup_log as sl
from modules.utility import rich_ui
from modules.allowance import referral as ref
from modules.search import delivery as dv
from modules.indexing import index_command as ic

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ((" -> " + str(extra)) if (extra and not cond) else ""))
    fails += (not cond)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------- user_db: first-start tracking
udb.init_user_db()
check("add_or_update_user_db: first call is_new=True", udb.add_or_update_user_db(11, "alice", "Alice A", "2026-11-01") is True)
check("add_or_update_user_db: second call is_new=False", udb.add_or_update_user_db(11, "alice", "Alice A", "2026-11-01") is False)
check("record_bot_start_db: first start True", udb.record_bot_start_db(11, "main", "mainbot") is True)
check("record_bot_start_db: repeat start False", udb.record_bot_start_db(11, "main", "mainbot") is False)
check("record_bot_start_db: other bot is separate", udb.record_bot_start_db(11, "helper:77", "helperbot") is True)
check("get_user_info_db", (udb.get_user_info_db(11) or {}).get("full_name") == "Alice A")
check("get_user_info_db unknown", udb.get_user_info_db(999) is None)

# existing users are seeded for the main bot on first creation of bot_starts (no mass "new user" logs after deploy)
import sqlite3
old = os.path.join(_TMP, "old.db")
c = sqlite3.connect(old)
c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, role TEXT DEFAULT 'Normal User', ban_status TEXT DEFAULT 'none', joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
c.execute("INSERT INTO users (user_id, username, full_name) VALUES (5, 'old', 'Old User')")
c.commit(); c.close()
os.environ["USERS_DB_PATH"] = old
udb.init_user_db()
check("backfill: pre-existing user is not 'new' on main bot", udb.record_bot_start_db(5, "main", "x") is False)
check("backfill: pre-existing user IS new on a helper bot", udb.record_bot_start_db(5, "helper:1", "h") is True)
os.environ["USERS_DB_PATH"] = os.path.join(_TMP, "users.db")

# ---------------------------------------------------------------- new-user log card
txt = sl.build_new_user_log_text(user_id=42, user_title="Bob <B>", username="bob_x", bot_title="George Orwell",
                                 bot_username="GeorgeOrwellAi", is_helper=False, referrer_id=11, referrer_title="Alice A")
check("log card: title", "New User Started the Bot" in txt)
check("log card: user profile link", '<a href="tg://user?id=42">Bob &lt;B&gt;</a>' in txt, txt)
check("log card: user id code", "<code>42</code>" in txt)
check("log card: username", "@bob_x" in txt)
check("log card: bot + kind", "@GeorgeOrwellAi" in txt and "Main Bot" in txt)
check("log card: referred by link + id", 'tg://user?id=11">Alice A</a> (<code>11</code>)' in txt, txt)
check("log card: IST stamp", re.search(r"\d{2} \w{3} \d{4}, \d{2}:\d{2} IST", txt) is not None)
check("log card: table", "<table striped>" in txt)
txt2 = sl.build_new_user_log_text(user_id=43, user_title="Cara", username=None, bot_title="Aurora", bot_username="Heyuqtbot", is_helper=True)
check("log card: helper kind, no referral row, no username", "Helper Bot" in txt2 and "Referred By" not in txt2 and "—" in txt2)


class FakeBot:
    def __init__(self, fail=0, uid=9185254121, uname="GeorgeOrwellAi"):
        self.sent, self.fail, self.id, self.username, self.first_name = [], fail, uid, uname, "George Orwell"

    async def send_message(self, **kw):
        if self.fail:
            self.fail -= 1
            from telegram.error import TelegramError
            raise TelegramError("topic closed")
        self.sent.append(kw)
        return SimpleNamespace(chat_id=kw["chat_id"], message_id=len(self.sent))


fb = FakeBot()
ok = run(sl.send_new_user_log([fb], txt))
check("send_new_user_log: goes to Logger Group USER topic", ok and fb.sent[0]["chat_id"] == -1004293995714 and fb.sent[0]["message_thread_id"] == 589, fb.sent)
fb2 = FakeBot(fail=1)
ok = run(sl.send_new_user_log([fb2], txt))
check("send_new_user_log: topic failure falls back to group (no admin PM)", ok and "message_thread_id" not in fb2.sent[0] and fb2.sent[0]["chat_id"] == -1004293995714)

user = SimpleNamespace(id=77, full_name="Dan D", username="dand")
fb3 = FakeBot()
ok = run(sl.log_new_user_start(fb3, user, is_helper=False, referrer_id=11))
check("log_new_user_start (main): sent once with referrer name from DB",
      ok and len(fb3.sent) == 1 and 'tg://user?id=11">Alice A</a>' in fb3.sent[0]["text"], fb3.sent)

# ---------------------------------------------------------------- referral: name fix + table
sent = []


class Ctx:
    class bot:
        @staticmethod
        async def send_message(**kw):
            sent.append(kw)


udb.add_or_update_user_db(100, "refr", "Referrer R", "2026-11-01")
ok, _ = run(ref.process_referral_with_notification(Ctx, 100, 200, "New Person"))
check("referral: success", ok)
rtxt = next(m["text"] for m in sent if m["chat_id"] == 100)
check("referral DM shows the new user's real name + profile link", 'tg://user?id=200">New Person</a>' in rtxt and "A user" not in rtxt, rtxt)

rows = [(200, "New <Person>", "newp", "2026-11-01 08:30:00"), (201, "", None, None)]
tbl = ref.build_referrals_table_html(rows)
check("referrals table: columns", all(h in tbl for h in ("<th>#</th>", "<th>User</th>", "<th>Username</th>", "<th>User ID</th>", "<th>Joined</th>")))
check("referrals table: profile link + escaped title", '<a href="tg://user?id=200">New &lt;Person&gt;</a>' in tbl)
check("referrals table: username, id", "@newp" in tbl and "<code>200</code>" in tbl)
check("referrals table: UTC -> IST (08:30 UTC = 14:00 IST)", "01 Nov 2026, 14:00 IST" in tbl, tbl)
check("referrals table: missing name/username/time handled", "User 201" in tbl and "—" in tbl)
t, m = ref.render_my_referrals(100, 1)
check("my referrals card has the table + buttons", "<table striped>" in t and isinstance(m, InlineKeyboardMarkup))
for i in range(300, 325):
    udb.add_or_update_user_db(i, f"u{i}", f"U {i}", "2026-11-01")
    udb.record_referral_db(100, i)
t2, m2 = ref.render_my_referrals(100, 2)
labels = [b.text for r in m2.inline_keyboard for b in r]
check("my referrals pagination (10 per page)", any("2/3" in l for l in labels) and any("Prev" in l for l in labels) and any("Next" in l for l in labels), labels)
check("referral module: duplicate refer_command removed", not hasattr(ref, "refer_command"))

# ---------------------------------------------------------------- rich_ui: <br> line breaks
src = "Title\n\nLine A\nLine B\n<pre>keep\nthis</pre>\n<code>a\nb</code>\n<table><tr><td>x\ny</td></tr></table>\nafter"
out = rich_ui.newlines_to_br(src)
check("<br>: newlines outside protected blocks", "Title<br><br>Line A<br>Line B" in out, out)
check("<br>: <pre>/<code>/<table> contents untouched", "keep\nthis" in out and "a\nb" in out and "x\ny" in out, out)
check("<br>: no run of 3+", "<br><br><br>" not in out)
html_out = rich_ui.build_rich_html("Hi\nthere", InlineKeyboardMarkup([[rich_ui.styled_button("Go", callback_data="x")]]))
check("build_rich_html: <br> + button row kept", html_out.startswith("Hi<br>there") and "<tg-button-row" in html_out, html_out)
check("build_rich_html: use_br=False keeps raw newline", rich_ui.build_rich_html("Hi\nthere", use_br=False) == "Hi\nthere")
clean, _ = rich_ui.extract_buttons_and_clean_html_for_fallback("a<br>b", small_caps=False)
check("plain fallback turns <br> back into newline", clean == "a\nb", clean)


class PostBot:
    def __init__(self, reject_br):
        self.calls, self.reject_br = [], reject_br

    async def _post(self, method, data=None):
        self.calls.append(data["rich_message"]["html"])
        if self.reject_br and "<br>" in data["rich_message"]["html"]:
            raise BadRequest("can't parse entities: unsupported tag br")
        return {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}}


pb = PostBot(reject_br=True)
run(rich_ui._post_rich(pb, "sendRichMessage", {"chat_id": 1}, "a\nb", None, False, False))
check("rich post: <br> rejected -> retried with raw newlines", len(pb.calls) == 2 and "<br>" in pb.calls[0] and pb.calls[1] == "a\nb", pb.calls)
check("rich post: <br> auto-disabled afterwards", rich_ui._BR_ENABLED is False)
pb2 = PostBot(reject_br=True)
run(rich_ui._post_rich(pb2, "sendRichMessage", {"chat_id": 1}, "c\nd", None, False, False))
check("rich post: later sends use raw newlines directly (1 call)", len(pb2.calls) == 1 and pb2.calls[0] == "c\nd", pb2.calls)
rich_ui._BR_ENABLED = True

# ---------------------------------------------------------------- delivery: PM-only cards, helper bots send none
check("_is_main_bot: main token id", dv._is_main_bot(SimpleNamespace(id=9185254121)) is True)
check("_is_main_bot: helper id", dv._is_main_bot(SimpleNamespace(id=8752800863)) is False)

ROW = lambda i, name: {"id": i, "file_name": name, "extension": ".epub", "file_size": 1_500_000, "caption": "", "category": "ebook",
                       "user_title": "Up Loader", "storage_message_id": 5, "file_id": "f", "file_unique_id": "u"}


class MainBot(FakeBot):
    pass


async def fake_select(bot, app=None):
    return {"token": "t", "id": 8752800863, "username": "Heyuqtbot", "first_name": "Aurora"}


async def fake_dual(update, context, row_id, *, send_card=True, helper=None):
    row = ROW(row_id, f"Book {row_id}.epub")
    pm = row_id != 3
    return {"ok": True, "row": row, "pm_delivered": pm, "posting_link": f"https://t.me/c/1/{row_id}",
            "helper_username": "Heyuqtbot", "delete_secs": 300, "delete_mins": 5, "error": None,
            "helper_start_url": f"https://t.me/Heyuqtbot?start=dl_{row_id}"}


dv.select_helper_bot, dv.deliver_file_dual = fake_select, fake_dual
mb = MainBot()
upd = SimpleNamespace(effective_user=SimpleNamespace(id=555), effective_chat=SimpleNamespace(type="supergroup"),
                      effective_message=SimpleNamespace(reply_text=None))
ctx = SimpleNamespace(bot=mb, application=SimpleNamespace(bot=mb))
summary = run(dv.deliver_batch_combined(upd, ctx, [ROW(1, "A.epub"), ROW(2, "B.epub"), ROW(3, "C.epub")]))
check("Send All: exactly ONE card sent", len(mb.sent) == 1, len(mb.sent))
check("Send All: card goes to the user's PM, not the topic", mb.sent[0]["chat_id"] == 555, mb.sent[0].get("chat_id"))
card = mb.sent[0]["text"]
check("Send All: one combined <table striped> with all rows", card.count("<table striped>") == 1 and card.count("<tr>") == 4, card)
check("Send All: per-file status + channel links", card.count("✅ PM") == 2 and "⏳ Start bot" in card and card.count(">View</a>") == 3, card)
check("Send All: start button for the pending helper", "Heyuqtbot?start=dl_3" in str(mb.sent[0]["reply_markup"].inline_keyboard[0][0].url))
check("Send All: summary counts", summary["delivered_pm"] == 2 and summary["failed"] == 0)

# single card text still has the table + PM wording
res = {"row": ROW(1, "Book 1.epub"), "helper_username": "Heyuqtbot", "posting_link": "https://t.me/c/1/1", "pm_delivered": True,
       "delete_mins": 5, "helper_start_url": "https://t.me/Heyuqtbot?start=dl_1"}
text, markup = dv._single_card(res)
check("single card: delivered wording + 2 buttons", "Delivered directly to your PM" in text and len(markup.inline_keyboard) == 2)

# ---------------------------------------------------------------- /index callbacks
rid = "ab12cd34"
for action in ("cancel", "apr", "rej", "sk_none", "sk_top", "sk_bot", "sk_custom", "pr_dir", "pr_hlp"):
    m = re.match(r"^idx_(.+)_([0-9a-f]{8})$", f"idx_{action}_{rid}")
    check(f"index callback parse idx_{action}_<rid>", bool(m) and m.group(1) == action and m.group(2) == rid)

job = {"rid": rid, "chat_id": -100123, "title": "Source <Chan>", "start_id": 1, "end_id": 50, "priority_mode": None,
       "requester_id": 9, "requester_name": "Admin A", "prompt_chat": -100123, "prompt_msg_id": 7, "state": "pending",
       "is_channel": True, "helper_token": "tok"}
ic._persist_job(job)
back = ic._load_job(rid)
check("index job persisted and restored after 'restart'", back and back["end_id"] == 50 and back["is_channel"] is True and back["helper_token"] == "tok" and back["cancel"] is False, back)
ic._forget_job(rid)
check("index job forgotten", ic._load_job(rid) is None)

print(f"\nFAILS: {fails}")
sys.exit(1 if fails else 0)
