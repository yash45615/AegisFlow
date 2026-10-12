
import json
import logging

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.observability import RequestObservabilityMiddleware


def make_test_app():
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware)

    @app.get("/test")
    def test_route(request: Request):
        return {
            "request_id": request.state.request_id,
            "status": "ok",
        }

    @app.get("/failure")
    def failure_route():
        raise RuntimeError("sensitive example message")

    return app


def test_response_contains_request_id():
    client = TestClient(make_test_app())

    response = client.get("/test")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_valid_incoming_request_id_is_preserved():
    client = TestClient(make_test_app())

    response = client.get(
        "/test",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_invalid_incoming_request_id_is_replaced():
    client = TestClient(make_test_app())

    response = client.get(
        "/test",
        headers={"X-Request-ID": "invalid request id with spaces"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != (
        "invalid request id with spaces"
    )


def test_structured_log_contains_request_metadata(caplog):
    client = TestClient(make_test_app())

    with caplog.at_level(logging.INFO, logger="aegisflow.access"):
        response = client.get("/test")

    assert response.status_code == 200

    records = [
        record for record in caplog.records
        if record.name == "aegisflow.access"
    ]
    assert records

    log_data = json.loads(records[-1].message)
    assert log_data["event"] == "http_request"
    assert log_data["status_code"] == 200
    assert log_data["request_id"] == response.headers["X-Request-ID"]
    assert isinstance(log_data["duration_ms"], (int, float))


def test_logs_do_not_include_query_string(caplog):
    client = TestClient(make_test_app())

    with caplog.at_level(logging.INFO, logger="aegisflow.access"):
        response = client.get("/test?token=do-not-log-this")

    assert response.status_code == 200
    assert "do-not-log-this" not in caplog.text
