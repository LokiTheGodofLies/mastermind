"""Format tables and routing rules for the unified ebook converter (62 inputs, 31 outputs).

Everything here is plain data so it can be imported and tested without Telegram, Calibre, or Pandoc.
"""

# 21 Calibre output formats
CALIBRE_OUTPUT_FORMATS = (
    "epub", "mobi", "azw3", "pdf", "docx", "fb2", "htmlz", "kepub", "kfx",
    "lit", "lrf", "oeb", "pdb", "pmlz", "rb", "rtf", "snb", "tcr", "txt", "txtz", "zip",
)

# 10 Pandoc-only output formats (21 + 10 = 31 total output formats)
PANDOC_ONLY_OUTPUT_FORMATS = (
    "adoc", "html", "md", "odt", "org", "pptx", "rst", "tex", "typ", "typst",
)

# All 31 output formats offered by the converter
OUTPUT_FORMATS = (*CALIBRE_OUTPUT_FORMATS, *PANDOC_ONLY_OUTPUT_FORMATS)

PANDOC_INPUT_MAP = {
    "adoc": "asciidoc",
    "asciidoc": "asciidoc",
    "csv": "csv",
    "docx": "docx",
    "epub": "epub",
    "fb2": "fb2",
    "htm": "html",
    "html": "html",
    "ipynb": "ipynb",
    "md": "gfm",
    "mediawiki": "mediawiki",
    "odt": "odt",
    "org": "org",
    "pptx": "pptx",
    "rst": "rst",
    "rtf": "rtf",
    "t2t": "t2t",
    "tex": "latex",
    "textile": "textile",
    "tsv": "tsv",
    "txt": "markdown",
    "typ": "typst",
    "typst": "typst",
    "xlsx": "xlsx",
    "xhtml": "html",
}

PANDOC_OUTPUT_MAP = {
    "adoc": "asciidoc",
    "docx": "docx",
    "epub": "epub",
    "html": "html5",
    "md": "gfm+raw_html",
    "odt": "odt",
    "org": "org",
    "pptx": "pptx",
    "rst": "rst",
    "tex": "latex",
    "txt": "plain",
    "typ": "typst",
    "typst": "typst",
}

ANYDOC_INPUT_FORMATS = frozenset({
    "doc", "docm", "odp", "ods", "ppt", "xls", "xlsm",
})

PANDOC_ONLY_INPUT_FORMATS = frozenset({
    "adoc", "asciidoc", "csv", "ipynb", "mediawiki", "org",
    "pptx", "rst", "t2t", "tex", "textile", "tsv", "typ", "typst", "xlsx",
})

KFX_INPUT_FORMATS = frozenset({"azw8", "kfx", "kfx-zip"})
KFX_ALLOWED_SOURCES = frozenset({"epub", "opf", "mobi", "doc", "docx", "kpf", "kfx-zip"})

# All 62 supported input formats
SUPPORTED_INPUT_LIST = (
    "azw", "azw3", "azw4", "azw8", "adoc", "asciidoc", "cb7", "cbc",
    "cbr", "cbz", "chm", "csv", "djv", "djvu", "docm", "docx", "doc",
    "kepub", "epub", "fb2", "fbz", "htm", "html", "htmlz", "ipynb",
    "kfx", "kfx-zip", "kpf", "lit", "lrf", "md", "mobi", "mediawiki",
    "odt", "odp", "ods", "opf", "org", "pdb", "pml", "ppt", "pptx",
    "prc", "rb", "rst", "rtf", "snb", "tcr", "tex", "textile", "tsv",
    "txt", "txtz", "t2t", "typ", "typst", "xls", "xlsm", "xlsx",
    "xhtml", "bok", "pdf",
)

INPUT_FORMATS = frozenset(SUPPORTED_INPUT_LIST)

# Popular formats highlighted with a marker in inline keyboards
HIGHLIGHTED_FORMATS = frozenset({"epub", "mobi", "azw3", "pdf", "docx", "kfx", "md"})

# Telegram Bot API limits
BOT_DOWNLOAD_LIMIT_MB = 20
BOT_UPLOAD_LIMIT_MB = 50


def detect_input_format(file_name: str) -> str:
    """Return the lowercase input format of ``file_name`` or an empty string.

    ``book.fb2.zip`` is reported as ``fbz`` because that is the name Calibre expects.
    """
    name = str(file_name or "").strip().lower()
    if name.endswith(".fb2.zip"):
        return "fbz"
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


def is_supported_input(file_name: str) -> bool:
    return detect_input_format(file_name) in INPUT_FORMATS


def is_same_pandoc_route(input_format: str, output_format: str) -> bool:
    return input_format == output_format or (
        input_format in PANDOC_INPUT_MAP
        and output_format in PANDOC_OUTPUT_MAP
        and PANDOC_INPUT_MAP[input_format] == PANDOC_OUTPUT_MAP[output_format]
    )


def output_choices(input_format: str) -> list[str]:
    """Return valid output formats for ``input_format`` (never offering the identical format)."""
    fmt = (input_format or "").lower().lstrip(".")
    if fmt in ANYDOC_INPUT_FORMATS:
        return [o for o in OUTPUT_FORMATS if o != fmt]
    if fmt in PANDOC_ONLY_INPUT_FORMATS:
        return [o for o in PANDOC_OUTPUT_MAP if not is_same_pandoc_route(fmt, o)]
    if fmt in PANDOC_INPUT_MAP:
        return [o for o in OUTPUT_FORMATS if not is_same_pandoc_route(fmt, o)]
    return [o for o in CALIBRE_OUTPUT_FORMATS if o != fmt]
