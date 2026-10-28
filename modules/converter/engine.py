"""Unified async e-book conversion engine (Calibre + Pandoc + PyMuPDF + Shamela .bok + Anydoc).

Supports all 62 input formats and 31 output formats while remaining completely Telegram-free
so it can be used by both python-telegram-bot handlers (`modules.converter.handlers`) and
standalone/Telethon callers (`ebook_converter`).
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
import html
import logging
import os
from pathlib import Path
import re
import shutil
import signal
from tempfile import NamedTemporaryFile
from typing import ClassVar, Optional
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from modules.converter.formats import (
    ANYDOC_INPUT_FORMATS,
    CALIBRE_OUTPUT_FORMATS,
    INPUT_FORMATS,
    KFX_ALLOWED_SOURCES,
    KFX_INPUT_FORMATS,
    OUTPUT_FORMATS,
    PANDOC_INPUT_MAP,
    PANDOC_ONLY_INPUT_FORMATS,
    PANDOC_ONLY_OUTPUT_FORMATS,
    PANDOC_OUTPUT_MAP,
    SUPPORTED_INPUT_LIST,
    detect_input_format,
    is_supported_input,
    output_choices,
)

logger = logging.getLogger(__name__)

CONVERTER_BINARY = "ebook-convert"
PANDOC_BINARY = "pandoc"
MAX_ERROR_CHARS = 1800
ERROR_TAIL_LINES = 25
KEEP_LOG_LINES = 400
SAMPLE_INTERVAL = 1.0
DEFAULT_TIMEOUT = 300


@dataclass
class ConversionResult:
    """Outcome of one conversion.

    Provides both `.ok` / `.path` (Mastermind Library Bot convention) and
    `.success` / `.output_file` aliases (standalone `ebook_converter` convention).
    """

    ok: bool
    path: Optional[Path] = None
    error: str = ""

    @property
    def success(self) -> bool:
        return self.ok

    @property
    def output_file(self) -> Optional[Path]:
        return self.path

    @output_file.setter
    def output_file(self, value: Optional[Path]) -> None:
        self.path = value


def converter_available() -> bool:
    """True if Calibre's ``ebook-convert`` or ``pandoc`` is on PATH."""
    return shutil.which(CONVERTER_BINARY) is not None or shutil.which(PANDOC_BINARY) is not None


def safe_output_name(original_name: str, output_format: str) -> str:
    """Build a clean download name: original stem (sanitised, max 100 chars) + new extension."""
    stem = Path(original_name or "book").name
    stem = re.sub(r"\.fb2\.zip$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", stem)
    stem = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .") or "book"
    return f"{stem[:100].strip()}.{output_format.lstrip('.')}"


class ProgressSink:
    """Receives live events from a running conversion. All methods are sync and must not block."""

    def stage(self, text: str) -> None:  # a high-level step ("Extracting PDF text", ...)
        ...

    def line(self, text: str) -> None:  # one line of converter output
        ...

    def started(self, pid: int, tool: str) -> None:  # a CLI tool was launched
        ...

    def stats(self, proc_rss: int | None, cg_used: int | None, cg_limit: int | None) -> None:  # memory sample
        ...


NULL_PROGRESS = ProgressSink()


def _group_rss_bytes(pgid: int) -> int | None:
    """Sum RSS of every process in process group ``pgid`` (Linux only)."""
    page = os.sysconf("SC_PAGE_SIZE")
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    total = 0
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8", errors="replace") as handle:
                rest = handle.read().rsplit(")", 1)[1].split()
            if int(rest[2]) != pgid:
                continue
            with open(f"/proc/{entry}/statm", encoding="utf-8") as handle:
                total += int(handle.read().split()[1]) * page
        except (OSError, ValueError, IndexError):
            continue
    return total


def _read_int(*paths: str) -> int | None:
    for path in paths:
        try:
            raw = Path(path).read_text().strip()
        except OSError:
            continue
        if raw.isdigit() and int(raw) < (1 << 60):
            return int(raw)
    return None


def _cgroup_memory() -> tuple[int | None, int | None]:
    """(used, limit) in bytes for the whole container, cgroup v2 or v1."""
    used = _read_int("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes")
    limit = _read_int("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    return used, limit


def describe_exit(rc: int | None) -> str:
    """Human readable exit status; negative codes are signals."""
    if rc is None:
        return "no exit code"
    if rc < 0:
        try:
            name = signal.Signals(-rc).name
        except ValueError:
            name = f"signal {-rc}"
        hint = " - the process was killed, most likely the container ran out of memory (OOM)" if -rc == 9 else ""
        return f"killed by {name} (exit {rc}){hint}"
    return f"exit code {rc}"


def _tail(text: str) -> str:
    text = (text or "").strip()
    return text[-MAX_ERROR_CHARS:]


def _kill_group(pid: int) -> None:
    with suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pid, signal.SIGKILL)


def pdf_to_htmlz(input_file: Path, output_file: Path) -> str | None:
    """Extract text blocks from a PDF into an HTMLZ archive for cleaner reflowable ebook conversion."""
    try:
        import pymupdf
    except ImportError:
        return "pymupdf is not installed."

    parts: list[str] = []
    total_chars = 0

    with pymupdf.open(str(input_file)) as doc:
        for page in doc:
            for block in page.get_text("blocks", sort=True):
                if len(block) < 7 or block[6] != 0 or not block[4]:
                    continue
                lines = [line.strip() for line in str(block[4]).splitlines() if line.strip()]
                if lines:
                    paragraph = " ".join(lines)
                    total_chars += len(paragraph)
                    parts.append(f"<p>{html.escape(paragraph)}</p>")
            parts.append("<hr />")

    if total_chars == 0:
        return "No extractable text found in PDF (scanned/image PDF)."

    title = html.escape(input_file.stem)
    body = "\n".join(parts)
    html_bytes = (
        f'<html><head><meta charset="utf-8"><title>{title}</title></head>'
        f"<body>{body}</body></html>"
    ).encode("utf-8")

    with ZipFile(output_file, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html_bytes)
    return None


def set_epub_rtl(epub_path: Path) -> bool:
    """Force RTL page progression and CSS direction inside an EPUB archive."""
    if not epub_path.exists():
        return False
    try:
        with ZipFile(epub_path, "r") as zin:
            namelist = zin.namelist()
            opf_files = [f for f in namelist if f.endswith(".opf")]
            if not opf_files:
                return False
            replacements: dict[str, bytes] = {}
            for opf_name in opf_files:
                opf_text = zin.read(opf_name).decode("utf-8", errors="ignore")
                if 'page-progression-direction="rtl"' not in opf_text:
                    opf_text = re.sub(
                        r"<spine\b([^>]*)>",
                        r'<spine\1 page-progression-direction="rtl">',
                        opf_text,
                        count=1,
                    )
                    replacements[opf_name] = opf_text.encode("utf-8")
            for css_name in [f for f in namelist if f.endswith(".css")]:
                css_bytes = zin.read(css_name)
                if b"direction: rtl !important" not in css_bytes[:300].lower():
                    replacements[css_name] = b"* {direction: rtl !important;}\n" + css_bytes

            if not replacements:
                return True

            temp_path = epub_path.with_suffix(".rtl_tmp.epub")
            with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as zout:
                if "mimetype" in namelist:
                    zout.writestr("mimetype", zin.read("mimetype"), compress_type=ZIP_STORED)
                for item in zin.infolist():
                    if item.filename == "mimetype":
                        continue
                    data = replacements.get(item.filename, zin.read(item.filename))
                    zout.writestr(item, data)
            temp_path.replace(epub_path)
            return True
    except Exception as exc:
        logger.warning("Failed to set RTL on %s: %s", epub_path, exc)
        return False


def bok_to_epub(input_bok: Path, out_epub: Path) -> None:
    """Convert a Shamela .bok (Jet/Access MDB) database file into an EPUB 3 file."""
    try:
        from access_parser import AccessParser
    except ImportError as exc:
        raise RuntimeError("access-parser is required to convert .bok files.") from exc

    db = AccessParser(str(input_bok))
    tables = sorted(t for t in db.catalog if t != "MSysObjects")
    b_tables = [t for t in tables if t.lower().startswith("b")]
    if not b_tables:
        raise ValueError("Could not find a content table in .bok file.")

    content = db.parse_table(b_tables[0])
    text_col = "nass" if "nass" in content else next(iter(content.keys()), "")
    if not text_col:
        raise ValueError("Could not find text column in .bok file.")

    pages_html: list[str] = []
    for raw in content.get(text_col) or []:
        if not raw:
            continue
        cleaned = str(raw).replace("\x00", "").strip()
        if not cleaned:
            continue
        paras = "".join(
            f"<p>{html.escape(line.strip())}</p>"
            for line in re.split(r"\r?\n+", cleaned)
            if line.strip()
        )
        if paras:
            pages_html.append(paras)

    if not pages_html:
        raise ValueError("No readable text pages found in .bok file.")

    title = html.escape(input_bok.stem)
    modified = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    zfill = len(str(len(pages_html))) + 1

    out_epub.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(out_epub, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr("OEBPS/styles.css", "body{line-height:1.7;margin:1.5rem}")
        manifest_items: list[str] = []
        spine_items: list[str] = []
        nav_items: list[str] = []
        for idx, body_html in enumerate(pages_html, start=1):
            fname = f"page_{idx:0{zfill}d}.xhtml"
            zf.writestr(
                f"OEBPS/text/{fname}",
                '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" dir="rtl">'
                f'<head><meta charset="utf-8"/><title>{title}</title><link rel="stylesheet" href="../styles.css"/></head>'
                f"<body><div>{body_html}</div></body></html>",
            )
            manifest_items.append(f'<item id="p{idx}" href="text/{fname}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="p{idx}"/>')
            nav_items.append(f'<li><a href="text/{fname}">Page {idx}</a></li>')

        nav_joined = "".join(nav_items)
        manifest_joined = "".join(manifest_items)
        spine_joined = "".join(spine_items)
        zf.writestr(
            "OEBPS/nav.xhtml",
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="ar" dir="rtl">'
            f'<head><meta charset="utf-8"/><title>{title}</title></head>'
            f'<body><nav epub:type="toc" id="toc"><ol>{nav_joined}</ol></nav></body></html>',
        )
        zf.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">urn:shamela_bok:0</dc:identifier>'
            f'<dc:title>{title}</dc:title><dc:language>ar</dc:language><meta property="dcterms:modified">{modified}</meta></metadata>'
            '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            f'<item id="css" href="styles.css" media-type="text/css"/>{manifest_joined}</manifest>'
            f'<spine page-progression-direction="rtl">{spine_joined}</spine></package>',
        )


async def _run_subprocess(
    command: list[str],
    timeout: int | None = DEFAULT_TIMEOUT,
    progress: ProgressSink | None = None,
) -> tuple[int | None, str]:
    """Run a CLI tool in its own process group, streaming its output line by line to ``progress``.

    Returns ``(returncode, error_text)``; ``error_text`` is empty on success.
    """
    progress = progress or NULL_PROGRESS
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
    except FileNotFoundError:
        return None, f"{command[0]} is not installed on this host."
    except OSError as exc:
        return None, f"Could not start {command[0]}: {exc}"

    tool = Path(command[0]).name
    progress.started(proc.pid, tool)
    lines: deque[str] = deque(maxlen=KEEP_LOG_LINES)
    peak = {"rss": 0}

    def emit(raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text or any(noise in text for noise in (":fixme:", "DEBUG -", "INFO -")):
            return
        lines.append(text)
        logger.info("[%s] %s", tool, text)
        progress.line(text)

    async def pump() -> None:
        assert proc.stdout is not None
        buf = b""
        while chunk := await proc.stdout.read(4096):
            buf += chunk
            *complete, buf = re.split(rb"[\r\n]+", buf)  # Calibre also uses \r for progress
            for raw in complete:
                emit(raw)
        if buf:
            emit(buf)
        await proc.wait()

    async def sampler() -> None:
        while True:
            rss = await asyncio.to_thread(_group_rss_bytes, proc.pid)
            used, limit = _cgroup_memory()
            if rss:
                peak["rss"] = max(peak["rss"], rss)
            progress.stats(rss, used, limit)
            await asyncio.sleep(SAMPLE_INTERVAL)

    sampler_task = asyncio.create_task(sampler())
    try:
        await (pump() if timeout is None else asyncio.wait_for(pump(), timeout=timeout))
    except asyncio.TimeoutError:
        _kill_group(proc.pid)
        with suppress(Exception):
            await proc.wait()
        return None, f"Conversion timed out after {timeout} seconds."
    except asyncio.CancelledError:
        _kill_group(proc.pid)
        raise
    finally:
        sampler_task.cancel()
        with suppress(asyncio.CancelledError):
            await sampler_task
        _kill_group(proc.pid)  # reap any leftover helper processes (QtWebEngine etc.)

    rc = proc.returncode
    if rc == 0:
        return 0, ""

    log_text = "\n".join(lines)
    if matches := re.findall(
        r"(Conversion Failure Reason\s+\*{5,}\s+[E\d]+:.*)|(Conversion error: .*)",
        log_text,
    ):
        err = "\n".join(m[0].strip() or m[1].strip() for m in matches).replace("*", "")
        return rc, _tail(err)

    header = f"{tool}: {describe_exit(rc)}"
    if peak["rss"]:
        header += f"; peak memory ~{peak['rss'] / 1048576:.0f} MB"
    tail = "\n".join(list(lines)[-ERROR_TAIL_LINES:])
    logger.warning("%s", header)
    return rc, _tail(f"{header}\n{tail}" if tail else header)


async def convert_file(
    src: Path,
    output_format: str,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    force_rtl: bool = False,
    compress_images: bool = False,
    extra_calibre_args: list[str] | None = None,
    pdf_no_cover: bool = True,
    progress: ProgressSink | None = None,
) -> ConversionResult:
    """Convert ``src`` (any of 62 formats) to ``output_format`` (any of 31 formats)."""
    src = Path(src)
    progress = progress or NULL_PROGRESS
    out_fmt = output_format.lower().lstrip(".")
    if not src.exists():
        return ConversionResult(False, error=f"Input file not found: {src}")

    in_fmt = detect_input_format(src.name)
    if in_fmt == "fbz" and src.suffix.lower() == ".zip":
        normalized = src.with_suffix(".fbz")
        src.replace(normalized)
        src = normalized

    dst = src.with_name(f"{src.stem}.out.{out_fmt}")
    dst.unlink(missing_ok=True)

    # 1. Shamela .bok input -> EPUB -> target format
    if in_fmt == "bok":
        epub_tmp = src.with_name(f"{src.stem}.bok_tmp.epub")
        progress.stage("Reading Shamela .bok database")
        try:
            coro = asyncio.to_thread(bok_to_epub, src, epub_tmp)
            await (coro if timeout is None else asyncio.wait_for(coro, timeout=timeout))
        except Exception as exc:
            epub_tmp.unlink(missing_ok=True)
            return ConversionResult(False, error=str(exc))

        if force_rtl:
            set_epub_rtl(epub_tmp)
        if out_fmt == "epub":
            epub_tmp.replace(dst)
            return ConversionResult(True, path=dst)
        try:
            res = await convert_file(
                epub_tmp,
                out_fmt,
                timeout=timeout,
                force_rtl=False,
                compress_images=compress_images,
                extra_calibre_args=extra_calibre_args,
                pdf_no_cover=pdf_no_cover,
                progress=progress,
            )
            if res.ok and res.path and res.path.exists():
                res.path.replace(dst)
                return ConversionResult(True, path=dst)
            return res
        finally:
            epub_tmp.unlink(missing_ok=True)

    # 2. Legacy Office / OpenDocument inputs via Anydoc -> Markdown -> target format
    if in_fmt in ANYDOC_INPUT_FORMATS:
        if shutil.which(CONVERTER_BINARY) and out_fmt in CALIBRE_OUTPUT_FORMATS and in_fmt == "doc":
            # Allow direct Calibre fallback if anydoc is not installed
            pass
        else:
            progress.stage("Extracting document text (anydoc)")
            try:
                import anydoc
            except ImportError:
                return ConversionResult(False, error="firecrawl-anydoc is not installed on this host.")
            try:
                coro = asyncio.to_thread(anydoc.to_markdown, str(src))
                md_text = await (coro if timeout is None else asyncio.wait_for(coro, timeout=timeout))
            except Exception as exc:
                return ConversionResult(False, error=str(exc) or "Anydoc extraction failed.")
            if not (md_text or "").strip():
                return ConversionResult(False, error="No extractable content found in document.")
            with NamedTemporaryFile(
                mode="w", dir=src.parent, prefix=f"{src.stem}.anydoc-", suffix=".md", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(md_text)
                md_path = Path(tmp.name)
            try:
                if out_fmt == "md":
                    md_path.replace(dst)
                    return ConversionResult(True, path=dst)
                res = await convert_file(
                    md_path,
                    out_fmt,
                    timeout=timeout,
                    force_rtl=force_rtl,
                    compress_images=compress_images,
                    extra_calibre_args=extra_calibre_args,
                    pdf_no_cover=pdf_no_cover,
                    progress=progress,
                )
                if res.ok and res.path and res.path.exists():
                    res.path.replace(dst)
                    return ConversionResult(True, path=dst)
                return res
            finally:
                md_path.unlink(missing_ok=True)

    # 3. PDF input -> extract reflowable text to HTMLZ if PyMuPDF is available & non-empty
    if in_fmt == "pdf" and out_fmt != "pdf":
        htmlz_tmp = src.with_name(f"{src.stem}.pdf_tmp.htmlz")
        pdf_err = None
        try:
            import pymupdf as _pymupdf  # noqa: F401
            # Only use pdf_to_htmlz when the file is a valid PDF signature (%PDF)
            if src.read_bytes()[:4] == b"%PDF":
                progress.stage("Extracting text from PDF (PyMuPDF)")
                pdf_err = pdf_to_htmlz(src, htmlz_tmp)
        except Exception:
            pdf_err = None
        if htmlz_tmp.exists():
            try:
                if out_fmt == "htmlz":
                    htmlz_tmp.replace(dst)
                    return ConversionResult(True, path=dst)
                res = await convert_file(
                    htmlz_tmp,
                    out_fmt,
                    timeout=timeout,
                    force_rtl=force_rtl,
                    compress_images=compress_images,
                    extra_calibre_args=extra_calibre_args,
                    pdf_no_cover=pdf_no_cover,
                    progress=progress,
                )
                if res.ok and res.path and res.path.exists():
                    res.path.replace(dst)
                    return ConversionResult(True, path=dst)
                return res
            finally:
                htmlz_tmp.unlink(missing_ok=True)
        elif pdf_err:
            return ConversionResult(False, error=pdf_err)

    # 4. KFX input -> Calibre KFX Input plugin -> EPUB -> target format
    if in_fmt in KFX_INPUT_FORMATS:
        progress.stage("Converting KFX input")
        rc, err = await _run_subprocess(["calibre-debug", "-r", "KFX Input", "--", str(src)], timeout=timeout, progress=progress)
        epub_inter = src.with_suffix(".epub")
        if rc != 0 or not epub_inter.exists():
            epub_inter.unlink(missing_ok=True)
            return ConversionResult(False, error=err or "Failed to convert KFX input.")
        if out_fmt == "epub":
            if force_rtl:
                set_epub_rtl(epub_inter)
            epub_inter.replace(dst)
            return ConversionResult(True, path=dst)
        try:
            res = await convert_file(
                epub_inter,
                out_fmt,
                timeout=timeout,
                force_rtl=force_rtl,
                compress_images=compress_images,
                extra_calibre_args=extra_calibre_args,
                pdf_no_cover=pdf_no_cover,
                progress=progress,
            )
            if res.ok and res.path and res.path.exists():
                res.path.replace(dst)
                return ConversionResult(True, path=dst)
            return res
        finally:
            epub_inter.unlink(missing_ok=True)

    # 5. Pre-process EPUB RTL if requested
    if in_fmt == "epub" and force_rtl:
        set_epub_rtl(src)

    # 6. KFX output -> Calibre KFX Output plugin
    if out_fmt == "kfx":
        if in_fmt not in KFX_ALLOWED_SOURCES:
            return ConversionResult(False, error=f"Cannot convert .{in_fmt} directly to KFX.")
        progress.stage("Building KFX output")
        rc, err = await _run_subprocess(["calibre-debug", "-r", "KFX Output", "--", str(src)], timeout=timeout, progress=progress)
        kfx_out = src.with_suffix(".kfx")
        if rc != 0 or not kfx_out.exists() or kfx_out.stat().st_size == 0:
            kfx_out.unlink(missing_ok=True)
            return ConversionResult(False, error=err or "KFX conversion produced no output file.")
        kfx_out.replace(dst)
        return ConversionResult(True, path=dst)

    # 7. Route to Pandoc or Calibre
    use_pandoc = (in_fmt in PANDOC_ONLY_INPUT_FORMATS) or (out_fmt in PANDOC_ONLY_OUTPUT_FORMATS)
    if use_pandoc:
        if not shutil.which(PANDOC_BINARY):
            return ConversionResult(False, error="Pandoc (pandoc) is not installed on this host.")
        if in_fmt not in PANDOC_INPUT_MAP or out_fmt not in PANDOC_OUTPUT_MAP:
            return ConversionResult(False, error=f"Unsupported Pandoc route: .{in_fmt} -> .{out_fmt}")
        cmd = [
            PANDOC_BINARY,
            str(src),
            "-f",
            PANDOC_INPUT_MAP[in_fmt],
            "-t",
            PANDOC_OUTPUT_MAP[out_fmt],
            "-o",
            str(dst),
        ]
        progress.stage(f"Running Pandoc (.{in_fmt} -> .{out_fmt})")
        rc, err = await _run_subprocess(cmd, timeout=timeout, progress=progress)
    else:
        if not shutil.which(CONVERTER_BINARY):
            return ConversionResult(False, error="Calibre (ebook-convert) is not installed on this host.")
        cmd = [CONVERTER_BINARY, str(src), str(dst)]
        if out_fmt == "pdf" and pdf_no_cover:
            cmd.append("--pdf-no-cover")  # same default as the original bot: skips the cover render pass
        if extra_calibre_args:
            cmd.extend(extra_calibre_args)
        progress.stage(f"Running Calibre (.{in_fmt} -> .{out_fmt})")
        rc, err = await _run_subprocess(cmd, timeout=timeout, progress=progress)

    if rc != 0:
        dst.unlink(missing_ok=True)
        return ConversionResult(False, error=err)

    if not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        return ConversionResult(False, error="The converter produced no output file.")

    if out_fmt == "epub" and force_rtl:
        set_epub_rtl(dst)

    if compress_images and out_fmt in {"azw3", "epub", "kepub"} and shutil.which("ebook-polish"):
        progress.stage("Compressing images")
        await _run_subprocess(["ebook-polish", "--compress-images", str(dst)], timeout=timeout, progress=progress)

    return ConversionResult(True, path=dst)


class Converter:
    """Object-oriented facade exposing all 62 input formats and 31 output formats."""

    calibre_output_types: ClassVar[list[str]] = list(CALIBRE_OUTPUT_FORMATS)
    pandoc_only_output_types: ClassVar[list[str]] = list(PANDOC_ONLY_OUTPUT_FORMATS)
    supported_output_types: ClassVar[list[str]] = list(OUTPUT_FORMATS)
    supported_input_types: ClassVar[list[str]] = list(SUPPORTED_INPUT_LIST)
    pandoc_input_map: ClassVar[dict[str, str]] = dict(PANDOC_INPUT_MAP)
    pandoc_output_map: ClassVar[dict[str, str]] = dict(PANDOC_OUTPUT_MAP)
    anydoc_input_types: ClassVar[set[str]] = set(ANYDOC_INPUT_FORMATS)
    pandoc_only_input_types: ClassVar[set[str]] = set(PANDOC_ONLY_INPUT_FORMATS)

    @classmethod
    def get_input_type(cls, file_name: str | Path | None) -> str:
        return detect_input_format(str(file_name or ""))

    @classmethod
    def is_supported_input(cls, file_name: str | Path | None) -> bool:
        return is_supported_input(str(file_name or ""))

    @classmethod
    def get_output_formats(cls, input_type: str) -> list[str]:
        return output_choices(input_type)

    async def convert(
        self,
        input_file: str | Path,
        output_type: str,
        *,
        force_rtl: bool = False,
        compress_images: bool = False,
        extra_calibre_args: list[str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress: ProgressSink | None = None,
    ) -> ConversionResult:
        return await convert_file(
            Path(input_file),
            output_type,
            timeout=timeout,
            force_rtl=force_rtl,
            compress_images=compress_images,
            extra_calibre_args=extra_calibre_args,
            progress=progress,
        )


async def convert_ebook(
    input_file: str | Path,
    output_type: str,
    *,
    force_rtl: bool = False,
    compress_images: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> ConversionResult:
    """Convenience helper function to convert an ebook in a single call."""
    return await convert_file(
        Path(input_file),
        output_type,
        timeout=timeout,
        force_rtl=force_rtl,
        compress_images=compress_images,
    )


_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_size = 0


def get_semaphore(limit: int) -> asyncio.Semaphore:
    """Shared concurrency limiter; rebuilt only when the configured limit changes."""
    global _semaphore, _semaphore_size
    limit = max(1, int(limit))
    if _semaphore is None or _semaphore_size != limit:
        _semaphore, _semaphore_size = asyncio.Semaphore(limit), limit
    return _semaphore
