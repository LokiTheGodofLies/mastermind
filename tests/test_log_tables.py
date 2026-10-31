"""Offline tests: index log, restart card and 'Verified & Indexed' reply as rich tables (build 20261031-1758)."""
import asyncio, os, re, sys
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from modules.indexing import book_index as bi
from modules.log import startup_log as sl
from modules.utility import rich_ui

fails = 0
def check(n, c, x=""):
    global fails
    print(("PASS " if c else "FAIL ") + n + ((" -> " + x) if (x and not c) else "")); fails += (not c)

msg = bi.format_index_log_message("3 The Dragon's Choice - Roxie Ray.m4b", "319.82 MB", "AgAD-SAAAtcToVI",
    "https://t.me/c/3511375054/1087", 5, "Loki <&> Co", "✅ Added to files.db", "✅ Added to Storage Group (Msg #1087)",
    "✅ Enriched via Goodreads (Bluewater Dragons (Book #3))", indexed_by_bot="@Heyuqtbot")
check("index log: one table", msg.count("<table") == 1 and "<th>Field</th>" in msg, msg)
for lab in ("File Name", "File Size", "Unique ID", "Storage Link", "Sent By", "Indexed By", "Database Presence", "Storage Group Presence", "Caption Enrichment", "Timestamp"):
    check("index log row " + lab, f"<i>{lab}</i>" in msg, msg)
check("index log: stage order 1,2,3", msg.index("1. 🗄") < msg.index("2. 📦") < msg.index("3. 📝"))
check("index log: escaped user", "Loki &lt;&amp;&gt; Co" in msg and "<&>" not in msg)
check("index log: button kept", '<tg-button type="url"' in msg and "Open in Storage Group" in msg)
c, mk = rich_ui.extract_buttons_and_clean_html_for_fallback(msg, None)
check("index log fallback: pre + button", "<pre>" in c and "<table" not in c and mk is not None)

class FakeBot:
    id = 9; username = "GeorgeOrwellAi"; first_name = "George Orwell"
    async def get_me(self): return self
    async def get_chat(self, cid):
        if cid == -3: raise RuntimeError("nope")
        return SimpleNamespace(id=cid, type="supergroup", title=f"Chat {cid}", username=None, invite_link="https://t.me/+abc")
    async def get_chat_member(self, cid, uid): return SimpleNamespace(status="administrator")
    async def export_chat_invite_link(self, cid): return "https://t.me/+x"

async def run():
    sl.CHAT_SLOTS[:] = [("Storage", "STORAGE_GROUP_ID", "Storage group"), ("Posting", "POSTING_CHANNEL_ID", "Posting")]
    vals = {"STORAGE_GROUP_ID": "-100", "POSTING_CHANNEL_ID": "-3"}
    sl._cfg = lambda env: vals.get(env, "7")
    async def no_helpers(): return []
    sl._helper_bots = no_helpers
    problems = []
    text = await sl.build_startup_text(SimpleNamespace(bot=FakeBot()), problems)
    check("restart card: tables", text.count("<table") >= 3, text)
    check("restart card: status table fields", all(f"<i>{x}</i>" in text for x in ("Environment", "Main Bot", "Database", "Timestamp")))
    check("restart card: invite link in cell", '<a href="https://t.me/+abc">Invite Link</a>' in text)
    check("restart card: failing chat flagged + problem recorded", "Not accessible" in text and len(problems) == 1, str(problems))
    check("restart card: topics table", "<th>Topic</th>" in text)
    c, _ = rich_ui.extract_buttons_and_clean_html_for_fallback(text, None)
    check("restart card fallback fits 4096", "<table" not in c and len(re.sub(r"<[^>]+>", "", c)) <= 4096, str(len(c)))
asyncio.run(run())
print("\nFAILS:", fails); sys.exit(1 if fails else 0)
