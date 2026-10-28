from modules.converter import formats as f


def test_input_table_matches_standalone_module():
    assert len(f.INPUT_FORMATS) == 61  # the standalone module's 62 minus the unsupported .bok
    assert "bok" not in f.INPUT_FORMATS
    assert {"doc", "xls", "pptx", "kfx", "pdf", "md"} <= f.INPUT_FORMATS


def test_output_table_is_31_formats_and_all_get_a_button_slot():
    assert len(f.OUTPUT_FORMATS) == 31
    assert set(f.OUTPUT_FORMATS) == set(f.CALIBRE_OUTPUTS) | set(f.PANDOC_ONLY_OUTPUTS) | {"kfx"}


def test_epub_gets_calibre_and_pandoc_outputs():
    out = f.output_choices("epub")
    assert "mobi" in out and "md" in out and "docx" in out
    assert "epub" not in out
    assert "kfx" not in out                      # opt-in
    assert "kfx" in f.output_choices("epub", kfx=True)


def test_same_pandoc_route_is_hidden():
    assert "adoc" not in f.output_choices("asciidoc")   # same Pandoc format, different extension
    assert "typst" not in f.output_choices("typ")
    assert "tex" not in f.output_choices("tex")
    assert "typ" not in f.output_choices("typst")


def test_pandoc_only_inputs_only_get_pandoc_outputs():
    out = set(f.output_choices("rst"))
    assert out <= set(f.PANDOC_OUTPUT_MAP)
    assert "mobi" not in out and "docx" in out


def test_backends_can_be_switched_off():
    no_pandoc = f.output_choices("epub", pandoc=False)
    assert "md" not in no_pandoc and "mobi" in no_pandoc
    only_pandoc = f.output_choices("epub", calibre=False)
    assert "mobi" not in only_pandoc and "md" in only_pandoc
    assert f.output_choices("rst", pandoc=False) == []


def test_legacy_office_goes_through_markdown():
    assert f.effective_input("doc") == "md"
    assert f.effective_input("pdf") == "htmlz"
    assert f.effective_input("kfx") == "epub"
    assert "mobi" in f.output_choices("doc") and "md" in f.output_choices("doc")


def test_backend_for():
    assert f.backend_for("epub", "mobi") == "calibre"
    assert f.backend_for("epub", "md") == "pandoc"
    assert f.backend_for("rst", "docx") == "pandoc"
    assert f.backend_for("epub", "kfx") == "kfx"
    assert f.backend_for("pdf", "epub") == "calibre"
