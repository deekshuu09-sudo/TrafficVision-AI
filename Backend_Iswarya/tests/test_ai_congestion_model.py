"""AI Engine M4: /ai-engine/api/v1/predict/congestion uses model-v1 on the latest DB reading."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

ENDPOINT = "/ai-engine/api/v1/predict/congestion"


def _ai_route_function():
    ai_app = next(r.app for r in app.routes if getattr(r, "path", None) == "/ai-engine")
    path = "/api/v1/predict/congestion"
    route = next(r for r in ai_app.routes if getattr(r, "path", None) == path)
    return route.endpoint


class _Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params):
        self.params = params

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return _Cursor(self.row)

    def close(self):
        pass


@pytest.fixture
def service_globals():
    endpoint = _ai_route_function()
    return endpoint.__globals__["get_congestion_prediction"].__globals__


def test_prediction_comes_from_trained_model(monkeypatch, service_globals):
    row = ("R001", 28, 42.9, 5.6, datetime(2026, 8, 26, 22, 0), 120, 5.0)
    monkeypatch.setitem(service_globals, "get_postgres_connection", lambda: _Connection(row))

    response = TestClient(app).get(ENDPOINT, params={"road_id": "R001"})

    assert response.status_code == 200
    body = response.json()
    assert body["road_id"] == "R001"
    assert body["generated_by"] == "model-v1"
    assert body["predicted_level"] in {"Low", "Medium", "High", "Severe"}
    assert 0 < body["confidence"] <= 1


def test_unknown_road_is_404(monkeypatch, service_globals):
    monkeypatch.setitem(service_globals, "get_postgres_connection", lambda: _Connection(None))

    assert TestClient(app).get(ENDPOINT, params={"road_id": "R999"}).status_code == 404


def test_database_failure_is_503(monkeypatch, service_globals):
    def broken():
        raise RuntimeError("database unreachable")

    monkeypatch.setitem(service_globals, "get_postgres_connection", broken)

    assert TestClient(app).get(ENDPOINT, params={"road_id": "R001"}).status_code == 503
