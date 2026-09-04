import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import auth
from backend.routers import auth as auth_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module.config, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth.config, "ALLOWED_EMAILS", {"ok@x.com"})
    monkeypatch.setattr(auth_router.auth_db.config, "AUTH_DB_PATH", tmp_path / "a.sqlite")
    return TestClient(app_module.app)


def _login_as(monkeypatch, client, email, name="U"):
    monkeypatch.setattr(
        auth_router.auth, "verify_google_token",
        lambda cred: {"email": email, "name": name, "sub": "1"},
    )
    return client.post("/auth/google", json={"credential": "tok"})


# --------------------------------------------------------------------------- #
# /auth/google
# --------------------------------------------------------------------------- #
def test_google_login_allowed_sets_session_and_records(monkeypatch, client, tmp_path):
    r = _login_as(monkeypatch, client, "ok@x.com", "Oki")
    assert r.status_code == 200
    assert r.json() == {"email": "ok@x.com", "name": "Oki"}
    assert client.cookies.get("session")  # signed session cookie

    import sqlite3
    con = sqlite3.connect(tmp_path / "a.sqlite")
    assert con.execute("SELECT sessions FROM users WHERE email='ok@x.com'").fetchone()[0] == 1
    con.close()


def test_google_login_rejects_non_allowlisted(monkeypatch, client):
    r = _login_as(monkeypatch, client, "nope@x.com")
    assert r.status_code == 403


def test_google_login_rejects_bad_token(monkeypatch, client):
    monkeypatch.setattr(
        auth_router.auth, "verify_google_token",
        lambda cred: (_ for _ in ()).throw(auth.AuthError("bad")),
    )
    r = client.post("/auth/google", json={"credential": "tok"})
    assert r.status_code == 401


def test_me_and_logout(monkeypatch, client):
    assert client.get("/auth/me").status_code == 401
    _login_as(monkeypatch, client, "ok@x.com", "Oki")
    assert client.get("/auth/me").json()["email"] == "ok@x.com"
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #
def test_gate_blocks_api_without_session(client):
    r = client.get("/api/v1/reports/footwear/filters/options")
    assert r.status_code == 401


def test_gate_redirects_html_without_session(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/login.html"


def test_gate_allows_after_login(monkeypatch, client):
    _login_as(monkeypatch, client, "ok@x.com")
    assert client.get("/", follow_redirects=False).status_code == 200


def test_login_page_and_auth_config_are_public(client):
    assert client.get("/login.html").status_code == 200
    assert "client_id" in client.get("/auth/config").json()


def test_gate_open_when_auth_disabled(monkeypatch):
    monkeypatch.setattr(app_module.config, "AUTH_ENABLED", False)
    c = TestClient(app_module.app)
    assert c.get("/", follow_redirects=False).status_code == 200
    assert c.get("/auth/me").json()["email"] == "dev@localhost"
