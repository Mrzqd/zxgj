from __future__ import annotations

from collections.abc import Callable
import time
from typing import TypeVar

import httpx


RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_ERROR_BODY_CHARS = 500
MAX_BACKOFF_SECONDS = 30.0

T = TypeVar("T")


def describe_http_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = response.text.strip().replace("\n", " ")[:MAX_ERROR_BODY_CHARS]
        message = f"HTTP {response.status_code}"
        if response.reason_phrase:
            message += f" {response.reason_phrase}"
        return f"{message}，响应：{detail}" if detail else message
    if isinstance(exc, httpx.TimeoutException):
        return f"请求超时：{exc}"
    if isinstance(exc, httpx.TransportError):
        return f"网络连接异常：{exc}"
    return str(exc)


def run_with_http_retry(
    operation: str,
    request: Callable[[], T],
    *,
    attempts: int,
    backoff_seconds: float,
) -> T:
    max_attempts = max(1, attempts)
    delay = max(0.0, backoff_seconds)
    last_error: Exception | None = None
    used_attempts = 0

    for attempt_index in range(max_attempts):
        used_attempts = attempt_index + 1
        try:
            return request()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if not _is_retryable(exc) or attempt_index >= max_attempts - 1:
                break
            time.sleep(min(delay * (2**attempt_index), MAX_BACKOFF_SECONDS))

    if last_error is None:
        raise RuntimeError(f"{operation}失败")
    raise RuntimeError(
        f"{operation}失败（已尝试 {used_attempts} 次）：{describe_http_exception(last_error)}"
    ) from last_error


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    operation: str,
    attempts: int,
    backoff_seconds: float,
    accepted_status_codes: set[int] | None = None,
    **kwargs,
) -> httpx.Response:
    def request() -> httpx.Response:
        response = client.request(method, url, **kwargs)
        if accepted_status_codes is not None:
            if response.status_code not in accepted_status_codes:
                raise httpx.HTTPStatusError(
                    f"Unexpected status code {response.status_code}",
                    request=response.request,
                    response=response,
                )
        else:
            response.raise_for_status()
        return response

    return run_with_http_retry(
        operation,
        request,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
    )


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)
