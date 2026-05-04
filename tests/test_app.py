import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app


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
