from __future__ import annotations

import json
from http.client import HTTPConnection
from threading import Thread

from audioforge.app.server import create_server


def client(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=2)
    return conn, thread


def request(conn, method, path, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload)
    conn.request(method, path, body=body, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    data = response.read()
    return response, json.loads(data) if data else None


def test_state_retrieval_and_bounded_mutation():
    server = create_server(port=0)
    conn, thread = client(server)
    try:
        response, payload = request(conn, "GET", "/api/state")
        assert response.status == 200
        assert payload["state"]["profile"]["name"] == "Club"
        assert payload["status"]["mode"] == "simulation"

        response, payload = request(conn, "POST", "/api/state", {"output_gain_db": 99})
        assert response.status == 200
        assert payload["state"]["output_gain_db"] == 12.0
        assert "clamped" in (payload["state"]["protection"] or "")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_profile_snapshots_actions_and_validation():
    server = create_server(port=0)
    conn, thread = client(server)
    try:
        response, payload = request(conn, "POST", "/api/profile", {"profile": "Cinema"})
        assert response.status == 200
        assert payload["state"]["profile"]["name"] == "Cinema"

        response, payload = request(conn, "POST", "/api/snapshot", {"slot": "a"})
        assert response.status == 200
        response, payload = request(conn, "POST", "/api/action", {"action": "set_gain", "value": 99})
        assert response.status == 200
        assert payload["state"]["output_gain_db"] == 12.0
        request(conn, "POST", "/api/snapshot", {"slot": "b"})
        response, payload = request(conn, "POST", "/api/action", {"action": "compare_ab", "slot": "a"})
        assert response.status == 200
        assert payload["state"]["output_gain_db"] == 0.0

        response, payload = request(conn, "POST", "/api/action", {"action": "set_mute", "value": True})
        assert response.status == 200 and payload["state"]["muted"] is True
        response, payload = request(conn, "POST", "/api/action", {"action": "set_bypass", "value": False})
        assert response.status == 200 and payload["state"]["bypass"] is False

        response, payload = request(conn, "POST", "/api/action", {"action": "nope"})
        assert response.status == 400
        assert payload["error"]["code"] == "validation_error"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_localhost_cors_and_events():
    server = create_server(port=0)
    conn, thread = client(server)
    try:
        conn.request("GET", "/api/events", headers={"Origin": "https://evil.example"})
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert 'event: status' in body
        assert 'event: analyzer' in body
        assert response.getheader("Access-Control-Allow-Origin") is None
        assert response.getheader("Content-Type").startswith("text/event-stream")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
