"""Offline tests for the search-result tables (build 20261031-1745).

Run:  python tests/test_search_table.py      (needs python-telegram-bot, like the other test)
"""
import asyncio, sys, os, re
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("PUBLIC_STORAGE_GROUP_ID", "-100999")
os.environ.setdefault("TESTING_STORAGE_GROUP_ID", "-100999")

from modules.utility import rich_ui
from modules.utility import small_caps as sc
from modules.search import handlers as sh

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + extra) if (extra and not cond) else ""))
    fails += (not cond)


# ---- 1) table builder -------------------------------------------------------------------
tbl = sh.build_result_table_html(3, 'Dragon <Rider> & "Co"', "A. Author", "Series X (Book #2)", "2.61 MB", "Ebook", "epub")
check("table wrapper", tbl.startswith("<table>") and tbl.endswith("</table>"))
for label in ("No.", "Title", "Author", "Series", "Size", "Format", "Ext"):
    check(f"label {label}", f"<b>{label}</b>" in tbl)
check("7 rows", tbl.count("<tr>") == 7)
check("values escaped", "Dragon &lt;Rider&gt; &amp; &quot;Co&quot;" in tbl and "<Rider>" not in tbl, tbl)
check("ext dot", "<td>.epub</td>" in tbl)
check("no ext -> dash", "<td>-</td>" in sh.build_result_table_html(1, "t", "a", "s", "1 KB", "Ebook", ""))

# ---- 2) plain-HTML fallback -------------------------------------------------------------
pre = rich_ui.tables_to_pre(tbl)
check("fallback has pre, no table", "<pre>" in pre and "<table" not in pre and "<tr" not in pre, pre)
check("fallback keeps all fields", all(x in pre for x in ("No.", "Title", "Author", "Series", "Size", "Format", "Ext")), pre)
check("fallback escaped", "&lt;Rider&gt; &amp;" in pre and "<Rider>" not in pre, pre)
long_tbl = sh.build_result_table_html(1, "T" * 200, "a", "s", "1 KB", "Ebook", "epub")
check("long cell cut", ("T" * 44) not in rich_ui.tables_to_pre(long_tbl) and "…" in rich_ui.tables_to_pre(long_tbl))
check("3-col table joined", "a | b | c" in rich_ui.tables_to_pre("<table><tr><td>a</td><td>b</td><td>c</td></tr></table>"))
check("empty table gone", rich_ui.tables_to_pre("x<table></table>y") == "xy")

rich = tbl + "\n" + rich_ui.tg_button_row_html([
    rich_ui.tg_button_html("📥 Download #3", callback_data="file_dl_77", style="success"),
    rich_ui.tg_button_html("⚡ Direct Link", url="https://t.me/Bot?start=dl_77", style="primary"),
], align="left")
clean, markup = rich_ui.extract_buttons_and_clean_html_for_fallback(rich, None)
check("fallback: no table tag left", "<table" not in clean and "<pre>" in clean, clean)
check("fallback: monospace shows plain letters", "Dragon" in clean and sc.to_small_caps("Dragon") not in clean, clean)
cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
urls = [b.url for row in markup.inline_keyboard for b in row]
check("fallback: download callback unchanged", "file_dl_77" in cbs, str(cbs))
check("fallback: direct link unchanged", "https://t.me/Bot?start=dl_77" in urls, str(urls))

# message too long -> cells shortened until it fits
many = "\n".join(sh.build_result_table_html(i, "Title " * 12, "Author " * 8, "Series " * 8, "9 MB", "Ebook", "epub") for i in range(1, 11))
clean_long, _ = rich_ui.extract_buttons_and_clean_html_for_fallback(many, None)
check("fallback length fits Telegram", len(re.sub(r"<[^>]+>", "", clean_long)) <= 4096, str(len(clean_long)))

# ---- 3) URL safety for in-text buttons --------------------------------------------------
share = "https://t.me/share/url?url=https://t.me/Bot?start=ref_5&text=try this amazing bot and let's earn !"
btn = rich_ui.tg_button_html("📤 Refer", url=share, style="success")
m = re.search(r'url="([^"]*)"', btn)
check("share url: no space/apostrophe in attribute", m and " " not in m.group(1) and "'" not in m.group(1) and "&#x27;" not in m.group(1), btn)
check("share url: still decodes to same words", m and "try%20this%20amazing" in m.group(1), btn)
plain = rich_ui.tg_button_html("⚡ Direct Link", url="https://t.me/Bot?start=dl_12", style="primary")
check("normal link unchanged", 'url="https://t.me/Bot?start=dl_12"' in plain, plain)
check("already-encoded kept", "%20" in rich_ui.tg_button_html("x", url="https://a.b/c%20d") and "%2520" not in rich_ui.tg_button_html("x", url="https://a.b/c%20d"))

# ---- 4) full perform_search with a fake DB ----------------------------------------------
ROWS = []
for i in range(1, 13):
    ROWS.append({
        "id": 100 + i, "file_name": f"Dragon Book {i}.epub" if i != 2 else "Dragon Tales.mp3",
        "caption": f"📖 Title: Dragon Book {i}\n📚 Series: Standalone\n✍️ Author: Writer {i}",
        "extension": "epub" if i != 2 else "mp3", "file_size": 2_740_000 + i,
        "category": "ebook" if i != 2 else "audiobook", "user_title": "uploader",
    })
sh.search_files_db = lambda q: list(ROWS)
sh.can_user_search = lambda uid: True
sh.deduct_search_quota = lambda uid: None


class FakeMsg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append((text, kw))


async def run():
    msg = FakeMsg()
    upd = SimpleNamespace(
        effective_user=SimpleNamespace(id=1), effective_message=msg, callback_query=None,
        effective_chat=SimpleNamespace(type="private"),
    )
    ctx = SimpleNamespace(bot=SimpleNamespace(username="GeorgeOrwellAi", first_name="George Orwell"))
    await sh.perform_search(upd, ctx, "dragon", 1, "all")
    text, kw = msg.sent[0]
    check("10 tables on page 1", text.count("<table>") == 10, str(text.count("<table>")))
    check("10 download rows", text.count("<tg-button-row") >= 10)
    # each table is followed by its own button row (table -> row -> next table)
    seq = re.findall(r"</table>\s*(<tg-button-row[^>]*>.*?</tg-button-row>)", text, re.DOTALL)
    check("button row directly below every table", len(seq) == 10, str(len(seq)))
    for n, row in enumerate(seq, start=1):
        rid = 100 + n
        ok = (f'data="file_dl_{rid}"' in row and f"?start=dl_{rid}" in row and f"Download #{n}" in row)
        check(f"download #{n} -> file_dl_{rid} + deep link", ok, row)
    check("audiobook labelled", "<td>Audiobook</td>" in text and text.count("<td>Ebook</td>") == 9)
    check("size shown", "<td>2.61 MB</td>" in text)
    check("series shown", "<td>Standalone</td>" in text)
    check("old <code>/mark per-line layout gone", "✍️ <code>" not in text)
    check("pagination/filter callbacks kept", all(x in kw["reply_markup"].to_json() for x in ("sp_all_2_dragon", "sf_ebook_1_dragon", "sa_all_1_dragon", "sf_audio_1_dragon")))
    await sh.perform_search(upd, ctx, "dragon", 2, "all")
    t2 = msg.sent[1][0]
    check("page 2 has 2 tables, numbering continues", t2.count("<table>") == 2 and "<td>11</td>" in t2 and "<td>12</td>" in t2)
    check("page 2 download ids", 'file_dl_111' in t2 and 'file_dl_112' in t2)


asyncio.run(run())
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
