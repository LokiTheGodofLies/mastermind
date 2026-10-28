import asyncio
import os
import stat


from modules.converter import engine
from modules.converter.formats import (
    OUTPUT_FORMATS, detect_input_format, is_supported_input, output_choices,
)


def test_detect_input_format():
    assert detect_input_format("Book.EPUB") == "epub"
    assert detect_input_format("novel.fb2.zip") == "fbz"
    assert detect_input_format("noextension") == ""
    assert is_supported_input("a.mobi") and not is_supported_input("a.exe")


def test_output_choices_exclude_input():
    assert "epub" not in output_choices("epub")
    assert "pdf" not in output_choices("pdf")
    # pdf is not a Pandoc input, so it only gets Calibre outputs (and never kfx unless enabled)
    assert set(output_choices("pdf")) <= set(OUTPUT_FORMATS)
    assert "md" not in output_choices("pdf") and "epub" in output_choices("pdf")


def test_safe_output_name():
    assert engine.safe_output_name("My Book.epub", "pdf") == "My Book.pdf"
    assert engine.safe_output_name("../../etc/passwd.mobi", "txt") == "passwd.txt"
    assert engine.safe_output_name('a<b>:"c".docx', "epub") == "a b c.epub"
    assert engine.safe_output_name("story.fb2.zip", "epub") == "story.epub"
    assert engine.safe_output_name("", "epub") == "book.epub"
    assert len(engine.safe_output_name("x" * 500 + ".epub", "pdf")) <= 104


def _fake_converter(tmp_path, monkeypatch, body: str):
    binary = tmp_path / "bin" / "ebook-convert"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n" + body)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{binary.parent}{os.pathsep}{os.environ['PATH']}")


def run(coro):
    return asyncio.run(coro)


def test_convert_success(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=10))
    assert res.ok and res.path.name == "input.out.pdf" and res.path.stat().st_size > 0


def test_convert_failure_reports_tail(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo "boom: bad file"\nexit 3\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=10))
    assert not res.ok and "boom" in res.error
    assert not (tmp_path / "input.out.pdf").exists()


def test_convert_empty_output_is_error(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, ': > "$2"\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=10))
    assert not res.ok and "no output" in res.error.lower()


def test_convert_timeout_kills_process(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'sleep 30\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=1))
    assert not res.ok and "timed out" in res.error


def test_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf"))
    assert not res.ok and "not installed" in res.error
    assert engine.converter_available() is False


def test_semaphore_rebuilds_on_limit_change():
    async def go():
        a = engine.get_semaphore(2)
        assert engine.get_semaphore(2) is a
        assert engine.get_semaphore(3) is not a
    run(go())


# ----------------------------------------------------------------------------- merged engine
import shutil
import zipfile

import pytest


def _fake_tool(tmp_path, monkeypatch, name: str, body: str):
    binary = tmp_path / "bin" / name
    binary.parent.mkdir(exist_ok=True)
    binary.write_text("#!/bin/sh\n" + body)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{binary.parent}{os.pathsep}{os.environ['PATH']}")


def test_unsupported_route_is_rejected(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    src = tmp_path / "input.mobi"
    src.write_text("x")
    res = run(engine.convert_file(src, "md", timeout=10))  # mobi is not a Pandoc input
    assert not res.ok and "not supported" in res.error


def test_kfx_is_opt_in(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "kfx", timeout=10))
    assert not res.ok and "not supported" in res.error


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_pandoc_route_end_to_end(tmp_path):
    src = tmp_path / "input.md"
    src.write_text("# Title\n\nHello **world**\n")
    res = run(engine.convert_file(src, "html", timeout=30))
    assert res.ok and "<strong>world</strong>" in res.path.read_text()
    res = run(engine.convert_file(src, "rst", timeout=30))
    assert res.ok and "Title" in res.path.read_text()


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_pandoc_failure_is_reported(tmp_path):
    src = tmp_path / "input.docx"
    src.write_text("not a real docx")
    res = run(engine.convert_file(src, "md", timeout=30))
    assert not res.ok and res.error


def test_missing_pre_processors_are_reported(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    monkeypatch.setattr(engine, "anydoc_available", lambda: False)
    assert engine.available_output_choices("doc") == []
    assert "anydoc" in engine.missing_dependency_hint("doc")


def test_pdf_falls_back_to_calibre_without_pymupdf(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    monkeypatch.setattr(engine, "pymupdf_available", lambda: False)
    src = tmp_path / "input.pdf"
    src.write_text("%PDF-1.4")
    res = run(engine.convert_file(src, "epub", timeout=10))
    assert res.ok and res.path.name == "input.out.epub"


def test_pdf_text_extraction(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hello ebook world")
    pdf = tmp_path / "in.pdf"
    doc.save(str(pdf))
    out = tmp_path / "out.htmlz"
    assert engine.pdf_to_htmlz(pdf, out) is None
    with zipfile.ZipFile(out) as z:
        assert "Hello ebook world" in z.read("index.html").decode()


def _make_epub(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("OEBPS/content.opf", '<package><spine toc="ncx"><itemref idref="a"/></spine></package>')
        z.writestr("OEBPS/style.css", "p {margin:0}")


def test_set_epub_rtl(tmp_path):
    epub = tmp_path / "b.epub"
    _make_epub(epub)
    assert engine.set_epub_rtl(epub) is True
    with zipfile.ZipFile(epub) as z:
        assert z.namelist()[0] == "mimetype"
        assert 'page-progression-direction="rtl"' in z.read("OEBPS/content.opf").decode()
        assert z.read("OEBPS/style.css").startswith(b"* {direction: rtl !important;}")
    assert engine.set_epub_rtl(epub) is True       # idempotent
    assert engine.set_epub_rtl(tmp_path / "missing.epub") is False


def test_force_rtl_applies_to_epub_output(tmp_path, monkeypatch):
    # fake ebook-convert that writes a real (tiny) epub when asked for epub
    template = tmp_path / "template.epub"
    _make_epub(template)
    _fake_converter(tmp_path, monkeypatch, f'cp "{template}" "$2"\n')
    src = tmp_path / "input.mobi"
    src.write_text("x")
    res = run(engine.convert_file(src, "epub", timeout=10, force_rtl=True))
    assert res.ok
    with zipfile.ZipFile(res.path) as z:
        assert 'page-progression-direction="rtl"' in z.read("OEBPS/content.opf").decode()
