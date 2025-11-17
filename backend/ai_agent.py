import json
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
import re

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

logger = logging.getLogger(__name__)

AI_AGENT_ENABLED = os.getenv("AI_AGENT_ENABLED", "false").lower() == "true"
AI_AGENT_KEY = os.getenv("AI_AGENT_KEY")
AI_AGENT_MODEL = os.getenv("AI_AGENT_MODEL", "tngtech/deepseek-r1t2-chimera:free")
AI_AGENT_FREE_MODEL = os.getenv("AI_AGENT_FREE_MODEL", "tngtech/deepseek-r1t2-chimera:free")
OPENROUTER_URL = os.getenv("AI_AGENT_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_REFERER = os.getenv("AI_AGENT_OPENROUTER_REFERER", "http://localhost")
OPENROUTER_TITLE = os.getenv("AI_AGENT_OPENROUTER_TITLE", "NESCO Helper Bot")
AI_AGENT_TIMEOUT = int(os.getenv("AI_AGENT_TIMEOUT", "40"))

SYSTEM_INSTRUCTIONS = (
    "You help the NESCO Meter Helper Telegram bot understand user intent. "
    "Always respond with **ONLY** a compact JSON object containing: intent, meter_name, meter_number, response. "
    "Valid intents: START, HELP, LIST_METERS, ADD_METER, CHECK_BALANCES, REMOVE_METER, TOGGLE_REMINDER, USAGE_REPORT, SMALL_TALK, UNKNOWN. "
    "If the user wants to add a meter but did not share the number, set intent=ADD_METER and response='Please enter the meter number.' "
    "If they provide a number, echo it in meter_number and tell them next step (ask for name if missing). "
    "If the user gives both number and name, confirm addition and say you will check balance next. "
    "If they ask for balance, use intent=CHECK_BALANCES and response like 'Checking your balances now.' "
    "If they ask for a usage report, month summary, or electricity consumption history, set intent=USAGE_REPORT and respond with a short confirmation that you are generating the report. "
    "If the user asks about the owner/creator/developer of the bot, set intent=SMALL_TALK and respond exactly: 'This project is developed by Shahariar Shuvo. To learn more, visit https://shahariarshuvo.me'. "
    "If they just chat, use intent=SMALL_TALK with a short friendly response under two sentences. "
    "Never include explanations outside JSON."
)

# Few-shot examples and stronger formatting guidance to improve reliability when generating
# short personalized replies. These examples are used by generate_nlp_reply to help the model
# produce concise, factual, and polite messages in the requested language.
FEW_SHOT_EXAMPLES = (
    "Example 1 (Bangla):\nContext: User: Rahim. Date: 2025-11-18. Balances:\n- Home (3101): 120.00 BDT; min=100.00 BDT\n- Shop (3102): 45.50 BDT; min=120.00 BDT\nTotal used since yesterday: 10.00 BDT\n\nDesired reply (Bangla):\nআপনার ব্যালেন্স: Home: 120.00 BDT। Shop: 45.50 BDT — এটি ন্যূনতম সীমার নিচে আছে; অনুগ্রহ করে Shop মিটারে রিচার্জ করুন।\n\nExample 2 (English):\nContext: User: Shuvo. Date: 2025-11-18. Balances:\n- Office (1234): 300.00 BDT; min=100.00 BDT\nTotal used since yesterday: 0.00 BDT\n\nDesired reply (English):\nYour balance: Office: 300.00 BDT. All meters are above the minimum."
)


def _format_meter_context(meter_context: Optional[List[Dict[str, Any]]]) -> str:
    if not meter_context:
        return ""
    summary = ", ".join(
        f"{m.get('name')} ({m.get('number')})" for m in meter_context[:5]
    )
    return f"Known meters: {summary}. "


def _parse_json_block(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    try:
        if text.startswith("{") and text.endswith("}"):
            return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from AI payload: %s", text)
    return None


def _extract_message_content(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return data.get("text", "")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(part["text"])
        return "\n".join(parts)
    return ""


def ai_enabled() -> bool:
    return AI_AGENT_ENABLED and bool(AI_AGENT_KEY)


def _build_messages(system_content: str, user_text: str):
    return [
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": user_text,
        },
    ]


def _call_openrouter(model: str, headers: Dict[str, str], messages: List[Dict[str, str]]):
    payload = {
        "model": model,
        "messages": messages,
    }
    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=AI_AGENT_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def interpret_message(
    user_text: str,
    meter_context: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    if not ai_enabled():
        return None

    headers = {
        "Authorization": f"Bearer {AI_AGENT_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }
    context_line = _format_meter_context(meter_context)
    system_content = SYSTEM_INSTRUCTIONS
    if context_line:
        system_content = f"{SYSTEM_INSTRUCTIONS} {context_line}"

    messages = _build_messages(system_content, user_text)

    def _request_with_model(model_name: str):
        data = _call_openrouter(model_name, headers, messages)
        content = _extract_message_content(data)
        return _parse_json_block(content)

    try:
        return _request_with_model(AI_AGENT_MODEL)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response else None
        if status_code == 402 and AI_AGENT_FREE_MODEL and AI_AGENT_MODEL != AI_AGENT_FREE_MODEL:
            logger.warning(
                "Primary model '%s' requires payment. Falling back to free model '%s'.",
                AI_AGENT_MODEL,
                AI_AGENT_FREE_MODEL,
            )
            try:
                return _request_with_model(AI_AGENT_FREE_MODEL)
            except Exception as fallback_exc:  # noqa: BLE001
                logger.error("Fallback OpenRouter request failed: %s", fallback_exc)
                return None
        logger.error("OpenRouter request failed: %s", exc)
    except requests.RequestException as exc:
        logger.error("OpenRouter request failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error calling OpenRouter: %s", exc)
    return None


def generate_nlp_reply(
    user_display: str,
    results: List[Dict[str, Any]],
    language: str = 'bn',
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Given a user display name and structured balance results, ask the model to generate
    a short personalized reply (in Bangla if language=='bn'). Returns the reply text or None.
    """
    if not ai_enabled():
        logger.info('AI agent disabled; skipping generate_nlp_reply')
        return None

    model_name = model or AI_AGENT_MODEL

    # build a concise human-readable context for the model
    date_line = datetime.utcnow().strftime('%Y-%m-%d')
    lines = [f"User: {user_display}", f"Date: {date_line}", "Balances:"]
    total_used = 0.0
    for r in results:
        if r.get('error'):
            lines.append(f"- {r.get('name')} ({r.get('number')}): ERROR: {r.get('error')}")
            continue
        bal = float(r.get('balance') or 0.0)
        minb = float(r.get('min_balance') or 0.0)
        delta = r.get('delta')
        lines.append(f"- {r.get('name')} ({r.get('number')}): {bal:.2f} BDT; min={minb:.2f} BDT")
        if delta is not None and float(delta) < 0:
            total_used += -float(delta)

    lines.append(f"Total used since yesterday: {total_used:.2f} BDT")

    # language choice
    lang_sentence = 'Please reply in Bangla.' if language and language.lower().startswith('b') else 'Please reply in English.'

    system_prompt = (
        "You are a concise assistant that formats a short user-friendly reply. "
        "I will provide a user's prepaid meter balances. Use only this factual data to compose the reply. "
        "Do NOT invent numbers or other facts. Output only the final reply text (one or two short sentences)."
    )

    user_prompt = "\n".join(lines) + f"\nLanguage: {language}\n{lang_sentence}\nProduce a single short reply text suitable for a Telegram message."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    headers = {
        "Authorization": f"Bearer {AI_AGENT_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }

    try:
        data = _call_openrouter(model_name, headers, messages)
        text = _extract_message_content(data)
        # sanitize and log a truncated copy of the model output for debugging (no raw data persistence)
        if isinstance(text, str) and text.strip():
            safe = re.sub(r"\s+", " ", text).strip()
            safe_trunc = safe[:1000]
            logger.info('LLM produced reply (truncated): %s', safe_trunc)
            text = safe
        else:
            text = ''

        if not text:
            # empty model response -> fall back
            logger.warning('LLM returned empty response; using deterministic fallback')
            return _deterministic_fallback(user_display, results, language)

        # trim whitespace and return only the first paragraph
        text = text.strip()
        paragraphs = [p for p in text.split('\n') if p.strip()]
        return paragraphs[0] if paragraphs else text
    except Exception as exc:  # noqa: BLE001
        logger.exception('generate_nlp_reply failed: %s', exc)
        # fallback to deterministic reply so user always gets something
        return _deterministic_fallback(user_display, results, language)


def _deterministic_fallback(user_display: str, results: List[Dict[str, Any]], language: str = 'bn') -> str:
    """Produce a short deterministic reply from structured results when the LLM is unavailable.
    This avoids leaving the user without a response.
    """
    parts: List[str] = []
    # brief header
    if language and language.lower().startswith('b'):
        parts.append(f"{user_display}님의 ব্যালেন্স আপডেট:" if False else "আপনার ব্যালেন্স আপডেট:")
    else:
        parts.append(f"{user_display} balance update:")

    low_warnings: List[str] = []
    for r in results[:5]:
        if r.get('error'):
            # include error note
            if language and language.lower().startswith('b'):
                parts.append(f"{r.get('name')} ({r.get('number')}): ত্রুটি: {r.get('error')}")
            else:
                parts.append(f"{r.get('name')} ({r.get('number')}): ERROR: {r.get('error')}")
            continue
        try:
            bal = float(r.get('balance') or 0.0)
        except Exception:
            bal = r.get('balance')
        if language and language.lower().startswith('b'):
            parts.append(f"{r.get('name')} ({r.get('number')}): {float(bal):.2f} BDT")
        else:
            parts.append(f"{r.get('name')} ({r.get('number')}): {float(bal):.2f} BDT")
        if r.get('alert'):
            low_warnings.append(r.get('name') or r.get('number'))

    # summary lines
    if low_warnings:
        if language and language.lower().startswith('b'):
            parts.append(f"নিম্ন ব্যালেন্স সতর্কতা: {', '.join(low_warnings)} — অনুগ্রহ করে রিচার্জ করুন।")
        else:
            parts.append(f"Low balance warning: {', '.join(low_warnings)} — please recharge.")

    # join into one short message (limit length)
    message = ' '.join(parts)
    return (message[:900] + '...') if len(message) > 900 else message
