from __future__ import annotations

import json
from http.client import HTTPConnection
from threading import Thread

from audioforge.app.engine import start_engine
from audioforge.app.pipewire import PipeWireAdapter
from audioforge.app.server import create_server
from audioforge.app.state import create_default_state


def request(conn: HTTPConnection, method: str, path: str, payload=None):
    body = None if payload is None else json.dumps(payload)
    conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    raw = response.read()
    return response, json.loads(raw) if raw else None


def running_server(**kwargs):
    server = create_server(port=0, **kwargs)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, HTTPConnection(*server.server_address, timeout=2)


def close_server(server, thread, conn):
    conn.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_startup_is_safe_and_explicitly_simulated():
    server, thread, conn = running_server()
    try:
        response, payload = request(conn, "GET", "/api/state")
        assert response.status == 200
        assert payload["status"]["mode"] == "simulation"
        assert payload["status"]["label"] == "SIMULATION / PipeWire unavailable"
        assert payload["status"]["filter_chain_available"] is False
        assert payload["state"]["bypass"] is True
        assert payload["status"]["bypass"] is True
    finally:
        close_server(server, thread, conn)


def test_club_and_cinema_switching_preserves_safe_output():
    server, thread, conn = running_server()
    try:
        response, club = request(conn, "GET", "/api/state")
        assert response.status == 200 and club["state"]["profile"]["name"] == "Club"
        response, cinema = request(conn, "POST", "/api/profile", {"profile": "Cinema"})
        assert response.status == 200
        assert cinema["state"]["profile"]["name"] == "Cinema"
        assert cinema["state"]["bypass"] is True
        response, club = request(conn, "POST", "/api/profile", {"profile": "Club"})
        assert response.status == 200
        assert club["state"]["profile"]["name"] == "Club"
        assert club["state"]["bypass"] is True
    finally:
        close_server(server, thread, conn)


def test_chill_switching_preserves_safe_output_and_preset_profile(tmp_path):
    server, thread, conn = running_server(preset_dir=tmp_path)
    try:
        response, payload = request(conn, "POST", "/api/profile", {"profile": "Chill"})
        assert response.status == 200
        assert payload["state"]["profile"]["description"].startswith("Deep, controlled bass")
        request(conn, "POST", "/api/action", {"action": "save_preset", "name": "chill"})
        request(conn, "POST", "/api/profile", {"profile": "Club"})
        response, restored = request(conn, "POST", "/api/action", {"action": "load_preset", "name": "chill"})
        assert response.status == 200
        assert restored["state"]["profile"]["name"] == "Chill"
        assert restored["state"]["modules"]["imaging"]["parameters"]["width"] == 1.08
    finally:
        close_server(server, thread, conn)


def test_ab_snapshots_are_isolated_complete_states():
    server, thread, conn = running_server()
    try:
        request(conn, "POST", "/api/action", {"action": "set_gain", "value": 4})
        request(conn, "POST", "/api/action", {"action": "set_eq", "parameters": {"low_db": 6}})
        response, _ = request(conn, "POST", "/api/action", {"action": "snapshot_a"})
        assert response.status == 200
        request(conn, "POST", "/api/action", {"action": "set_gain", "value": -4})
        request(conn, "POST", "/api/action", {"action": "set_eq", "parameters": {"low_db": -6}})
        response, restored = request(conn, "POST", "/api/action", {"action": "compare_ab", "slot": "a"})
        assert response.status == 200
        assert restored["state"]["output_gain_db"] == 4.0
        assert restored["state"]["modules"]["eq"]["parameters"]["low_db"] == 6.0
    finally:
        close_server(server, thread, conn)


def test_bypass_and_mute_remain_visible_and_safe():
    server, thread, conn = running_server()
    try:
        response, payload = request(conn, "POST", "/api/action", {"action": "set_bypass", "value": False})
        assert response.status == 200 and payload["state"]["bypass"] is True
        response, payload = request(conn, "POST", "/api/action", {"action": "set_mute", "value": True})
        assert response.status == 200
        assert payload["state"]["muted"] is True and payload["status"]["muted"] is True
        assert payload["status"]["protection"]
    finally:
        close_server(server, thread, conn)


def test_missing_pipewire_reports_fallback_without_traceback():
    def missing(_argv):
        raise FileNotFoundError("pw-dump")

    state = create_default_state()
    status = start_engine(state, PipeWireAdapter(runner=missing))
    assert status.mode == "fallback"
    assert status.filter_chain_available is False
    assert state.bypass is True
    assert "pw-dump unavailable" in (status.reason or "")


def test_preset_round_trip_restores_state_and_is_listed(tmp_path):
    server, thread, conn = running_server(preset_dir=tmp_path)
    try:
        request(conn, "POST", "/api/action", {"action": "set_gain", "value": 4})
        request(conn, "POST", "/api/action", {"action": "loudness_match", "value": True})
        response, saved = request(conn, "POST", "/api/action", {"action": "save_preset", "name": "smoke"})
        assert response.status == 200
        request(conn, "POST", "/api/action", {"action": "set_gain", "value": -4})
        response, loaded = request(conn, "POST", "/api/action", {"action": "load_preset", "name": "smoke"})
        assert response.status == 200 and loaded["state"]["output_gain_db"] == 4.0
        assert loaded["state"]["loudness_match"] is True
        response, presets = request(conn, "GET", "/api/presets")
        assert response.status == 200 and presets["presets"] == ["smoke"]
        assert saved["state"]["output_gain_db"] == 4.0
    finally:
        close_server(server, thread, conn)
