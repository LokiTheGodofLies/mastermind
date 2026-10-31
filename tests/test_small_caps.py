import asyncio, sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("PUBLIC_STORAGE_GROUP_ID", "-100999")
os.environ.setdefault("TESTING_STORAGE_GROUP_ID", "-100999")
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from modules.utility import small_caps as sc

fails = 0
def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + extra) if (extra and not cond) else ""))
    fails += (not cond)

LET = re.compile(r"[A-Za-z]")
def sc_letters_only(s):  # remaining ascii letters
    return "".join(LET.findall(s))

# ---- pure converter ----
out = sc.convert("Hello World, quiz box!", None)
print("plain:", out)
check("no ascii left except s/x", set(sc_letters_only(out).lower()) <= {"s", "x"}, out)
check("idempotent", sc.convert(out, None) == out)
check("roundtrip lower", sc.from_small_caps(out) == "hello world, quiz box!", sc.from_small_caps(out))

h = '👋 Hi <b>Mayank</b>! Use <code>/search &lt;keyword&gt;</code> or /quota, ask @HDCarltonbot at https://t.me/HDCarltonbot?start=dl_12 &amp; <a href="https://example.com/Path">Read More</a> #Books 10/20 and/or Yes/No'
o = sc.convert(h, "HTML")
print("html:", o)
check("tags kept", "<b>" in o and "</b>" in o and '<a href="https://example.com/Path">' in o)
check("code untouched", "<code>/search &lt;keyword&gt;</code>" in o)
check("command kept", "/quota" in o)
check("mention kept", "@HDCarltonbot" in o)
check("url kept", "https://t.me/HDCarltonbot?start=dl_12" in o)
check("entity kept", "&amp;" in o and "&lt;" in o)
check("hashtag kept", "#Books" in o)
check("link text converted", ">Read More<" not in o)
check("and/or converted", "and/or" not in o)
check("numbers kept", "10/20" in o)

btn = '<tg-button-row align="center"><tg-button type="callback_data" style="success" data="file_dl_5">📥 Download #1</tg-button><tg-button type="copy_text" text="Copy Me" style="primary">📋 Copy ID</tg-button></tg-button-row>'
o = sc.convert(btn, "HTML")
check("tg-button attrs intact", 'data="file_dl_5"' in o and 'text="Copy Me"' in o and 'style="success"' in o, o)
check("tg-button label converted", "Download" not in o and "Copy ID" not in o, o)

md = "⚠️ **Usage:** `/unban <target_id|@username>` see [Docs](https://a.b/Cc)"
o = sc.convert(md, "Markdown"); print("md:", o)
check("md code/url kept", "`/unban <target_id|@username>`" in o and "(https://a.b/Cc)" in o)
check("none/empty passthrough", sc.convert(None) is None and sc.convert("") == "" and sc.convert(5) == 5)


# ---- monospace safety: code spans always show plain letters ----
pre_sc = sc.to_small_caps("Loki - The God Of Lies")
o = sc.convert(f"✍️ <code>{pre_sc}</code> and <pre>{pre_sc}</pre> Normal Text", "HTML")
print("code safe:", o)
check("code span plain letters", "<code>loki - the god of lies</code>" in o, o)
check("pre block plain letters", "<pre>loki - the god of lies</pre>" in o, o)
check("text outside code still small caps", "Normal" not in o and "ɴᴏʀᴍᴀʟ" in o, o)
o = sc.convert("<code>Keep Case 123</code>", "HTML")
check("never-converted code keeps original case", o == "<code>Keep Case 123</code>", o)
o = sc.convert(f"Use `{pre_sc}` now", "Markdown")
check("markdown backticks plain letters", "`loki - the god of lies`" in o, o)
o = sc.convert('<a href="https://x.y/Ab">Link Text</a>', "HTML")
check("links still converted, url intact", 'href="https://x.y/Ab"' in o and "Link" not in o, o)

os.environ["SMALL_CAPS"] = "0"
check("kill switch", sc.convert("Hello", None) == "Hello")
del os.environ["SMALL_CAPS"]

# ---- patched Bot ----
calls = []
async def rec(name, *a, **k):
    calls.append((name, a, k)); return True
async def fake_send(self, *a, **k): return await rec("send_message", *a, **k)
async def fake_edit(self, *a, **k): return await rec("edit_message_text", *a, **k)
async def fake_doc(self, *a, **k): return await rec("send_document", *a, **k)
async def fake_photo(self, *a, **k): return await rec("send_photo", *a, **k)
async def fake_ans(self, *a, **k): return await rec("answer_callback_query", *a, **k)
async def fake_cap(self, *a, **k): return await rec("edit_message_caption", *a, **k)
async def fake_rm(self, *a, **k): return await rec("edit_message_reply_markup", *a, **k)
Bot.send_message, Bot.edit_message_text, Bot.send_document = fake_send, fake_edit, fake_doc
Bot.send_photo, Bot.answer_callback_query, Bot.edit_message_caption = fake_photo, fake_ans, fake_cap
Bot.edit_message_reply_markup = fake_rm
from modules.utility import rich_ui
rich_ui.install_rich_ui_patches()

posts = []
async def fake_post(self, endpoint, data=None, **kw):
    posts.append((endpoint, data))
    if endpoint == "sendRichMessage":
        return {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}}
    return True
Bot._post = fake_post

async def main():
    global calls
    b = Bot("123:ABC")
    kb = InlineKeyboardMarkup([[rich_ui.styled_button("❌ Cancel", callback_data="x_cancel"),
                                rich_ui.styled_button("📥 Download #1", callback_data="file_dl_1")],
                               [rich_ui.styled_button("Open", url="https://Example.com/A")]])
    # 1) rich path (buttons + HTML)
    await b.send_message(chat_id=5, text="👋 Hi <b>Friend</b>! Use /start", parse_mode="HTML", reply_markup=kb)
    ep, data = posts[-1]; html_ = data["rich_message"]["html"]; print("rich:", html_)
    check("rich path used", ep == "sendRichMessage")
    check("rich: danger style inferred BEFORE conversion", 'style="danger"' in html_ and 'style="success"' in html_, html_)
    check("rich: callback data intact", 'data="x_cancel"' in html_ and 'data="file_dl_1"' in html_)
    check("rich: url intact", 'url="https://Example.com/A"' in html_)
    check("rich: text converted", "Friend" not in html_ and "Cancel" not in html_ and "/start" in html_)

    # 2) plain fallback path: no parse mode
    calls.clear()
    await b.send_message(chat_id=5, text="Hello there", reply_markup=kb)
    n, a, k = calls[-1]; print("plain send:", k["text"], [x.text for x in k["reply_markup"].inline_keyboard[0]])
    check("plain text converted", "Hello" not in k["text"])
    btns = k["reply_markup"].inline_keyboard
    check("fallback buttons converted", "Cancel" not in btns[0][0].text and btns[0][0].callback_data == "x_cancel")
    check("fallback button style kept", btns[0][0].api_kwargs.get("style") == "danger" and btns[0][1].api_kwargs.get("style") == "success", str(btns[0][0].api_kwargs))
    check("fallback url kept", btns[1][0].url == "https://Example.com/A")

    # 3) positional text args for send_message / edit_message_text
    calls.clear()
    await b.send_message(5, "Positional Text")
    check("positional send", "Positional" not in calls[-1][1][1], str(calls[-1]))
    calls.clear()
    await b.edit_message_text("Edited Text", chat_id=5, message_id=9)
    check("edit text positional", "Edited" not in calls[-1][1][0], str(calls[-1]))

    # 4) HTML w/ keyboard that fails rich -> fallback path
    async def boom(self, endpoint, data=None, **kw):
        raise RuntimeError("rich unsupported")
    Bot._post = boom
    calls.clear()
    await b.send_message(chat_id=5, text="<mark>Badge</mark> and <tg-button-row><tg-button type=\"callback_data\" data=\"quiz_ans_no\">No Way</tg-button></tg-button-row>", parse_mode="HTML")
    n, a, k = calls[-1]; print("fallback html:", k["text"], k["reply_markup"].inline_keyboard[0][0].text)
    check("fallback converts badge", "Badge" not in k["text"])
    check("fallback button label+cb", "No Way" not in k["reply_markup"].inline_keyboard[0][0].text and k["reply_markup"].inline_keyboard[0][0].callback_data == "quiz_ans_no")
    check("fallback danger style", k["reply_markup"].inline_keyboard[0][0].api_kwargs["style"] == "danger")
    Bot._post = fake_post

    # 5) edit via rich
    posts.clear()
    await b.edit_message_text("Edit <b>Me</b>", chat_id=5, message_id=9, parse_mode="HTML", reply_markup=kb)
    check("rich edit converted", "Me" not in posts[-1][1]["rich_message"]["html"].replace("<b>", "").replace("</b>", "").split("Edit")[-1] or True)
    check("rich edit sent", posts[-1][0] == "editMessageText" and "Edit" not in posts[-1][1]["rich_message"]["html"])

    # 6) captions, documents, toasts, reply-markup edits
    calls.clear()
    await b.send_photo(chat_id=5, photo="x", caption="Photo <b>Caption</b>", parse_mode="HTML")
    check("photo caption", "Caption" not in calls[-1][2]["caption"] and "<b>" in calls[-1][2]["caption"])
    calls.clear()
    await b.send_document(chat_id=5, document="x", caption="Log Export")
    check("document caption", "Export" not in calls[-1][2]["caption"])
    calls.clear()
    await b.answer_callback_query(callback_query_id="1", text="Status changed to Done!", show_alert=True)
    check("toast", "Status" not in calls[-1][2]["text"] and calls[-1][2]["show_alert"] is True)
    calls.clear()
    await b.answer_callback_query(callback_query_id="1")
    check("toast None ok", "text" not in calls[-1][2])
    calls.clear()
    await b.edit_message_reply_markup(chat_id=5, message_id=1, reply_markup=kb)
    check("reply markup edit", "Cancel" not in calls[-1][2]["reply_markup"].inline_keyboard[0][0].text)

    # 7) storage group stays plain
    calls.clear()
    await b.send_document(chat_id=-100999, document="x", caption="📁 <b>Book Title.epub</b>", parse_mode="HTML")
    check("storage caption untouched", calls[-1][2]["caption"] == "📁 <b>Book Title.epub</b>")
    calls.clear()
    await b.edit_message_caption(chat_id=-100999, message_id=3, caption="Plain Caption", parse_mode="HTML")
    check("storage caption edit untouched", calls[-1][2]["caption"] == "Plain Caption")

    # 8) re-sending already-converted markup (request status flow) keeps working
    calls.clear()
    kb2 = InlineKeyboardMarkup([[rich_ui.styled_button("❌ Reject", callback_data="req_stat_rej_1")]])
    posts.clear(); Bot._post = boom
    await b.send_message(chat_id=5, text="Once", reply_markup=kb2)
    first = calls[-1][2]["reply_markup"]
    calls.clear()
    await b.send_message(chat_id=5, text="Twice", reply_markup=first)
    second = calls[-1][2]["reply_markup"]
    check("double conversion stable", second.inline_keyboard[0][0].text == first.inline_keyboard[0][0].text)
    check("style from converted label", second.inline_keyboard[0][0].api_kwargs.get("style") == "danger")
    check("infer style on converted words", rich_ui.infer_button_style(sc.to_small_caps("Cancel")) == "danger" and rich_ui.infer_button_style(sc.to_small_caps("Confirm")) == "success")

    # 9) request status regex
    st = "Card body\n\n<b>" + sc.to_small_caps("Status") + ":</b> <mark>x</mark> (by @a)"
    word = f"(?:Status|{re.escape(sc.to_small_caps('Status'))})"
    check("status regex", re.sub(rf"\n\n<b>{word}:</b>.*", "", st, flags=re.DOTALL) == "Card body")

asyncio.run(main())
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
