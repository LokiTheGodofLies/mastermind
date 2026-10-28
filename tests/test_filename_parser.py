from modules.indexing.book_fetcher import parse_filename_metadata


def test_brackets_series_and_author():
    m = parse_filename_metadata("The Striker {Gods of the Game 1} Ana Huang.epub")
    assert m["title"] == "The Striker"
    assert m["author"] == "Ana Huang"
    assert "Gods of the Game" in m["series"]


def test_by_pattern():
    m = parse_filename_metadata("Dune by Frank Herbert.pdf")
    assert (m["title"], m["author"]) == ("Dune", "Frank Herbert")


def test_dash_pattern():
    m = parse_filename_metadata("Dune - Frank Herbert.epub")
    assert (m["title"], m["author"]) == ("Dune", "Frank Herbert")


def test_empty():
    assert parse_filename_metadata("")["title"] == "Unknown Title"
