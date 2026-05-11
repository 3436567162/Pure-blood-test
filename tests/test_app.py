import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app import choose_available_port, create_app, main


def test_check_endpoint_returns_structured_report():
    app = create_app(
        probe_service=lambda base_url, api_key, model, stream_enabled, timeout: {
            "target": base_url,
            "model": model,
            "stream_enabled": stream_enabled,
            "checked_at": "2026-05-04T12:00:00Z",
            "total_score": 97,
            "max_score": 100,
            "percent": 97,
            "verdict": "High probability native",
            "results": [],
        },
        models_service=lambda base_url, api_key: {
            "ok": True,
            "target": base_url,
            "models": [{"id": "gpt-5.4", "raw": {"id": "gpt-5.4"}}],
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/check",
        json={
            "base_url": "https://relay.example.com",
            "api_key": "sk-test",
            "model": "gpt-5.4",
            "stream": True,
            "timeout": 20,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.get_json()["verdict"] == "High probability native"


def test_models_endpoint_returns_model_list():
    app = create_app(
        probe_service=lambda *args, **kwargs: None,
        models_service=lambda base_url, api_key: {
            "ok": True,
            "target": base_url,
            "models": [{"id": "gpt-5.4", "raw": {"id": "gpt-5.4"}}],
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/models",
        json={"base_url": "https://relay.example.com", "api_key": "sk-test"},
    )

    assert response.status_code == 200
    assert response.get_json()["models"][0]["id"] == "gpt-5.4"


def test_index_route_renders_dashboard_shell():
    app = create_app(
        probe_service=lambda *args, **kwargs: {},
        models_service=lambda *args, **kwargs: {},
    )
    client = app.test_client()

    response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "中转协议取证台" in body
    assert "开始检测" in body


def test_index_route_includes_frontend_mount_points():
    app = create_app(
        probe_service=lambda *args, **kwargs: {},
        models_service=lambda *args, **kwargs: {},
    )
    client = app.test_client()

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert 'id="check-form"' in body
    assert 'id="summary-panel"' in body
    assert 'id="probe-grid"' in body
    assert 'id="details-panel"' in body


def test_choose_available_port_prefers_requested_port():
    selected = choose_available_port(
        start_port=5000,
        max_attempts=3,
        port_available=lambda host, port: port == 5000,
    )

    assert selected == 5000


def test_choose_available_port_falls_forward_when_preferred_port_is_busy():
    selected = choose_available_port(
        start_port=5000,
        max_attempts=4,
        port_available=lambda host, port: port == 5002,
    )

    assert selected == 5002


def test_choose_available_port_raises_when_no_port_is_free():
    with pytest.raises(RuntimeError):
        choose_available_port(
            start_port=5000,
            max_attempts=2,
            port_available=lambda host, port: False,
        )


def test_main_runs_app_on_selected_port():
    messages = []

    class FakeApp:
        def __init__(self):
            self.calls = []

        def run(self, host, port, debug):
            self.calls.append({"host": host, "port": port, "debug": debug})

    fake_app = FakeApp()

    selected_port = main(
        app_factory=lambda: fake_app,
        port_selector=lambda host, start_port, max_attempts: 5003,
        printer=messages.append,
    )

    assert selected_port == 5003
    assert fake_app.calls == [{"host": "127.0.0.1", "port": 5003, "debug": False}]
    assert messages == ["Server running at http://127.0.0.1:5003/"]
