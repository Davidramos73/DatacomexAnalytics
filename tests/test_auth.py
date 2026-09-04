import pytest

from backend import auth


@pytest.fixture
def allowlist(monkeypatch):
    monkeypatch.setattr(auth.config, "ALLOWED_EMAILS", {"a@x.com", "b@x.com"})


# --------------------------------------------------------------------------- #
# is_allowed
# --------------------------------------------------------------------------- #
def test_is_allowed_is_case_insensitive(allowlist):
    assert auth.is_allowed("A@X.com")
    assert auth.is_allowed("b@x.com")


def test_is_allowed_rejects_unlisted(allowlist):
    assert not auth.is_allowed("c@x.com")


def test_is_allowed_empty_list_allows_nobody(monkeypatch):
    monkeypatch.setattr(auth.config, "ALLOWED_EMAILS", set())
    assert not auth.is_allowed("a@x.com")


# --------------------------------------------------------------------------- #
# verify_google_token
# --------------------------------------------------------------------------- #
def _patch_verify(monkeypatch, info):
    from google.oauth2 import id_token

    def fake(credential, request, client_id, **kw):
        if info is None:
            raise ValueError("bad token")
        return info

    monkeypatch.setattr(id_token, "verify_oauth2_token", fake)


def test_verify_google_token_returns_identity(monkeypatch):
    _patch_verify(monkeypatch, {
        "email": "Person@X.com", "email_verified": True,
        "name": "Person", "sub": "123",
    })
    out = auth.verify_google_token("tok")
    assert out == {"email": "person@x.com", "name": "Person", "sub": "123"}


def test_verify_google_token_rejects_unverified_email(monkeypatch):
    _patch_verify(monkeypatch, {
        "email": "p@x.com", "email_verified": False, "name": "P", "sub": "1",
    })
    with pytest.raises(auth.AuthError):
        auth.verify_google_token("tok")


def test_verify_google_token_wraps_verifier_failure(monkeypatch):
    _patch_verify(monkeypatch, None)
    with pytest.raises(auth.AuthError):
        auth.verify_google_token("tok")


# --------------------------------------------------------------------------- #
# auth_db.record_login
# --------------------------------------------------------------------------- #
def test_record_login_upserts_and_logs(tmp_path, monkeypatch):
    from backend import auth_db

    db = tmp_path / "auth.sqlite"
    monkeypatch.setattr(auth_db.config, "AUTH_DB_PATH", db)

    auth_db.record_login("a@x.com", "Ana", "UA/1")
    auth_db.record_login("a@x.com", "Ana Updated", "UA/2")

    con = auth_db._connect()
    try:
        row = con.execute(
            "SELECT name, sessions, first_seen, last_seen FROM users WHERE email = ?",
            ("a@x.com",),
        ).fetchone()
        assert row[0] == "Ana Updated"
        assert row[1] == 2                      # sessions incremented
        assert row[2] < row[3] or row[2] == row[3]  # first_seen <= last_seen
        (n,) = con.execute(
            "SELECT COUNT(*) FROM session_log WHERE email = ?", ("a@x.com",)
        ).fetchone()
        assert n == 2
    finally:
        con.close()
