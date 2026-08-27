from ahmadnl.services.pdf import normalize_text, validate_pdf_name


def test_normalize_text_collapses_spaces_and_blank_lines():
    assert normalize_text("A   B\n\n\nC") == "A B\n\nC"


def test_validate_pdf_name_accepts_pdf_mime():
    validate_pdf_name("paper.pdf", "application/pdf")
