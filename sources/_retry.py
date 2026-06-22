"""Shared HTTP retry helper used by all source modules.

Every requests.get() in this project should go through get_with_retry()
so that 429 (rate limit) and transient 5xx errors are handled uniformly.

Default backoff sequence (base_delay=15): 15s → 30s → 60s → 120s.
"""
import time
import requests

_RETRY_ON = {429, 500, 502, 503, 504}


def get_with_retry(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 60,
    max_retries: int = 4,
    base_delay: int = 15,
    label: str = "",
) -> requests.Response:
    tag = f"[{label}] " if label else ""
    last_response = None

    for attempt in range(max_retries):
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        last_response = r

        if r.status_code in _RETRY_ON and attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            print(
                f"{tag}HTTP {r.status_code} — retrying in {delay}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(delay)
            continue

        r.raise_for_status()
        return r

    # All retries exhausted — raise on the last response
    last_response.raise_for_status()
    return last_response  # unreachable; satisfies type checker
