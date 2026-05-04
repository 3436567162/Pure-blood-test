from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any


Check = tuple[str, bool, str]
ProbeResult = dict[str, Any]

SUCCESS_PROMPT = "Reply with exactly OK."
STREAM_PROMPT = "Count from 1 to 3, one token at a time if possible."

PROBE_WEIGHTS = {
    "chat_success": 15,
    "chat_error": 15,
    "responses_success": 25,
    "responses_error": 20,
    "chat_stream": 10,
    "responses_stream": 15,
}


def normalize_base_url(base_url: str) -> str:
    stripped = base_url.strip().rstrip("/")
    if not stripped.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    if stripped.endswith("/v1"):
        return stripped
    return f"{stripped}/v1"


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url}{path}"


def classify_score(percent: int) -> str:
    if percent >= 75:
        return "High probability native"
    if percent >= 45:
        return "Suspicious; compatibility layer or response rewriting likely"
    return "Clearly non-native"


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def build_probe_result(endpoint: str, probe: str, checks: list[Check], weight: int) -> ProbeResult:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    earned_score = 0 if total == 0 else round(weight * passed / total)
    return {
        "endpoint": endpoint,
        "probe": probe,
        "checks": checks,
        "passed": passed,
        "total": total,
        "earned_score": earned_score,
        "max_score": weight,
    }


def compute_totals(results: list[ProbeResult]) -> tuple[int, int]:
    return (
        sum(int(item["earned_score"]) for item in results),
        sum(int(item["max_score"]) for item in results),
    )


def inspect_chat_success_payload(status_code: int, payload: Any) -> list[Check]:
    choices = payload.get("choices") if isinstance(payload, dict) else None
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else {}
    usage = payload.get("usage") if isinstance(payload, dict) else None
    return [
        ("status_200", status_code == 200, f"HTTP {status_code}"),
        (
            "object_chat_completion",
            isinstance(payload, dict) and payload.get("object") == "chat.completion",
            f"object={payload.get('object') if isinstance(payload, dict) else type(payload).__name__}",
        ),
        (
            "id_present",
            isinstance(payload, dict) and isinstance(payload.get("id"), str) and bool(payload["id"].strip()),
            f"id={payload.get('id') if isinstance(payload, dict) else None}",
        ),
        (
            "choices_list",
            isinstance(choices, list) and bool(choices),
            f"choices_type={type(choices).__name__}",
        ),
        (
            "message_present",
            isinstance(message, dict) and "content" in message,
            f"message_keys={sorted(message.keys()) if isinstance(message, dict) else []}",
        ),
        (
            "finish_reason_present",
            isinstance(first_choice, dict) and "finish_reason" in first_choice,
            f"finish_reason={first_choice.get('finish_reason') if isinstance(first_choice, dict) else None}",
        ),
        (
            "has_usage",
            isinstance(usage, dict) and "total_tokens" in usage,
            f"usage_keys={sorted(usage.keys()) if isinstance(usage, dict) else []}",
        ),
        (
            "model_present",
            isinstance(payload, dict) and isinstance(payload.get("model"), str) and bool(payload["model"]),
            f"model={payload.get('model') if isinstance(payload, dict) else None}",
        ),
    ]


def inspect_responses_success_payload(status_code: int, payload: Any) -> list[Check]:
    output = payload.get("output") if isinstance(payload, dict) else None
    usage = payload.get("usage") if isinstance(payload, dict) else None
    return [
        ("status_200", status_code == 200, f"HTTP {status_code}"),
        (
            "object_response",
            isinstance(payload, dict) and payload.get("object") == "response",
            f"object={payload.get('object') if isinstance(payload, dict) else type(payload).__name__}",
        ),
        (
            "id_present",
            isinstance(payload, dict) and isinstance(payload.get("id"), str) and bool(payload["id"].strip()),
            f"id={payload.get('id') if isinstance(payload, dict) else None}",
        ),
        (
            "has_output",
            isinstance(output, list) and bool(output),
            f"output_type={type(output).__name__}",
        ),
        (
            "status_present",
            isinstance(payload, dict) and isinstance(payload.get("status"), str) and bool(payload["status"]),
            f"status={payload.get('status') if isinstance(payload, dict) else None}",
        ),
        (
            "has_usage",
            isinstance(usage, dict) and (
                "total_tokens" in usage or ("input_tokens" in usage and "output_tokens" in usage)
            ),
            f"usage_keys={sorted(usage.keys()) if isinstance(usage, dict) else []}",
        ),
    ]


def inspect_error_payload(status_code: int, payload: Any) -> list[Check]:
    error = payload.get("error") if isinstance(payload, dict) else None
    return [
        ("non_200_status", status_code >= 400, f"HTTP {status_code}"),
        (
            "has_error_object",
            isinstance(error, dict),
            f"error_type={type(error).__name__}",
        ),
        (
            "has_error_message",
            isinstance(error, dict) and isinstance(error.get("message"), str) and bool(error["message"].strip()),
            f"message={error.get('message') if isinstance(error, dict) else None}",
        ),
        (
            "has_error_type",
            isinstance(error, dict) and isinstance(error.get("type"), str) and bool(error["type"].strip()),
            f"type={error.get('type') if isinstance(error, dict) else None}",
        ),
        (
            "param_field_plausible",
            isinstance(error, dict) and ("param" not in error or error.get("param") is None or isinstance(error.get("param"), str)),
            f"param={error.get('param') if isinstance(error, dict) else None}",
        ),
        (
            "code_field_plausible",
            isinstance(error, dict) and ("code" not in error or error.get("code") is None or isinstance(error.get("code"), str)),
            f"code={error.get('code') if isinstance(error, dict) else None}",
        ),
    ]


def inspect_stream_lines(status_code: int, content_type: str, lines: list[str]) -> list[Check]:
    stripped_lines = [line.strip() for line in lines if line.strip()]
    data_lines = [line for line in stripped_lines if line.startswith("data:")]
    done_present = any(line == "data: [DONE]" for line in data_lines)
    json_like_events = 0
    for line in data_lines:
        if line == "data: [DONE]":
            continue
        payload = line.removeprefix("data:").strip()
        if payload.startswith("{") and payload.endswith("}"):
            json_like_events += 1
    return [
        ("status_200", status_code == 200, f"HTTP {status_code}"),
        (
            "content_type_event_stream",
            "text/event-stream" in (content_type or "").lower(),
            f"content_type={content_type}",
        ),
        (
            "has_data_lines",
            len(data_lines) >= 2,
            f"data_lines={len(data_lines)}",
        ),
        (
            "json_like_events",
            json_like_events >= 1,
            f"json_events={json_like_events}",
        ),
        (
            "has_done_marker",
            done_present,
            f"done_present={done_present}",
        ),
    ]


def render_summary(
    base_url: str,
    model: str,
    stream_enabled: bool,
    total_score: int,
    max_score: int,
    results: list[ProbeResult],
) -> str:
    percent = 0 if max_score == 0 else round(total_score * 100 / max_score)
    verdict = classify_score(percent)
    lines = [
        "OpenAI relay pureblood check",
        f"Target: {base_url}",
        f"Model: {model}",
        f"Streaming tested: {'yes' if stream_enabled else 'no'}",
        f"Score: {total_score}/{max_score} ({percent}%)",
        f"Verdict: {verdict}",
        "",
    ]
    for result in results:
        earned_score = result.get("earned_score")
        max_probe_score = result.get("max_score")
        if earned_score is not None and max_probe_score is not None:
            score_suffix = f", {earned_score}/{max_probe_score} points"
        else:
            score_suffix = ""
        lines.append(
            f"{result['endpoint']} {result['probe']}: "
            f"{result['passed']}/{result['total']} checks"
            f"{score_suffix}"
        )
        for name, ok, detail in result["checks"]:
            prefix = "PASS" if ok else "FAIL"
            lines.append(f"{prefix} {name}: {detail}")
        lines.append("")
    lines.append("Note: protocol similarity is heuristic and does not prove the actual commercial upstream.")
    return "\n".join(lines).rstrip()


def make_check_payload(check: Check) -> dict[str, Any]:
    name, ok, detail = check
    return {"name": name, "ok": ok, "detail": detail}


def make_report_payload(
    base_url: str,
    model: str,
    stream_enabled: bool,
    results: list[ProbeResult],
    checked_at: str,
) -> dict[str, Any]:
    total_score, max_score = compute_totals(results)
    percent = 0 if max_score == 0 else round(total_score * 100 / max_score)
    return {
        "target": base_url,
        "model": model,
        "stream_enabled": stream_enabled,
        "checked_at": checked_at,
        "total_score": total_score,
        "max_score": max_score,
        "percent": percent,
        "verdict": classify_score(percent),
        "results": [
            {
                "endpoint": result["endpoint"],
                "probe": result["probe"],
                "passed": result["passed"],
                "total": result["total"],
                "earned_score": result["earned_score"],
                "max_score": result["max_score"],
                "checks": [make_check_payload(check) for check in result["checks"]],
            }
            for result in results
        ],
    }


def run_report(
    base_url: str,
    api_key: str,
    model: str,
    stream_enabled: bool,
    timeout: int,
    checked_at: str | None = None,
    probe_runner: Any = None,
) -> dict[str, Any]:
    checked_at = checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    probe_runner = probe_runner or run_probes
    results = probe_runner(base_url, api_key, model, stream_enabled, timeout)
    return make_report_payload(
        base_url=base_url,
        model=model,
        stream_enabled=stream_enabled,
        results=results,
        checked_at=checked_at,
    )


def extract_models_payload(base_url: str, payload: Any) -> dict[str, Any]:
    items = payload.get("data") if isinstance(payload, dict) else []
    return {
        "ok": True,
        "target": base_url,
        "models": [
            {"id": item.get("id", ""), "raw": item}
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
        ],
    }


def fetch_models(base_url: str, api_key: str, timeout: int = 30) -> dict[str, Any]:
    status, body, error = get_json(
        endpoint_url(base_url, "/models"),
        {"Authorization": f"Bearer {api_key}"},
        timeout,
    )
    if error:
        raise RuntimeError(error)
    if status != 200:
        detail = body if isinstance(body, dict) else {"message": "model listing failed"}
        raise RuntimeError(json.dumps(detail, ensure_ascii=False))
    return extract_models_payload(base_url, body)


def _require_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The requests package is required to send API probes. Install it with: python -m pip install requests"
        ) from exc
    return requests


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> tuple[int, Any, str]:
    requests = _require_requests()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        return response.status_code, _safe_json(response), ""
    except Exception as exc:
        return 0, None, str(exc)


def get_json(url: str, headers: dict[str, str], timeout: int) -> tuple[int, Any, str]:
    requests = _require_requests()
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        return response.status_code, _safe_json(response), ""
    except Exception as exc:
        return 0, None, str(exc)


def post_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
    max_lines: int = 12,
) -> tuple[int, str, list[str], str]:
    requests = _require_requests()
    try:
        with requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True) as response:
            lines: list[str] = []
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if not line:
                    continue
                lines.append(line)
                if len(lines) >= max_lines:
                    break
                if line == "data: [DONE]":
                    break
            return response.status_code, response.headers.get("Content-Type", ""), lines, ""
    except Exception as exc:
        return 0, "", [], str(exc)


def _network_failure_checks(error_message: str) -> list[Check]:
    return [("request_completed", False, error_message or "request failed before receiving a response")]


def probe_chat_success(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": SUCCESS_PROMPT}],
        "max_tokens": 8,
        "temperature": 0,
    }
    status, body, error = post_json(
        endpoint_url(base_url, "/chat/completions"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_chat_success_payload(status, body)
    return build_probe_result("chat/completions", "success", checks, PROBE_WEIGHTS["chat_success"])


def probe_chat_error(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "messages": "invalid-type",
    }
    status, body, error = post_json(
        endpoint_url(base_url, "/chat/completions"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_error_payload(status, body)
    return build_probe_result("chat/completions", "error", checks, PROBE_WEIGHTS["chat_error"])


def probe_responses_success(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "input": SUCCESS_PROMPT,
        "max_output_tokens": 16,
    }
    status, body, error = post_json(
        endpoint_url(base_url, "/responses"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_responses_success_payload(status, body)
    return build_probe_result("responses", "success", checks, PROBE_WEIGHTS["responses_success"])


def probe_responses_error(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "input": {"bad": "type"},
    }
    status, body, error = post_json(
        endpoint_url(base_url, "/responses"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_error_payload(status, body)
    return build_probe_result("responses", "error", checks, PROBE_WEIGHTS["responses_error"])


def probe_chat_stream(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": STREAM_PROMPT}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": True,
    }
    status, content_type, lines, error = post_stream(
        endpoint_url(base_url, "/chat/completions"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_stream_lines(status, content_type, lines)
    return build_probe_result("chat/completions", "stream", checks, PROBE_WEIGHTS["chat_stream"])


def probe_responses_stream(base_url: str, api_key: str, model: str, timeout: int) -> ProbeResult:
    payload = {
        "model": model,
        "input": STREAM_PROMPT,
        "max_output_tokens": 16,
        "stream": True,
    }
    status, content_type, lines, error = post_stream(
        endpoint_url(base_url, "/responses"),
        build_headers(api_key),
        payload,
        timeout,
    )
    checks = _network_failure_checks(error) if error else inspect_stream_lines(status, content_type, lines)
    return build_probe_result("responses", "stream", checks, PROBE_WEIGHTS["responses_stream"])


def run_probes(base_url: str, api_key: str, model: str, stream_enabled: bool, timeout: int) -> list[ProbeResult]:
    results = [
        probe_chat_success(base_url, api_key, model, timeout),
        probe_chat_error(base_url, api_key, model, timeout),
        probe_responses_success(base_url, api_key, model, timeout),
        probe_responses_error(base_url, api_key, model, timeout),
    ]
    if stream_enabled:
        results.extend(
            [
                probe_chat_stream(base_url, api_key, model, timeout),
                probe_responses_stream(base_url, api_key, model, timeout),
            ]
        )
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a relay API and estimate how closely it behaves like a native OpenAI endpoint."
    )
    parser.add_argument("--base-url", required=True, help="Relay base URL, with or without /v1")
    parser.add_argument("--api-key", required=True, help="Bearer token for the relay")
    parser.add_argument("--model", required=True, help="Model name to probe")
    parser.add_argument("--stream", action="store_true", help="Enable streaming probes")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as exc:
        print(f"Argument error: {exc}")
        return 2

    try:
        results = run_probes(base_url, args.api_key, args.model, args.stream, args.timeout)
    except RuntimeError as exc:
        print(str(exc))
        return 2

    total_score, max_score = compute_totals(results)
    print(
        render_summary(
            base_url=base_url,
            model=args.model,
            stream_enabled=args.stream,
            total_score=total_score,
            max_score=max_score,
            results=results,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
