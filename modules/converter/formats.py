"""Format tables and routing rules for the ebook converter.

Everything here is plain data / pure functions so it can be imported (and tested) without
Telegram, Calibre or Pandoc installed.

Three conversion backends exist (see ``engine.py``):

* **calibre**  - ``ebook-convert``; reads most ebook formats, writes ``CALIBRE_OUTPUTS``.
* **pandoc**   - used for markup/office formats (``PANDOC_ONLY_*``) and for ``md``/``html``/...
* **kfx**      - Calibre's KFX Input/Output *plugin* (opt-in, ``convert_kfx_enabled``).

Legacy Office files (``doc``, ``xls`` ...) and PDFs get a pre-processing step first
(Anydoc / PyMuPDF), after which the normal routes apply.
"""

# ----------------------------------------------------------------------------- outputs
# Output formats Calibre can write (``kfx`` is handled separately, it needs a plugin).
CALIBRE_OUTPUTS = (
    "azw3", "docx", "epub", "fb2", "htmlz", "kepub", "lit", "lrf", "mobi", "oeb", "pdb",
    "pdf", "pmlz", "rb", "rtf", "snb", "tcr", "txt", "txtz", "zip",
)
KFX_OUTPUT = "kfx"

# Output formats that only Pandoc can write.
PANDOC_ONLY_OUTPUTS = ("adoc", "html", "md", "odt", "org", "pptx", "rst", "tex", "typ", "typst")

# Display order of the buttons: the popular formats first, then the rest alphabetically.
_POPULAR = ("epub", "mobi", "azw3", "pdf", "docx", "fb2", "rtf", "txt", "htmlz", "txtz", "md", "html")
_ALL_OUTPUTS = set(CALIBRE_OUTPUTS) | set(PANDOC_ONLY_OUTPUTS) | {KFX_OUTPUT}
OUTPUT_FORMATS = tuple(_POPULAR) + tuple(sorted(_ALL_OUTPUTS - set(_POPULAR)))

# Formats most readers want; they get a marker on their button.
HIGHLIGHTED_FORMATS = frozenset({"epub", "mobi", "azw3", "pdf", "docx", "kfx", "md"})

# ----------------------------------------------------------------------------- pandoc maps
# file extension -> Pandoc reader name
PANDOC_INPUT_MAP = {
    "adoc": "asciidoc", "asciidoc": "asciidoc", "csv": "csv", "docx": "docx", "epub": "epub",
    "fb2": "fb2", "htm": "html", "html": "html", "ipynb": "ipynb", "md": "gfm",
    "mediawiki": "mediawiki", "odt": "odt", "org": "org", "pptx": "pptx", "rst": "rst",
    "rtf": "rtf", "t2t": "t2t", "tex": "latex", "textile": "textile", "tsv": "tsv",
    "txt": "markdown", "typ": "typst", "typst": "typst", "xlsx": "xlsx", "xhtml": "html",
}
# file extension -> Pandoc writer name
PANDOC_OUTPUT_MAP = {
    "adoc": "asciidoc", "docx": "docx", "epub": "epub", "html": "html5", "md": "gfm+raw_html",
    "odt": "odt", "org": "org", "pptx": "pptx", "rst": "rst", "tex": "latex", "txt": "plain",
    "typ": "typst", "typst": "typst",
}
# Inputs only Pandoc understands.
PANDOC_ONLY_INPUTS = frozenset({
    "adoc", "asciidoc", "csv", "ipynb", "mediawiki", "org", "pptx", "rst", "t2t", "tex",
    "textile", "tsv", "typ", "typst", "xlsx",
})

# ----------------------------------------------------------------------------- special inputs
# Legacy Office / OpenDocument inputs: extracted to Markdown with the ``anydoc`` package first.
ANYDOC_INPUTS = frozenset({"doc", "docm", "odp", "ods", "ppt", "xls", "xlsm"})
# Amazon KFX family: needs Calibre's "KFX Input" plugin.
KFX_INPUTS = frozenset({"azw8", "kfx", "kfx-zip"})
# Sources the "KFX Output" plugin accepts.
KFX_ALLOWED_SOURCES = frozenset({"epub", "opf", "mobi", "doc", "docx", "kpf", "kfx-zip"})

# Everything the bot can read (the standalone module's 62 inputs; Shamela ``.bok`` is not
# included because its helper was never part of the module).
INPUT_FORMATS = frozenset({
    "azw", "azw3", "azw4", "azw8", "adoc", "asciidoc", "cb7", "cbc", "cbr", "cbz", "chm",
    "csv", "djv", "djvu", "docm", "docx", "doc", "kepub", "epub", "fb2", "fbz", "htm", "html",
    "htmlz", "ipynb", "kfx", "kfx-zip", "kpf", "lit", "lrf", "md", "mobi", "mediawiki", "odt",
    "odp", "ods", "opf", "org", "pdb", "pml", "ppt", "pptx", "prc", "rb", "rst", "rtf", "snb",
    "tcr", "tex", "textile", "tsv", "txt", "txtz", "t2t", "typ", "typst", "xls", "xlsm", "xlsx",
    "xhtml", "pdf",
})

# Telegram Bot API limits.
BOT_DOWNLOAD_LIMIT_MB = 20
BOT_UPLOAD_LIMIT_MB = 50


# ----------------------------------------------------------------------------- helpers
def detect_input_format(file_name: str) -> str:
    """Return the lowercase input format of ``file_name`` or an empty string.

    ``book.fb2.zip`` is reported as ``fbz`` because that is the name Calibre expects.
    """
    name = (file_name or "").strip().lower()
    if name.endswith(".fb2.zip"):
        return "fbz"
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


def is_supported_input(file_name: str) -> bool:
    return detect_input_format(file_name) in INPUT_FORMATS


def effective_input(input_format: str) -> str:
    """The format the writer stage really sees after pre-processing.

    PDF -> htmlz (PyMuPDF text extraction), legacy Office -> Markdown (Anydoc),
    KFX family -> EPUB (Calibre KFX Input plugin).
    """
    if input_format == "pdf":
        return "htmlz"
    if input_format in ANYDOC_INPUTS:
        return "md"
    if input_format in KFX_INPUTS:
        return "epub"
    return input_format


def _same_pandoc_route(input_format: str, output_format: str) -> bool:
    return input_format == output_format or (
        input_format in PANDOC_INPUT_MAP
        and output_format in PANDOC_OUTPUT_MAP
        and PANDOC_INPUT_MAP[input_format] == PANDOC_OUTPUT_MAP[output_format]
    )


def backend_for(input_format: str, output_format: str) -> str:
    """Which backend writes ``output_format`` for ``input_format``: calibre | pandoc | kfx."""
    if output_format == KFX_OUTPUT:
        return "kfx"
    eff = effective_input(input_format)
    if eff in PANDOC_ONLY_INPUTS or output_format in PANDOC_ONLY_OUTPUTS:
        return "pandoc"
    return "calibre"


def output_choices(input_format: str, *, calibre: bool = True, pandoc: bool = True,
                   kfx: bool = False) -> list:
    """Output formats to offer for ``input_format``, in button order.

    The same format is never offered. ``calibre`` / ``pandoc`` / ``kfx`` say which backends
    are usable; outputs whose backend is unavailable are left out.
    """
    fmt = (input_format or "").lower().lstrip(".")
    if fmt in ANYDOC_INPUTS:
        candidates = set(CALIBRE_OUTPUTS) | set(PANDOC_ONLY_OUTPUTS) | {KFX_OUTPUT}
    elif fmt not in PANDOC_INPUT_MAP:
        candidates = set(CALIBRE_OUTPUTS) | {KFX_OUTPUT}
    elif fmt in PANDOC_ONLY_INPUTS:
        candidates = set(PANDOC_OUTPUT_MAP)
    else:
        candidates = set(CALIBRE_OUTPUTS) | set(PANDOC_ONLY_OUTPUTS) | {KFX_OUTPUT}

    result = []
    for out in OUTPUT_FORMATS:
        if out not in candidates or out == fmt or _same_pandoc_route(fmt, out):
            continue
        if out == KFX_OUTPUT and (not kfx or effective_input(fmt) not in KFX_ALLOWED_SOURCES):
            continue
        backend = backend_for(fmt, out)
        if (backend == "calibre" and not calibre) or (backend == "pandoc" and not pandoc) \
                or (backend == "kfx" and not calibre):
            continue
        result.append(out)
    return result
