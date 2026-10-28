import asyncio
import os
import stat
from zipfile import ZipFile

from modules.converter import engine
from modules.converter.formats import (
    INPUT_FORMATS,
    OUTPUT_FORMATS,
    detect_input_format,
    is_supported_input,
    output_choices,
)
from ebook_converter import Converter, convert_ebook


def test_supported_counts():
    assert len(INPUT_FORMATS) == 62
    assert len(OUTPUT_FORMATS) == 31
    assert len(Converter.supported_input_types) == 62
    assert len(Converter.supported_output_types) == 31


def test_detect_input_format():
    assert detect_input_format("Book.EPUB") == "epub"
    assert detect_input_format("novel.fb2.zip") == "fbz"
    assert detect_input_format("shamela.bok") == "bok"
    assert detect_input_format("paper.typst") == "typst"
    assert detect_input_format("noextension") == ""
    assert is_supported_input("a.mobi") and is_supported_input("a.bok") and not is_supported_input("a.exe")


def test_output_choices_exclude_input():
    assert "epub" not in output_choices("epub")
    assert "pdf" not in output_choices("pdf")
    # EPUB is in both Calibre and Pandoc maps, so it offers both Calibre and Pandoc outputs (30 total)
    assert len(output_choices("epub")) == 30
    # AZW3 is Calibre-only input, so it offers the other 20 Calibre outputs
    assert len(output_choices("azw3")) == 20


def test_safe_output_name():
    assert engine.safe_output_name("My Book.epub", "pdf") == "My Book.pdf"
    assert engine.safe_output_name("../../etc/passwd.mobi", "txt") == "passwd.txt"
    assert engine.safe_output_name('a<b>:"c".docx', "epub") == "a b c.epub"
    assert engine.safe_output_name("story.fb2.zip", "epub") == "story.epub"
    assert engine.safe_output_name("", "epub") == "book.epub"
    assert len(engine.safe_output_name("x" * 500 + ".epub", "pdf")) <= 104


def _fake_converter(tmp_path, monkeypatch, body: str, binary_name: str = "ebook-convert"):
    binary = tmp_path / "bin" / binary_name
    binary.parent.mkdir(exist_ok=True)
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
    assert res.ok and res.success and res.path.name == "input.out.pdf" and res.path.stat().st_size > 0


def test_convert_ebook_facade(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo converted > "$2"\n')
    src = tmp_path / "input.mobi"
    src.write_text("x")
    res = run(convert_ebook(src, "epub", timeout=10))
    assert res.success and res.output_file.exists()


def test_set_epub_rtl(tmp_path):
    epub_file = tmp_path / "sample.epub"
    with ZipFile(epub_file, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/content.opf", '<package><manifest/><spine toc="ncx"/></package>')
        zf.writestr("OEBPS/style.css", "body { color: black; }")
    assert engine.set_epub_rtl(epub_file) is True
    with ZipFile(epub_file, "r") as zf:
        assert 'page-progression-direction="rtl"' in zf.read("OEBPS/content.opf").decode()
        assert b"direction: rtl !important" in zf.read("OEBPS/style.css")


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


class _Sink(engine.ProgressSink):
    def __init__(self):
        self.lines, self.stages, self.tools = [], [], []

    def line(self, text):
        self.lines.append(text)

    def stage(self, text):
        self.stages.append(text)

    def started(self, pid, tool):
        self.tools.append(tool)


def test_progress_streams_lines_live(tmp_path, monkeypatch):
    _fake_converter(
        tmp_path, monkeypatch,
        'echo "Parsing all content..."\nprintf "34%% Running transforms\\r67%% PDF Output plugin\\n"\necho done > "$2"\n',
    )
    src = tmp_path / "input.epub"
    src.write_text("x")
    sink = _Sink()
    res = run(engine.convert_file(src, "pdf", timeout=10, progress=sink))
    assert res.ok
    assert sink.lines == ["Parsing all content...", "34% Running transforms", "67% PDF Output plugin"]
    assert sink.tools == ["ebook-convert"] and any("Calibre" in s for s in sink.stages)


def test_sigkill_is_reported_as_oom(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo "68%% Parsed all content for"\nkill -9 $$\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=10))
    assert not res.ok
    assert "SIGKILL" in res.error and "memory" in res.error and "Parsed all content for" in res.error


def test_pdf_no_cover_default(tmp_path, monkeypatch):
    _fake_converter(tmp_path, monkeypatch, 'echo "$@" > "$2.args"\necho x > "$2"\n')
    src = tmp_path / "input.epub"
    src.write_text("x")
    res = run(engine.convert_file(src, "pdf", timeout=10))
    assert res.ok and "--pdf-no-cover" in (tmp_path / "input.out.pdf.args").read_text()
