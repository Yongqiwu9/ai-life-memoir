from app.core.security import hash_password, verify_password


def test_password_is_hashed_not_plaintext() -> None:
    password = "s3cret-password"
    hashed = hash_password(password)

    assert hashed != password
    assert password not in hashed
    assert hashed.startswith("$2")


def test_verify_password() -> None:
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("", hashed) is False
