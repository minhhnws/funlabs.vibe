from __future__ import annotations

import json
from http.client import HTTPConnection
from threading import Thread
from pathlib import Path

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
        assert response.status == 200 and payload["state"]["bypass"] is True
        assert payload["status"]["mode"] == "simulation"

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


def test_schema_versions_and_positive_cors_preflight():
    server = create_server(port=0)
    conn, thread = client(server)
    try:
        response, payload = request(conn, "GET", "/api/state")
        assert payload["api_version"] == "1.0"
        assert payload["state_schema_version"] == 1
        conn.request("OPTIONS", "/api/action", headers={"Origin": "http://localhost:3000"})
        response = conn.getresponse()
        response.read()
        assert response.status == 204
        assert response.getheader("Access-Control-Allow-Origin") == "http://localhost:3000"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_controls_are_bounded_and_reject_wrong_types_and_slots():
    server = create_server(port=0)
    conn, thread = client(server)
    try:
        for action, payload in [
            ("set_eq", {"action": "set_eq", "parameters": {"low_db": 99}}),
            ("set_dynamics", {"action": "set_dynamics", "parameters": {"ratio": 99}}),
            ("set_width", {"action": "set_width", "value": 99}),
        ]:
            response, payload = request(conn, "POST", "/api/action", payload)
            assert response.status == 200, action
        response, payload = request(conn, "GET", "/api/state")
        assert payload["state"]["modules"]["eq"]["parameters"]["low_db"] == 12.0
        assert payload["state"]["modules"]["compressor"]["parameters"]["ratio"] == 20.0
        assert payload["state"]["modules"]["imaging"]["parameters"]["width"] == 1.5
        for bad in [
            {"action": "set_mute", "value": "false"},
            {"action": "set_module", "module": "eq", "enabled": 1},
            {"action": "set_gain", "value": "2"},
            {"action": "set_eq", "parameters": {"unknown": 1}},
            {"action": "compare_ab", "slot": "c"},
        ]:
            response, payload = request(conn, "POST", "/api/action", bad)
            assert response.status == 400, bad
        response, payload = request(conn, "POST", "/api/snapshot", {"slot": "c"})
        assert response.status == 400
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_presets_round_trip_and_status_transitions(tmp_path: Path):
    server = create_server(port=0, preset_dir=tmp_path)
    conn, thread = client(server)
    try:
        response, payload = request(conn, "POST", "/api/action", {"action": "set_gain", "value": 4})
        assert response.status == 200
        response, payload = request(conn, "POST", "/api/action", {"action": "save_preset", "name": "smoke"})
        assert response.status == 200
        response, payload = request(conn, "POST", "/api/action", {"action": "set_gain", "value": -4})
        response, payload = request(conn, "POST", "/api/action", {"action": "load_preset", "name": "smoke"})
        assert response.status == 200 and payload["state"]["output_gain_db"] == 4.0
        response, payload = request(conn, "POST", "/api/action", {"action": "set_bypass", "value": False})
        assert response.status == 200
        assert payload["state"]["bypass"] is True
        assert payload["status"]["mode"] == "simulation"
        assert payload["status"]["bypass"] is True
        response, payload = request(conn, "POST", "/api/action", {"action": "set_mute", "value": True})
        assert payload["state"]["muted"] is True
        assert payload["status"]["muted"] is True
        assert payload["status"]["protection"]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
