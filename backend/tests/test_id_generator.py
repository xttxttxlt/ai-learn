from app.utils.id_generator import generate_quiz_id


def test_has_prefix():
    assert generate_quiz_id().startswith("quiz_")


def test_ids_are_unique():
    ids = {generate_quiz_id() for _ in range(200)}
    assert len(ids) == 200


def test_length():
    assert len(generate_quiz_id()) == len("quiz_") + 16
