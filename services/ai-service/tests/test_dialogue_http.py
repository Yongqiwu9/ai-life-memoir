"""ASGI source prepared; run only under separately authorized HTTP verification."""

import pytest
from fastapi.testclient import TestClient
from test_dialogue_wire import request

from app.dialogue.http import create_app
from app.dialogue.mock import DeterministicDialogueMock


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "Bearer synthetic-test"}, 200),
    ],
)
def test_internal_asgi_auth_and_bound_reply(headers, expected):
    app = create_app(
        credential="synthetic-test",
        allocation=lambda _: True,
        provider=DeterministicDialogueMock(),
        max_request_bytes=100_000,
        max_response_bytes=100_000,
    )
    with TestClient(app) as client:
        data = request()
        response = client.post(
            "/internal/v1/dialogue/initialize", content=data.model_dump_json(), headers=headers
        )
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["input_digest"] == data.input_digest


def test_internal_default_closed_and_no_error_body_leak():
    with TestClient(create_app()) as client:
        response = client.post("/internal/v1/dialogue/initialize", content="synthetic-secret")
    assert response.status_code == 503 and "synthetic-secret" not in response.text


@pytest.mark.parametrize("body,expected", [(b"x" * 201, 413), (b'{"secret":"do-not-echo"}', 422)])
def test_internal_body_limits_and_validation_privacy(body, expected):
    app = create_app(
        credential="synthetic-test",
        allocation=lambda _: True,
        max_request_bytes=200,
        max_response_bytes=1000,
    )
    with TestClient(app) as client:
        response = client.post(
            "/internal/v1/dialogue/initialize",
            content=body,
            headers={"Authorization": "Bearer synthetic-test"},
        )
    assert response.status_code == expected and "do-not-echo" not in response.text
