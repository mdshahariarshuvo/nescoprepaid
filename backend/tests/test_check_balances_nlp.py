import os
import json

import pytest

try:
    import requests
except Exception:  # pragma: no cover - helpful error when running tests without deps
    requests = None


@pytest.mark.skipif(requests is None, reason="requests not installed")
def test_check_balances_nlp_endpoint():
    """Assert the /api/check-balances-nlp endpoint returns success and structured results.

    This test expects a running backend (default http://127.0.0.1:5000) and a test user id
    present in the database (default TELEGRAM_TEST_USER env var: 6895627984).
    """
    backend = os.getenv('BACKEND_URL', 'http://127.0.0.1:5000').rstrip('/')
    user = int(os.getenv('TELEGRAM_TEST_USER', '6895627984'))
    url = f"{backend}/api/check-balances-nlp"
    payload = {'telegram_user_id': user, 'language': os.getenv('TEST_LANG', 'bn')}

    resp = requests.post(url, json=payload, timeout=30)
    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} - {resp.text[:200]}"

    body = resp.json()
    assert body.get('success') is True
    assert 'results' in body and isinstance(body['results'], list)
    # nlp_reply may be None (if AI disabled/fallback), but key should exist
    assert 'nlp_reply' in body
