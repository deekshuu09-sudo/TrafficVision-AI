from fastapi.testclient import TestClient

from app.main import app


def test_version_reports_render_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")

    response = TestClient(app).get("/version")

    assert response.status_code == 200
    assert response.json() == {"commit": "abc123"}
