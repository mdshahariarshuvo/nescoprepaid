#!/usr/bin/env python3
"""
Manual test script for the backend endpoint `/api/check-balances-nlp`.

This script contains a small suite of manual tests you can run against a
locally-running backend to exercise these behaviours:

- Normal NLP call for an existing user
- Caching behaviour: make two calls in quick succession and compare `nlp_reply`
- Missing-field/error case: call without `telegram_user_id` (expect 400)
- Non-existent user: call with an unknown id (expect 404)
- User without meters: create a user but do not add meters, expect an error

How to run:
    # from the project root
    cd backend
    source .env            # or set env vars appropriately
    python3 tests/manual_test_check_balances_nlp.py

Environment variables:
    BACKEND_URL (default http://127.0.0.1:5000)
    TELEGRAM_TEST_USER (default 6895627984)
    TEST_LANG (default 'bn')

Notes on simulating LLM fallback:
    - The backend uses `AI_AGENT_ENABLED` and `AI_AGENT_KEY` from the environment.
    - To force the deterministic fallback (instead of a live LLM reply), start the
        backend with `AI_AGENT_ENABLED=true` and an invalid `AI_AGENT_KEY` (or
        point OPENROUTER_URL to a non-routable address). The agent will attempt the
        call, fail, and return the deterministic fallback reply. Watch backend logs
        for messages like "LLM produced reply (truncated)" or "LLM returned empty
        response; using deterministic fallback".

This script will attempt to create a user (via /webhook/telegram start) if the
user does not exist, then run the tests. It prints human-friendly results and
exits with code 0 if all core tests pass, otherwise non-zero.
"""
import os
import sys
import json

try:
    import requests
except Exception as exc:
    print("The 'requests' package is required to run this test. Install with: pip install requests")
    raise


def main():
    backend = os.getenv('BACKEND_URL', 'http://127.0.0.1:5000').rstrip('/')
    user = int(os.getenv('TELEGRAM_TEST_USER', '6895627984'))
    url = f"{backend}/api/check-balances-nlp"
    payload = {
        'telegram_user_id': user,
        'language': os.getenv('TEST_LANG', 'bn')
    }

    # helper functions -------------------------------------------------
    def call(payload, timeout=30):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            return r
        except requests.RequestException as exc:
            print('Request failed:', exc)
            return None

    def ensure_user_exists(tel_id: int):
        start_url = f"{backend}/webhook/telegram"
        print(f"Ensuring user {tel_id} exists via {start_url}")
        try:
            resp = requests.post(start_url, json={'command': 'start', 'telegram_user_id': tel_id}, timeout=10)
            print('start HTTP', resp.status_code)
        except Exception as exc:
            print('Failed to create/verify user:', exc)

    # run tests ---------------------------------------------------------
    ensure_user_exists(user)

    print('\n1) Normal NLP call')
    print(f"Calling {url} for user {user} (language={payload['language']})")
    r1 = call(payload)
    if r1 is None:
        print('Test 1: request failed')
        sys.exit(2)
    print('HTTP', r1.status_code)
    try:
        body1 = r1.json()
    except Exception as exc:
        print('Failed to parse JSON response:', exc)
        print('Raw body:', r1.text[:1000])
        sys.exit(3)

    print(json.dumps(body1, ensure_ascii=False, indent=2))
    ok = body1.get('success') is True
    print('Result:', 'PASS' if ok else 'FAIL')
    results = []
    results.append(('normal_call', ok, body1))

    # caching test: call twice and compare nlp_reply
    print('\n2) Caching behaviour: calling twice to observe cache/store')
    r2 = call(payload)
    if r2 is None:
        print('Test 2: second request failed')
        sys.exit(4)
    try:
        body2 = r2.json()
    except Exception as exc:
        print('Failed to parse JSON on second call:', exc)
        print('Raw body:', r2.text[:1000])
        sys.exit(5)

    reply1 = (body1.get('nlp_reply') or '')
    reply2 = (body2.get('nlp_reply') or '')
    same = reply1 == reply2 and reply1 != ''
    print('nlp_reply equal between calls?', same)
    if same:
        print('Likely cached (or deterministic replies). Check backend logs for "NLP cache" messages to confirm.')
    else:
        print('Replies differ; cache may not be enabled or TTL expired.')
    results.append(('caching', same, {'first': reply1, 'second': reply2}))

    # missing-field error case
    print('\n3) Missing-field error (no telegram_user_id)')
    r3 = call({'language': payload['language']})
    if r3 is None:
        print('Test 3: request failed')
        sys.exit(6)
    print('HTTP', r3.status_code)
    try:
        b3 = r3.json()
    except Exception:
        b3 = {'raw': r3.text[:500]}
    print(json.dumps(b3, ensure_ascii=False, indent=2))
    missing_ok = r3.status_code == 400
    print('Result:', 'PASS' if missing_ok else 'FAIL')
    results.append(('missing_field', missing_ok, b3))

    # non-existent user
    print('\n4) Non-existent user (expect 404)')
    unknown_id = 999999999999
    r4 = call({'telegram_user_id': unknown_id, 'language': payload['language']})
    if r4 is None:
        print('Test 4: request failed')
        sys.exit(7)
    print('HTTP', r4.status_code)
    try:
        b4 = r4.json()
    except Exception:
        b4 = {'raw': r4.text[:500]}
    print(json.dumps(b4, ensure_ascii=False, indent=2))
    notfound_ok = r4.status_code == 404
    print('Result:', 'PASS' if notfound_ok else 'FAIL')
    results.append(('nonexistent_user', notfound_ok, b4))

    # user without meters: create a new user id and don't add meters
    print('\n5) User without meters (expect service error / no meters)')
    bare_user = int(os.getenv('TEST_BARE_USER', '6890000000'))
    ensure_user_exists(bare_user)
    r5 = call({'telegram_user_id': bare_user, 'language': payload['language']})
    if r5 is None:
        print('Test 5: request failed')
        sys.exit(8)
    print('HTTP', r5.status_code)
    try:
        b5 = r5.json()
    except Exception:
        b5 = {'raw': r5.text[:500]}
    print(json.dumps(b5, ensure_ascii=False, indent=2))
    # backend returns structured failure when no meters; this endpoint converts that into a 500
    bare_ok = (not b5.get('success')) or (r5.status_code in (400, 500))
    print('Result:', 'PASS' if bare_ok else 'FAIL')
    results.append(('no_meters', bare_ok, b5))

    # summary
    print('\nSummary:')
    failed = [r for r in results if not r[1]]
    for name, ok, info in results:
        print(f" - {name}: {'PASS' if ok else 'FAIL'}")

    if failed:
        print('\nSome manual tests failed. See above output and check backend logs for details.')
        sys.exit(10)
    else:
        print('\nAll manual tests passed (subject to the backend configuration).')
        print('If you want to test LLM fallback, restart the backend with AI_AGENT_ENABLED=true and an invalid AI_AGENT_KEY; then run the normal NLP call and watch logs for fallback messages.')
        sys.exit(0)


if __name__ == '__main__':
    main()
