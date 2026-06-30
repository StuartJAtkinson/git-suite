"""github: the 403/429 rate-limit disambiguation (ported from homelab-designer)."""
import time

import httpx

from services.github import _rate_limit_wait, _quota_sleep


def test_429_with_retry_after():
    r = httpx.Response(429, headers={"Retry-After": "30"})
    assert _rate_limit_wait(r) == 31


def test_403_secondary_rate_limit_retry_after():
    r = httpx.Response(403, headers={"Retry-After": "10"})
    assert _rate_limit_wait(r) == 11


def test_403_primary_rate_limit_remaining_zero():
    reset = int(time.time()) + 30
    r = httpx.Response(403, headers={"X-RateLimit-Remaining": "0",
                                     "X-RateLimit-Reset": str(reset)})
    wait = _rate_limit_wait(r)
    assert 25 <= wait <= 35          # ~until reset


def test_403_genuine_auth_failure_returns_none():
    # No Retry-After, remaining > 0, body isn't about rate limits -> not throttling
    r = httpx.Response(403, headers={"X-RateLimit-Remaining": "4999"},
                       json={"message": "Must have admin rights to Repository."})
    assert _rate_limit_wait(r) is None


def test_200_is_not_rate_limited():
    assert _rate_limit_wait(httpx.Response(200)) is None


def test_quota_sleep_only_when_low():
    plenty = httpx.Response(200, headers={"X-RateLimit-Remaining": "500"})
    assert _quota_sleep(plenty) == 0.0
    low = httpx.Response(200, headers={"X-RateLimit-Remaining": "5",
                                       "X-RateLimit-Reset": str(int(time.time()) + 20)})
    assert _quota_sleep(low) > 0
