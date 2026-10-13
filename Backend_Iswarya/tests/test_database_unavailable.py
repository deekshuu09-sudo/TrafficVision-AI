"""DEF-M4-022: a missing or failing traffic database is reported as 503, not sample data."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import traffic_service

ENDPOINTS = [
    "/api/v1/traffic/live",
    "/api/v1/traffic/road/R001",
    "/api/v1/traffic/density",
    "/api/v1/traffic/history",
    "/api/v1/traffic/aggregate",
    "/api/v1/traffic/road-condition/R001",
]


class _BrokenConnection:
    def cursor(self):
        raise RuntimeError('relation "traffic_readings" does not exist')

    def close(self):
        pass


@pytest.mark.parametrize("connection", [None, _BrokenConnection()], ids=["no-conn", "query-fails"])
@pytest.mark.parametrize("path", ENDPOINTS)
def test_traffic_endpoints_return_503_without_database(monkeypatch, path, connection):
    monkeypatch.setattr(traffic_service, "get_postgres_connection", lambda: connection)

    response = TestClient(app).get(path)

    assert response.status_code == 503
    assert response.json() == {"detail": "Traffic database unavailable"}
