from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from pureblood_check import fetch_models, normalize_base_url, run_report


def create_app(probe_service=None, models_service=None) -> Flask:
    app = Flask(__name__)

    probe_service = probe_service or (
        lambda base_url, api_key, model, stream_enabled, timeout: run_report(
            base_url=base_url,
            api_key=api_key,
            model=model,
            stream_enabled=stream_enabled,
            timeout=timeout,
        )
    )
    models_service = models_service or (
        lambda base_url, api_key: fetch_models(base_url=base_url, api_key=api_key)
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/models")
    def api_models():
        payload = request.get_json(silent=True) or {}
        try:
            base_url = normalize_base_url(str(payload.get("base_url", "")))
            api_key = str(payload.get("api_key", "")).strip()
            if not api_key:
                raise ValueError("api_key is required")
            result = models_service(base_url, api_key)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": "models_request_failed", "detail": str(exc)}), 400

    @app.post("/api/check")
    def api_check():
        payload = request.get_json(silent=True) or {}
        try:
            base_url = normalize_base_url(str(payload.get("base_url", "")))
            api_key = str(payload.get("api_key", "")).strip()
            model = str(payload.get("model", "")).strip()
            stream_enabled = bool(payload.get("stream", False))
            timeout = int(payload.get("timeout", 30))
            if not api_key:
                raise ValueError("api_key is required")
            if not model:
                raise ValueError("model is required")
            result = probe_service(base_url, api_key, model, stream_enabled, timeout)
            return jsonify({"ok": True, **result})
        except Exception as exc:
            return jsonify({"ok": False, "error": "check_failed", "detail": str(exc)}), 400

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
