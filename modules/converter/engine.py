"""Conversion engine of the ebook converter (Telegram-free).

It takes a file on disk and returns a file on disk, which keeps it easy to test and reuse.

Backends (see ``formats.py`` for the routing rules)
    * Calibre ``ebook-convert``  - most ebook formats
    * Pandoc                      - markup / office formats and md, html, odt, ...
    * Calibre KFX plugin          - opt-in, via ``calibre-debug``
    * PyMuPDF                     - optional; extracts PDF text into an HTMLZ for cleaner output
    * Anydoc (``firecrawl-anydoc``) - optional; reads legacy doc / xls / ppt / odp / ods

Every external process runs in its own process group so a timeout kills the whole tree, and a
conversion never leaves a half-written output behind.
"""
import asyncio
import html
import importlib.util
import logging
import os
import re
import shutil
import signal
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from modules.converter.formats import (
    ANYDOC_INPUTS,
    KFX_ALLOWED_SOURCES,
    KFX_INPUTS,
    KFX_OUTPUT,
    PANDOC_INPUT_MAP,
    PANDOC_OUTPUT_MAP,
    backend_for,
    detect_input_format,
    output_choices,
)

logger = logging.getLogger(__name__)

CALIBRE_BINARY = "ebook-convert"
CALIBRE_DEBUG_BINARY = "calibre-debug"
POLISH_BINARY = "ebook-polish"
PANDOC_BINARY = "pandoc"
CONVERTER_BINARY = CALIBRE_BINARY  # kept for backwards compatibility
MAX_ERROR_CHARS = 600

_CALIBRE_ERROR_RE = re.compile(r"(Conversion Failure Reason\s+\*{5,}\s+[E\d]+:.*)|(Conversion error: .*)")


@dataclass
class ConversionResult:
    """Outcome of one conversion. ``ok`` is True only if ``path`` exists and is non-empty."""
    ok: bool
    path: Optional[Path] = None
    error: str = ""


# ----------------------------------------------------------------------------- capabilities
def calibre_available() -> bool:
    return shutil.which(CALIBRE_BINARY) is not None


def converter_available() -> bool:
    """True if Calibre's ``ebook-convert`` is on PATH (kept for backwards compatibility)."""
    return calibre_available()


def pandoc_available() -> bool:
    return shutil.which(PANDOC_BINARY) is not None


def pymupdf_available() -> bool:
    return importlib.util.find_spec("pymupdf") is not None


def anydoc_available() -> bool:
    return importlib.util.find_spec("anydoc") is not None


def any_backend_available() -> bool:
    return calibre_available() or pandoc_available()


def capabilities() -> dict:
    """What this host can do - handy for /ping style diagnostics and the tests."""
    return {
        "calibre": calibre_available(),
        "pandoc": pandoc_available(),
        "pymupdf": pymupdf_available(),
        "anydoc": anydoc_available(),
        "kfx_tools": shutil.which(CALIBRE_DEBUG_BINARY) is not None,
    }


def available_output_choices(input_format: str, *, kfx: bool = False) -> List[str]:
    """Output formats offered for ``input_format`` on *this* host (backends + optional deps)."""
    fmt = (input_format or "").lower().lstrip(".")
    if fmt in ANYDOC_INPUTS and not anydoc_available():
        return []
    return output_choices(fmt, calibre=calibre_available(), pandoc=pandoc_available(), kfx=kfx)


def missing_dependency_hint(input_format: str) -> str:
    """Human readable reason why nothing can be offered for ``input_format`` (or '')."""
    fmt = (input_format or "").lower().lstrip(".")
    if not any_backend_available():
        return "Neither Calibre nor Pandoc is installed on this host."
    if fmt in ANYDOC_INPUTS and not anydoc_available():
        return f".{fmt} files need the optional 'firecrawl-anydoc' package."
    if not available_output_choices(fmt):
        return f"No converter for .{fmt} is installed on this host."
    return ""


# ----------------------------------------------------------------------------- small helpers
def safe_output_name(original_name: str, output_format: str) -> str:
    """Build a clean download name: original stem (sanitised, max 100 chars) + new extension."""
    stem = Path(original_name or "book").name
    stem = re.sub(r"\.fb2\.zip$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", stem)
    stem = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .") or "book"
    return f"{stem[:100].strip()}.{output_format}"


def _tail(text: str) -> str:
    text = (text or "").strip()
    return text[-MAX_ERROR_CHARS:]


def _kill_group(pid: int) -> None:
    with suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pid, signal.SIGKILL)


def _summarise_failure(output: str) -> str:
    """Prefer Calibre's own 'Conversion error' lines; otherwise the tail of the log."""
    matches = _CALIBRE_ERROR_RE.findall(output)
    if matches:
        return _tail("\n".join((a or b).strip() for a, b in matches).replace("*", ""))
    lines = [ln for ln in output.splitlines() if not any(s in ln for s in (":fixme:", "DEBUG -", "INFO -"))]
    return _tail("\n".join(lines[-15:]))


async def _run_cmd(command: List[str], timeout: int) -> Tuple[Optional[int], str, bool]:
    """Run ``command`` in its own process group.

    Returns ``(returncode, log_text, timed_out)``; ``returncode`` is None if the binary is missing.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # own process group -> killable as a whole
        )
    except OSError as exc:
        return None, f"Could not start '{command[0]}': {exc}", False

    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_group(proc.pid)
        with suppress(Exception):
            await proc.wait()
        return proc.returncode, f"Conversion timed out after {timeout} seconds.", True
    except asyncio.CancelledError:
        _kill_group(proc.pid)
        raise
    finally:
        if proc.returncode is None:  # only if still running (e.g. cancelled); never a recycled pid
            _kill_group(proc.pid)
    return proc.returncode, (out or b"").decode(errors="replace"), False


# ----------------------------------------------------------------------------- pre/post steps
def pdf_to_htmlz(input_file: Path, output_file: Path) -> Optional[str]:
    """Extract the text blocks of a PDF into an HTMLZ archive. Returns an error string or None."""
    try:
        import pymupdf
    except ImportError:
        return "pymupdf is not installed."

    parts: List[str] = []
    total_chars = 0
    try:
        with pymupdf.open(str(input_file)) as doc:
            for page in doc:
                for block in page.get_text("blocks", sort=True):
                    if len(block) < 7 or block[6] != 0 or not block[4]:
                        continue
                    lines = [ln.strip() for ln in str(block[4]).splitlines() if ln.strip()]
                    if lines:
                        paragraph = " ".join(lines)
                        total_chars += len(paragraph)
                        parts.append(f"<p>{html.escape(paragraph)}</p>")
                parts.append("<hr />")
    except Exception as exc:  # corrupt / encrypted PDF
        return f"Could not read the PDF: {exc}"

    if total_chars == 0:
        return "No extractable text found in the PDF (scanned / image-only PDF)."

    title = html.escape(input_file.stem)
    body = "\n".join(parts)
    page = (f'<html><head><meta charset="utf-8"><title>{title}</title></head>'
            f"<body>{body}</body></html>").encode("utf-8")
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", page)
    return None


def set_epub_rtl(epub_path: Path) -> bool:
    """Force RTL page progression and CSS direction inside an EPUB archive (in place)."""
    epub_path = Path(epub_path)
    if not epub_path.exists():
        return False
    try:
        with zipfile.ZipFile(epub_path, "r") as zin:
            names = zin.namelist()
            opf_files = [n for n in names if n.endswith(".opf")]
            if not opf_files:
                return False
            replacements = {}
            for opf_name in opf_files:
                opf_text = zin.read(opf_name).decode("utf-8", errors="ignore")
                if 'page-progression-direction="rtl"' not in opf_text:
                    opf_text = re.sub(r"<spine\b([^>]*)>", r'<spine\1 page-progression-direction="rtl">',
                                      opf_text, count=1)
                    replacements[opf_name] = opf_text.encode("utf-8")
            for css_name in [n for n in names if n.endswith(".css")]:
                css_bytes = zin.read(css_name)
                if b"direction: rtl !important" not in css_bytes[:300].lower():
                    replacements[css_name] = b"* {direction: rtl !important;}\n" + css_bytes
            if not replacements:
                return True

            tmp_path = epub_path.with_suffix(".rtl_tmp.epub")
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                if "mimetype" in names:  # must be the first, uncompressed entry
                    zout.writestr("mimetype", zin.read("mimetype"), compress_type=zipfile.ZIP_STORED)
                for item in zin.infolist():
                    if item.filename == "mimetype":
                        continue
                    zout.writestr(item, replacements.get(item.filename, zin.read(item.filename)))
        tmp_path.replace(epub_path)
        return True
    except Exception as exc:
        logger.warning("Failed to set RTL on %s: %s", epub_path, exc)
        return False


# ----------------------------------------------------------------------------- the pipeline
async def _pandoc(src: Path, dst: Path, in_fmt: str, out_fmt: str, timeout: int) -> str:
    if in_fmt not in PANDOC_INPUT_MAP or out_fmt not in PANDOC_OUTPUT_MAP:
        return f"Unsupported Pandoc route: {in_fmt} -> {out_fmt}"
    if not pandoc_available():
        return "Pandoc is not installed on this host."
    cmd = [PANDOC_BINARY, str(src), "-f", PANDOC_INPUT_MAP[in_fmt], "-t", PANDOC_OUTPUT_MAP[out_fmt], "-o", str(dst)]
    rc, text, timed_out = await _run_cmd(cmd, timeout)
    if timed_out:
        return text
    if rc != 0:
        logger.warning("pandoc failed (%s): %s", rc, _tail(text))
        return _summarise_failure(text) or f"Pandoc exited with code {rc}."
    return ""


async def _calibre(src: Path, dst: Path, out_fmt: str, timeout: int) -> str:
    if not calibre_available():
        return "Calibre (ebook-convert) is not installed on this host."
    cmd = [CALIBRE_BINARY, str(src), str(dst)]
    if out_fmt == "docx":
        cmd += ["--filter-css", "float"]
    rc, text, timed_out = await _run_cmd(cmd, timeout)
    if timed_out:
        return text
    if rc != 0:
        logger.warning("ebook-convert failed (%s): %s", rc, _tail(text))
        return _summarise_failure(text) or f"Converter exited with code {rc}."
    return ""


async def _kfx_plugin(plugin: str, src: Path, timeout: int) -> str:
    """Run Calibre's KFX Input / Output plugin; its result lands next to ``src``."""
    rc, text, timed_out = await _run_cmd([CALIBRE_DEBUG_BINARY, "-r", plugin, "--", str(src)], timeout)
    if timed_out:
        return text
    if rc is None:
        return "Calibre (calibre-debug) is not installed on this host."
    return _summarise_failure(text) if rc != 0 else ""


async def _pipeline(src: Path, in_fmt: str, out_fmt: str, dst: Path, timeout: int, *,
                    force_rtl: bool, compress_images: bool, temps: List[Path]) -> str:
    """Run every stage; returns an error message ('' on success). Intermediates go to ``temps``."""
    cur, cur_fmt = src, in_fmt

    # 1. PDF -> HTMLZ text extraction (falls back to Calibre's own PDF reader without PyMuPDF)
    if in_fmt == "pdf" and pymupdf_available():
        pre = src.with_name(f"{src.stem}.pre.htmlz")
        temps.append(pre)
        err = await asyncio.to_thread(pdf_to_htmlz, src, pre)
        if err:
            return err
        cur, cur_fmt = pre, "htmlz"

    # 2. Legacy Office / OpenDocument -> Markdown through Anydoc
    elif in_fmt in ANYDOC_INPUTS:
        try:
            import anydoc
        except ImportError:
            return "The optional 'firecrawl-anydoc' package is not installed on this host."
        try:
            md_text = await asyncio.wait_for(asyncio.to_thread(anydoc.to_markdown, str(src)), timeout)
        except asyncio.TimeoutError:
            return f"Conversion timed out after {timeout} seconds."
        except Exception as exc:
            return str(exc) or "Anydoc extraction failed."
        if not md_text.strip():
            return "No content could be extracted from the input file."
        pre = src.with_name(f"{src.stem}.pre.md")
        temps.append(pre)
        pre.write_text(md_text, encoding="utf-8")
        cur, cur_fmt = pre, "md"

    # 3. KFX family -> EPUB through the Calibre KFX Input plugin
    elif in_fmt in KFX_INPUTS:
        err = await _kfx_plugin("KFX Input", src, timeout)
        epub = src.with_suffix(".epub")
        if not epub.exists():
            return err or "Failed to read the KFX input."
        temps.append(epub)
        cur, cur_fmt = epub, "epub"

    # 4. Optional RTL pre-processing of an EPUB source (a private temp copy, safe to modify)
    if force_rtl and cur_fmt == "epub":
        set_epub_rtl(cur)

    # 5. Writer stage
    backend = backend_for(in_fmt, out_fmt)
    if backend == "kfx":
        if cur_fmt not in KFX_ALLOWED_SOURCES:
            return f"Cannot convert {in_fmt} directly to KFX."
        err = await _kfx_plugin("KFX Output", cur, timeout)
        produced = cur.with_suffix(f".{KFX_OUTPUT}")
        if produced.exists():
            produced.replace(dst)
            return ""
        return err or "The KFX plugin produced no output."
    if backend == "pandoc":
        err = await _pandoc(cur, dst, cur_fmt, out_fmt, timeout)
    else:
        err = await _calibre(cur, dst, out_fmt, timeout)
    if err:
        return err

    # 6. Post-processing
    if out_fmt == "epub" and force_rtl and dst.exists():
        set_epub_rtl(dst)
    if compress_images and out_fmt in {"azw3", "epub", "kepub"} and dst.exists() and shutil.which(POLISH_BINARY):
        await _run_cmd([POLISH_BINARY, "--compress-images", str(dst)], timeout)
    return ""


async def convert_file(src: Path, output_format: str, timeout: int = 300, *, force_rtl: bool = False,
                       compress_images: bool = False, enable_kfx: bool = False) -> ConversionResult:
    """Convert ``src`` to ``output_format`` next to it and return a :class:`ConversionResult`."""
    src = Path(src)
    out_fmt = (output_format or "").lower().lstrip(".")
    if not src.exists():
        return ConversionResult(False, error=f"Input file not found: {src.name}")

    in_fmt = detect_input_format(src.name)
    backend = backend_for(in_fmt, out_fmt)
    if backend in ("calibre", "kfx") and not calibre_available():
        return ConversionResult(False, error="Calibre (ebook-convert) is not installed on this host.")
    if backend == "pandoc" and not pandoc_available():
        return ConversionResult(False, error="Pandoc is not installed on this host.")
    if out_fmt not in output_choices(in_fmt, calibre=calibre_available(), pandoc=pandoc_available(),
                                     kfx=enable_kfx):
        return ConversionResult(False, error=f"Converting .{in_fmt} to .{out_fmt} is not supported.")

    dst = src.with_name(f"{src.stem}.out.{out_fmt}")
    dst.unlink(missing_ok=True)
    temps: List[Path] = []
    try:
        error = await _pipeline(src, in_fmt, out_fmt, dst, timeout, force_rtl=force_rtl,
                                compress_images=compress_images, temps=temps)
    except asyncio.CancelledError:
        dst.unlink(missing_ok=True)
        raise
    finally:
        for tmp in temps:
            tmp.unlink(missing_ok=True)

    if error:
        dst.unlink(missing_ok=True)
        return ConversionResult(False, error=error)
    if not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        return ConversionResult(False, error="The converter produced no output file.")
    return ConversionResult(True, path=dst)


# ----------------------------------------------------------------------------- concurrency
_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_size = 0


def get_semaphore(limit: int) -> asyncio.Semaphore:
    """Shared concurrency limiter; rebuilt only when the configured limit changes."""
    global _semaphore, _semaphore_size
    limit = max(1, int(limit))
    if _semaphore is None or _semaphore_size != limit:
        _semaphore, _semaphore_size = asyncio.Semaphore(limit), limit
    return _semaphore
