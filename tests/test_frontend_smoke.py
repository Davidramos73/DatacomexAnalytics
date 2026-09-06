from fastapi.testclient import TestClient
from backend import app as app_module

client = TestClient(app_module.app)


def test_stylesheets_served_with_tokens():
    css = client.get("/chatkit.css")
    assert css.status_code == 200
    assert "--accent" in css.text
    assert client.get("/app.css").status_code == 200


def test_index_is_thin_and_imports_module():
    html = client.get("/").text
    assert 'type="module"' in html
    assert "chatkit.js" in html
    assert len(html) < 4000  # the shell is thin now
    js = client.get("/chatkit.js")
    assert js.status_code == 200
    assert "export function boot" in js.text or "export async function boot" in js.text


def test_login_is_thin_and_imports_module():
    html = client.get("/login.html").text
    assert 'type="module"' in html
    assert "mountLogin" in html
    assert "accounts.google.com/gsi/client" in html
    assert "<script>" not in html  # no inline logic left
