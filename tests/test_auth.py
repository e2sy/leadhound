"""Auth unit tests — scrypt hashes, validation, session lifecycle."""

from __future__ import annotations

import pytest

from leadhound import auth, db


def test_password_hash_roundtrip():
    stored = auth.hash_password("correct horse battery staple")
    assert stored.startswith("scrypt$")
    assert auth.verify_password("correct horse battery staple", stored)
    assert not auth.verify_password("wrong password", stored)


def test_password_hash_is_salted():
    a = auth.hash_password("same-password")
    b = auth.hash_password("same-password")
    assert a != b, "salting must produce different hashes"
    assert auth.verify_password("same-password", a)


def test_verify_rejects_garbage():
    assert not auth.verify_password("x", "not-a-hash")
    assert not auth.verify_password("x", "bcrypt$a$b$c$d$e")


def test_register_creates_account(monkeypatch, tmp_path):
    monkeypatch.setenv("LEADHOUND_HOME", str(tmp_path / "lh"))
    db.ensure_db()
    user = auth.register("Mayank@Example.com ", "hunter2boogaloo")
    assert user["email"] == "mayank@example.com"  # normalized
    assert db.users_count() == 1


def test_register_rejects_duplicates():
    db.ensure_db()
    auth.register("a@b.dev", "longenough1")
    with pytest.raises(auth.AuthError, match="already"):
        auth.register("a@b.dev", "longenough2")


def test_register_validates():
    db.ensure_db()
    with pytest.raises(auth.AuthError, match="email"):
        auth.register("nope", "longenough1")
    with pytest.raises(auth.AuthError, match="8 characters"):
        auth.register("a@b.dev", "short")


def test_login_paths():
    db.ensure_db()
    auth.register("dev@b.dev", "longenough1")
    user = auth.login("dev@b.dev", "longenough1")
    assert user["email"] == "dev@b.dev"
    with pytest.raises(auth.AuthError, match="wrong"):
        auth.login("dev@b.dev", "wrong-password")
    with pytest.raises(auth.AuthError, match="wrong"):
        auth.login("ghost@b.dev", "longenough1")


def test_session_lifecycle():
    db.ensure_db()
    user = auth.register("sess@b.dev", "longenough1")
    token = auth.start_session(user["id"])
    got = auth.user_for_token(token)
    assert got and got["email"] == "sess@b.dev"
    assert auth.user_for_token("bogus-token") is None
    assert auth.user_for_token(None) is None
    auth.end_session(token)
    assert auth.user_for_token(token) is None  # one logout kills the session
