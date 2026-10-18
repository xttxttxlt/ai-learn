from app.utils.text_cleaner import MAX_INPUT_LEN, clean_user_input


def test_trims_and_collapses_spaces():
    assert clean_user_input("  hello   world  ") == "hello world"


def test_normalizes_newlines():
    assert clean_user_input("a\r\nb\rc") == "a\nb\nc"


def test_collapses_extra_blank_lines():
    assert clean_user_input("a\n\n\n\nb") == "a\n\nb"


def test_handles_none():
    assert clean_user_input(None) == ""


def test_truncates_over_max_length():
    text = "x" * (MAX_INPUT_LEN + 100)
    assert len(clean_user_input(text)) == MAX_INPUT_LEN
