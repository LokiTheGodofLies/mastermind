"""Offline tests: index audit/channel cards + routing, restart card and 'Verified & Indexed' reply tables (build 20261031-1830)."""
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

# ---- Index logs: audit card (topic) + curated card (channel) + routing (build 20261031-1830) ----
INFO_AUDIO = {"file_name": "3 The Dragon's Choice - Roxie Ray.m4b", "file_unique_id": "AgAD-SAAAtcToVI", "extension": ".m4b",
              "duration": 51730, "raw_caption": "Roxie Ray - Dragon <final> release", "file_size": 335_000_000}
INFO_EBOOK = dict(INFO_AUDIO, file_name="The Final Empire.epub", extension=".epub", duration=0)
CAP = ("📚 <b>Book:</b> <a href=\"https://x.test/b\">The Final Empire</a>\n✍️ <b>Author:</b> <code>Brandon Sanderson</code>\n"
       "📚 <b>Series:</b> <code>Mistborn (Book #1)</code>\n\n📁 <b>File:</b> <code>The Final Empire.epub</code>\n"
       "📦 <b>Size:</b> <code>1.45 MB</code> | <b>Type:</b> <code>.epub</code>")
def res(ok=True, status="indexed"):
    return {"status": status, "is_success_enrichment": ok, "file_size_str": "1.45 MB", "storage_link": "https://t.me/c/3511375054/1087",
            "db_badge": "✅ Added to files.db", "storage_badge": "✅ Added to Storage Group (Msg #1087)",
            "caption_badge": "✅ Enriched via Goodreads (Mistborn (Book #1))" if ok else "🚧 Info Not Found (Reported to Error Logs)",
            "caption_html": CAP if ok else "📚 <b>Book:</b> \n✍️ <b>Author:</b> "}

check("duration: audio full h m s", bi.duration_for_log(INFO_AUDIO) == "14h 22m 10s", bi.duration_for_log(INFO_AUDIO))
check("duration: ebook skipped", bi.duration_for_log(INFO_EBOOK) == "")
check("duration: audio w/o duration skipped", bi.duration_for_log(dict(INFO_AUDIO, duration=0)) == "")

audit = bi.format_index_audit_card("The Final Empire.epub", "1.45 MB", ".epub", "AQADAgADxqc", "https://t.me/c/3511375054/1087", 123, "Loki <&> Co",
    "✅ Added to files.db", "✅ Added to Storage Group (Msg #1087)", "✅ Enriched via Goodreads", True,
    source_info='<a href="https://t.me/c/442/9">Fantasy Archive</a> (<code>-100442</code>) | Msg <code>#95</code>',
    indexed_by_bot="@Heyuqtbot", original_caption="Brandon Sanderson - Mistborn <b>Book 1</b>", enriched_caption_html=CAP)
check("audit: header", audit.startswith("📄 <b>FILE INDEXED AUDIT</b>"))
check("audit: user title embedded link + id", '<a href="tg://user?id=123">Loki &lt;&amp;&gt; Co</a> (<code>123</code>)' in audit, audit)
check("audit: source with msg id", "Fantasy Archive" in audit and "Msg <code>#95</code>" in audit)
check("audit: storage embedded link (no raw url text)", '<a href="https://t.me/c/3511375054/1087">View in Storage Group</a>' in audit)
check("audit: details", all(x in audit for x in ("File Name", "File Size", "Extension", "File Unique ID")) and "Duration" not in audit)
check("audit: ticks in order", audit.index("1. 🗄") < audit.index("2. 📦") < audit.index("3. 📝"))
check("audit: original caption escaped in blockquote", "<blockquote>Brandon Sanderson - Mistborn &lt;b&gt;Book 1&lt;/b&gt;</blockquote>" in audit)
check("audit: enriched caption block", "✨ <b>Enriched Caption</b>" in audit and "Brandon Sanderson" in audit)
check("audit: no failure note on success", "Caption enrichment failed" not in audit)
fail_audit = bi.format_index_audit_card("x.epub", "1 MB", ".epub", "U", "https://t.me/c/1/2", 5, "A", "d", "s", "c", False, enriched_caption_html=CAP)
check("audit: failure note, no enriched block", "Caption enrichment failed for this item" in fail_audit and "Enriched Caption" not in fail_audit)
check("audit: duration row for media", "Duration</b>: 14h 22m 10s" in bi.format_index_audit_card("a.m4b", "1 MB", ".m4b", "U", "", 0, "A", "d", "s", "c", True, duration_str="14h 22m 10s"))

card = bi.format_index_channel_card("The Final Empire.epub", "1.45 MB", ".epub", "AQADAgADxqc", CAP)
check("channel card: header + fields", card.startswith("📚 <b>New file added to library</b>") and all(x in card for x in ("File Name:", "File Size:", "Extension:", "File Unique ID:")))
check("channel card: no duration for ebook", "Duration" not in card)
check("channel card: enriched caption kept, file/size lines not duplicated", "Brandon Sanderson" in card and "📁 <b>File:</b>" not in card and "📦 <b>Size:</b>" not in card)
check("channel card: no audit-only fields", all(x not in card for x in ("Added By", "Timestamp", "Storage", "Original Caption", "Database")))
check("channel card: duration for media", "Duration:</b> 14h 22m 10s" in bi.format_index_channel_card("a.m4b", "1 MB", ".m4b", "U", CAP, "14h 22m 10s"))
check("channel card: archive header 📦 line survives", "📦 <b>Book / Audiobook:</b>" in bi.format_index_channel_card("a.zip", "1 MB", ".zip", "U", "📦 <b>Book / Audiobook:</b> X\n\n📁 <b>File:</b> <code>a</code>\n📦 <b>Size:</b> <code>1</code>"))

class Sink:
    username = "Heyuqtbot"
    def __init__(self): self.sent = []
    async def send_message(self, **kw): self.sent.append(kw)
bi.index_channel_id = lambda: "-1004343321416"
bi.logger_group_id = lambda: "-1004293995714"
bi.log_topic = lambda name: 590 if name == "INDEX" else None
async def routing():
    for label, ok, status, want_chan in (("enriched", True, "indexed", 1), ("failed", False, "indexed", 0), ("duplicate", True, "duplicate", 0)):
        b = Sink()
        await bi.send_index_file_logs(b, info=INFO_AUDIO, res=res(ok, status), user_id=7, user_title="U", indexed_by_bot="@x", original_caption="o")
        topic = [m for m in b.sent if m["chat_id"] == -1004293995714]
        chan = [m for m in b.sent if m["chat_id"] == -1004343321416]
        check(f"routing {label}: topic gets audit card (thread 590)", len(topic) == 1 and topic[0].get("message_thread_id") == 590 and "FILE INDEXED AUDIT" in topic[0]["text"])
        check(f"routing {label}: channel cards = {want_chan}", len(chan) == want_chan and (not want_chan or ("New file added to library" in chan[0]["text"] and "message_thread_id" not in chan[0] and "Duration:</b> 14h 22m 10s" in chan[0]["text"])))
    b = Sink()
    await bi.send_index_topic_log(b, "lifecycle")
    check("lifecycle/topic-only sender never hits channel", [m["chat_id"] for m in b.sent] == [-1004293995714])
    class Boom(Sink):
        async def send_message(self, **kw): raise RuntimeError("x")
    bad, good = Boom(), Sink()
    await bi.send_index_channel_log(bad, "t", fallback_bot=good)
    check("channel send falls back to second bot", len(good.sent) == 1 and good.sent[0]["chat_id"] == -1004343321416)
    fwd = SimpleNamespace(forward_origin=SimpleNamespace(chat=SimpleNamespace(id=-100442, title="Fantasy <Archive>", username=None), message_id=95), chat=SimpleNamespace(type="private", id=5), message_id=1)
    src = bi.source_info_from_message(fwd)
    check("source: forwarded channel linked + id + msg", 'href="https://t.me/c/442/95"' in src and "Fantasy &lt;Archive&gt;" in src and "<code>-100442</code>" in src and "Msg <code>#95</code>" in src, src)
    check("source: plain DM upload", bi.source_info_from_message(SimpleNamespace(chat=SimpleNamespace(type="private", id=5), message_id=3)).startswith("Direct upload"))
asyncio.run(routing())

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
