from fastapi.testclient import TestClient
from backend import app as app_module

client = TestClient(app_module.app)


def test_stylesheets_served_with_tokens():
    css = client.get("/chatkit.css")
    assert css.status_code == 200
    assert "--accent" in css.text
    assert client.get("/app.css").status_code == 200
