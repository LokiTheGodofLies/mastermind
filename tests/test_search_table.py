"""Offline tests for the search-result tables (build 20261031-1737).

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


# ---- 1) table builder (ONE table per page, download link in column 1) ------------------
def item(i, title="t", author="a", series="s", size="1 KB", kind="Ebook", ext="epub"):
    return (i, 100 + i, title, author, series, size, kind, ext, f"https://t.me/Bot?start=dl_{100 + i}")


tbl = sh.build_results_table_html([item(3, 'Dragon <Rider> & "Co"', "A. Author", "Series X (Book #2)", "2.61 MB")])
check("table wrapper", tbl.startswith("<table") and tbl.endswith("</table>"))
head = re.search(r"<tr>(.*?)</tr>", tbl).group(1)
check("header row", re.findall(r"<th>(.*?)</th>", head) == ["No.", "Title", "Author", "Series", "Size", "Format", "Ext"], head)
check("header + 1 body row", tbl.count("<tr>") == 2)
check("values escaped", "Dragon &lt;Rider&gt; &amp; \"Co\"" in tbl and "<Rider>" not in tbl, tbl)
check("ext dot", "<td>.epub</td>" in tbl)
check("first column = plain serial number", "<td>3</td>" in tbl and "<a " not in tbl, tbl)
check("no ext -> dash", "<td>-</td>" in sh.build_results_table_html([item(1, ext="")]))
two = sh.build_results_table_html([item(1), item(2)])
check("many books = one table, one row each", two.count("<table") == 1 and two.count("<tr>") == 3)

# ---- 2) plain-HTML fallback -------------------------------------------------------------
pre = rich_ui.tables_to_pre(tbl)
check("fallback has pre, no table", "<pre>" in pre and "<table" not in pre and "<tr" not in pre, pre)
check("fallback keeps all columns", all(x in pre for x in ("No.", "Title", "Author", "Series", "Size", "Format", "Ext")), pre)
check("fallback escaped", "&lt;Rider&gt; &amp;" in pre and "<Rider>" not in pre, pre)
long_tbl = sh.build_results_table_html([item(1, "T" * 200)])
check("long cell cut", ("T" * 44) not in rich_ui.tables_to_pre(long_tbl) and "…" in rich_ui.tables_to_pre(long_tbl))
check("3-col table joined", "a | b | c" in rich_ui.tables_to_pre("<table><tr><td>a</td><td>b</td><td>c</td></tr></table>"))
check("empty table gone", rich_ui.tables_to_pre("x<table></table>y") == "xy")

rich_two = two + "\n" + rich_ui.tg_button_row_html([rich_ui.tg_button_html("Download 1", callback_data="file_dl_101", style="success"), rich_ui.tg_button_html("Download 2", callback_data="file_dl_102", style="success")])
clean, markup = rich_ui.extract_buttons_and_clean_html_for_fallback(rich_two, None)
check("fallback: no table tag left", "<table" not in clean and "<pre>" in clean, clean)
check("fallback: monospace shows plain letters", sc.to_small_caps("Dragon") not in clean, clean)
cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
check("fallback: Download buttons -> file_dl_<id>", cbs == ["file_dl_101", "file_dl_102"], str(cbs))

many_items = [item(i, "Title " * 12, "Author " * 8, "Series " * 8, "9 MB") for i in range(1, 12)]
# message too long -> cells shortened until it fits
clean_long, _ = rich_ui.extract_buttons_and_clean_html_for_fallback(sh.build_results_table_html(many_items[:10]), None)
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
    check("ONE table on page 1", text.count("<table") == 1, str(text.count("<table")))
    check("header + 10 rows", text.count("<tr>") == 11, str(text.count("<tr>")))
    rows_btn = re.findall(r"<tg-button-row[^>]*>.*?</tg-button-row>", text, re.DOTALL)
    check("5 button rows, 2 Download buttons each", len(rows_btn) == 5 and all(r.count("<tg-button ") == 2 for r in rows_btn), str(len(rows_btn)))
    for n in range(1, 11):
        rid = 100 + n
        check(f"Download {n} -> file_dl_{rid}", f'data="file_dl_{rid}"' in text and f">Download {n}</tg-button>" in text)
    check("serial in first column", all(f"<td>{n}</td>" in text for n in range(1, 11)))
    check("audiobook labelled", "<td>Audiobook</td>" in text and text.count("<td>Ebook</td>") == 9)
    check("size shown", "<td>2.61 MB</td>" in text)
    check("series shown", "<td>Standalone</td>" in text)
    check("pagination/filter callbacks kept", all(x in kw["reply_markup"].to_json() for x in ("sp_all_2_dragon", "sf_ebook_1_dragon", "sa_all_1_dragon", "sf_audio_1_dragon")))
    await sh.perform_search(upd, ctx, "dragon", 2, "all")
    t2 = msg.sent[1][0]
    check("page 2: one table, 2 rows, numbering continues", t2.count("<table") == 1 and t2.count("<tr>") == 3 and "<td>11</td>" in t2 and "<td>12</td>" in t2)
    check("page 2 download ids", "file_dl_111" in t2 and "file_dl_112" in t2)


asyncio.run(run())

# ---- 5) captions (Storage Group) and delivery card, Mira style --------------------------
from modules.indexing import book_index as bi
from modules.search import delivery as dv
meta = {"is_matched": True, "title": "Pride and Prejudice", "url": "https://goodreads.com/book/1", "author": "Jane Austen",
        "series": "Jane Austen Tea Society Mystery", "published": "1813", "narrator": "Someone", "length": "11 hrs"}
cap = bi.format_index_channel_caption("Pride and Prejudice - Jane Austen.m4b", "316.80 MB", ".m4b", "audio/mp4", meta, "audiobook")
L = cap.split("\n")
check("caption: title line first", L[0].startswith("🎧 <b>Audiobook:</b> <a href"), cap)
check("caption: By before Series", L[1].startswith("✍️ <b>By:</b> <code>Jane Austen") and L[2].startswith("📚 <b>Series:</b>"), cap)
check("caption: Release Date own line", "📅 <b>Release Date:</b> <code>1813</code>" in L, cap)
check("caption: File line", "📁 <b>File:</b> <code>Pride and Prejudice - Jane Austen.m4b</code>" in L, cap)
check("caption: Size | Type .ext (no mime)", L[-1] == "📦 <b>Size:</b> <code>316.80 MB</code> | <b>Type:</b> <code>.m4b</code>", cap)
check("caption: blank line before File", L[-3] == "", cap)
check("caption: no 'File Name' / mime left", "File Name" not in cap and "audio/mp4" not in cap)
ebook_cap = bi.format_index_channel_caption("x.epub", "2.05 MB", "epub", "application/epub+zip", dict(meta, narrator="", length=""), "ebook")
check("ebook caption uses Book / Author", ebook_cap.startswith("📚 <b>Book:</b>") and "<b>Author:</b>" in ebook_cap and "Type:</b> <code>.epub</code>" in ebook_cap, ebook_cap)
empty = bi.format_index_channel_caption("x.epub", "2.05 MB", "epub", "application/epub+zip", {"is_matched": False}, "ebook")
check("unmatched caption: empty Book/Author/Series, File, Size", empty.split("\n")[:3] == ["📚 <b>Book:</b> ", "✍️ <b>Author:</b> ", "📚 <b>Series:</b> "] and "<b>File:</b>" in empty, empty)
# parsers must still read the new layout, and empty lines must not leak into the next line
pm = bi._parse_caption_meta(re.sub(r"<[^>]+>", "", cap))
check("parser: title/author/series/date", pm.get("book_title") == "Pride and Prejudice" and pm.get("book_author") == "Jane Austen" and pm.get("book_published") == "1813" and "Tea Society" in pm.get("book_series", ""), str(pm))
pe = bi._parse_caption_meta(re.sub(r"<[^>]+>", "", empty))
check("parser: empty placeholders give no author/title", not pe.get("book_author") and not pe.get("book_title"), str(pe))
card = dv.build_file_info_html({"caption": cap, "file_name": "Pride and Prejudice - Jane Austen.m4b", "file_size": 332197000, "extension": ".m4b",
                                "category": "audiobook"})
check("delivery card: Field|Value table", card.startswith("<table><tr><th>Field</th><th>Value</th></tr>") and card.endswith("</table>"), card)
for lab in ("Audiobook", "By", "Series", "Release Date", "File", "Size", "Type"):
    check(f"card row {lab}", f"<i>{lab}</i>" in card, card)
check("card values monospace", "<code>Jane Austen</code>" in card and "<code>.m4b</code>" in card and "<code>1813</code>" in card, card)
bare = dv.build_file_info_html({"caption": "", "file_name": "a.epub", "file_size": 2_100_000, "extension": "epub", "category": "ebook"})
check("card: unenriched file shows only File/Size/Type", bare.count("<tr>") == 4 and "<i>Author</i>" not in bare, bare)
pre = rich_ui.tables_to_pre(card)
check("card fallback is a clean monospace block", "<pre>" in pre and "Field" in pre and "<table" not in pre, pre)
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
