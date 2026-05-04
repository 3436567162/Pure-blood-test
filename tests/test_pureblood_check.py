import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pureblood_check import (
    build_headers,
    build_probe_result,
    classify_score,
    compute_totals,
    endpoint_url,
    extract_models_payload,
    inspect_chat_success_payload,
    inspect_error_payload,
    inspect_responses_success_payload,
    inspect_stream_lines,
    make_check_payload,
    make_report_payload,
    normalize_base_url,
    parse_args,
    render_summary,
    run_report,
)


def test_normalize_base_url_adds_v1_once():
    assert normalize_base_url("https://relay.example.com") == "https://relay.example.com/v1"
    assert normalize_base_url("https://relay.example.com/") == "https://relay.example.com/v1"
    assert normalize_base_url("https://relay.example.com/v1") == "https://relay.example.com/v1"
    assert normalize_base_url("https://relay.example.com/v1/") == "https://relay.example.com/v1"


def test_endpoint_url_appends_relative_path():
    assert endpoint_url("https://relay.example.com/v1", "/chat/completions") == (
        "https://relay.example.com/v1/chat/completions"
    )


def test_classify_score_uses_three_buckets():
    assert classify_score(85) == "High probability native"
    assert classify_score(60) == "Suspicious; compatibility layer or response rewriting likely"
    assert classify_score(30) == "Clearly non-native"


def test_render_summary_includes_verdict_and_checks():
    report = render_summary(
        base_url="https://relay.example.com/v1",
        model="gpt-4.1",
        stream_enabled=True,
        total_score=72,
        max_score=100,
        results=[
            {
                "endpoint": "chat/completions",
                "probe": "success",
                "passed": 2,
                "total": 3,
                "checks": [("status_200", True, "HTTP 200"), ("has_usage", False, "missing usage")],
            }
        ],
    )

    assert "High probability native" not in report
    assert "Suspicious; compatibility layer or response rewriting likely" in report
    assert "chat/completions success" in report
    assert "PASS status_200" in report
    assert "FAIL has_usage" in report


def test_normalize_base_url_rejects_non_http_values():
    import pytest

    with pytest.raises(ValueError):
        normalize_base_url("relay.example.com")


def test_build_probe_result_counts_passed_checks():
    result = build_probe_result(
        endpoint="responses",
        probe="success",
        checks=[
            ("status_200", True, "HTTP 200"),
            ("has_output", True, "output list present"),
            ("has_usage", False, "usage missing"),
        ],
        weight=20,
    )

    assert result["passed"] == 2
    assert result["total"] == 3
    assert result["earned_score"] == 13
    assert result["max_score"] == 20


def test_compute_totals_adds_all_probe_scores():
    totals = compute_totals(
        [
            {"earned_score": 13, "max_score": 20},
            {"earned_score": 10, "max_score": 10},
            {"earned_score": 0, "max_score": 15},
        ]
    )

    assert totals == (23, 45)


def test_inspect_chat_success_payload_accepts_openai_like_shape():
    checks = inspect_chat_success_payload(
        200,
        {
            "id": "chatcmpl-abc",
            "object": "chat.completion",
            "model": "gpt-4.1",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )

    assert all(ok for _, ok, _ in checks)


def test_inspect_responses_success_payload_flags_missing_output():
    checks = inspect_responses_success_payload(
        200,
        {
            "id": "resp_123",
            "object": "response",
            "status": "completed",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        },
    )

    failures = {name for name, ok, _ in checks if not ok}
    assert "has_output" in failures


def test_inspect_error_payload_accepts_openai_style_error_object():
    checks = inspect_error_payload(
        400,
        {
            "error": {
                "message": "Invalid request",
                "type": "invalid_request_error",
                "param": "model",
                "code": "bad_value",
            }
        },
    )

    failures = {name for name, ok, _ in checks if not ok}
    assert "has_error_object" not in failures
    assert "has_error_message" not in failures


def test_build_headers_sets_bearer_authorization():
    headers = build_headers("sk-test")
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"


def test_inspect_stream_lines_detects_done_marker():
    checks = inspect_stream_lines(
        200,
        "text/event-stream; charset=utf-8",
        [
            'data: {"id":"chatcmpl-1","object":"chat.completion.chunk"}',
            "data: [DONE]",
        ],
    )

    failures = {name for name, ok, _ in checks if not ok}
    assert "content_type_event_stream" not in failures
    assert "has_data_lines" not in failures
    assert "has_done_marker" not in failures


def test_parse_args_supports_stream_flag_and_timeout():
    args = parse_args(
        [
            "--base-url",
            "https://relay.example.com",
            "--api-key",
            "sk-test",
            "--model",
            "gpt-4.1",
            "--stream",
            "--timeout",
            "12",
        ]
    )

    assert args.base_url == "https://relay.example.com"
    assert args.api_key == "sk-test"
    assert args.model == "gpt-4.1"
    assert args.stream is True
    assert args.timeout == 12


def test_make_check_payload_serializes_tuple_check():
    payload = make_check_payload(("status_200", True, "HTTP 200"))
    assert payload == {"name": "status_200", "ok": True, "detail": "HTTP 200"}


def test_make_report_payload_builds_structured_dashboard_result():
    report = make_report_payload(
        base_url="https://relay.example.com/v1",
        model="gpt-5.4",
        stream_enabled=True,
        results=[
            {
                "endpoint": "responses",
                "probe": "success",
                "passed": 6,
                "total": 6,
                "earned_score": 25,
                "max_score": 25,
                "checks": [("status_200", True, "HTTP 200")],
            }
        ],
        checked_at="2026-05-04T12:00:00Z",
    )

    assert report["target"] == "https://relay.example.com/v1"
    assert report["model"] == "gpt-5.4"
    assert report["stream_enabled"] is True
    assert report["percent"] == 100
    assert report["verdict"] == "High probability native"
    assert report["results"][0]["checks"][0]["name"] == "status_200"


def test_run_report_uses_supplied_probe_runner():
    report = run_report(
        base_url="https://relay.example.com/v1",
        api_key="sk-test",
        model="gpt-5.4",
        stream_enabled=False,
        timeout=10,
        checked_at="2026-05-04T12:00:00Z",
        probe_runner=lambda base_url, api_key, model, stream_enabled, timeout: [
            {
                "endpoint": "chat/completions",
                "probe": "success",
                "passed": 8,
                "total": 8,
                "earned_score": 15,
                "max_score": 15,
                "checks": [("status_200", True, "HTTP 200")],
            }
        ],
    )

    assert report["total_score"] == 15
    assert report["max_score"] == 15
    assert report["results"][0]["checks"][0]["detail"] == "HTTP 200"


def test_extract_models_payload_flattens_model_ids():
    payload = extract_models_payload(
        "https://relay.example.com/v1",
        {
            "object": "list",
            "data": [
                {"id": "gpt-5.4", "type": "model"},
                {"id": "gpt-4.1", "type": "model"},
            ],
        },
    )

    assert payload["target"] == "https://relay.example.com/v1"
    assert payload["models"][0]["id"] == "gpt-5.4"
    assert payload["models"][1]["id"] == "gpt-4.1"
