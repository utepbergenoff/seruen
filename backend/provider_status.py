"""Bounded provider diagnostics. Never expose response text, keys, URLs or prompts."""

import json
import logging

SAFE_REASONS = {
    "API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_SERVICE_BLOCKED",
    "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED",
    "SERVICE_DISABLED", "BILLING_DISABLED", "CONSUMER_INVALID",
}


def http_error_code(response):
    code = f"http_{int(response.status_code)}"
    try:
        if len(response.content) <= 100_000:
            for detail in response.json().get("error", {}).get("details", []):
                reason = detail.get("reason")
                if reason in SAFE_REASONS:
                    return f"{code}_{reason.lower()}"
    except (ValueError, TypeError, AttributeError):
        pass
    return code


def log_provider(provider, code):
    # Callers pass only local constants or http_error_code, never exception text.
    logging.getLogger("seruen").info(json.dumps({
        "mode": provider, "duration_ms": 0, "candidates": 0, "error_code": code,
    }))
