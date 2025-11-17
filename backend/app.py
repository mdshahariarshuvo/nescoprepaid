from collections import defaultdict
from datetime import datetime, timedelta
import pytz
from functools import wraps
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

# Timezone configuration (defaults to Dhaka)
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Dhaka')
try:
    TZ = pytz.timezone(TIMEZONE)
except Exception:
    TZ = pytz.timezone('Asia/Dhaka')

def now():
    """Return current time as timezone-aware datetime in configured TZ."""
    return datetime.now(tz=TZ)

# Scheduler configuration: enable internal scheduler and set daily reminder time (HH:MM)
ENABLE_INTERNAL_SCHEDULER = os.getenv('ENABLE_INTERNAL_SCHEDULER', 'true').lower() == 'true'
DAILY_REMINDER_TIME = os.getenv('DAILY_REMINDER_TIME', '20:00')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/nesco_bot')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# In-memory cache for NLP replies: { key: (reply_text, expires_at) }
NLP_CACHE: Dict[str, Any] = {}
NLP_CACHE_LOCK = threading.Lock()
NLP_CACHE_TTL = int(os.getenv('NLP_CACHE_TTL', '60'))  # seconds


# Development helper: allow simple CORS so the frontend (localhost:8081) can reach the API
# This is intentionally permissive for local development. For production, restrict origins.
@app.after_request
def _allow_cors(response):
    response.headers.setdefault('Access-Control-Allow-Origin', '*')
    response.headers.setdefault('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    response.headers.setdefault('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    return response

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'shuvo')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'shuvo')
ADMIN_AUTH_ENABLED = os.getenv('ADMIN_AUTH_ENABLED', 'true').lower() == 'true'

# Messenger integration removed per project configuration. If you later want to
# re-enable Messenger support, re-add the tokens and logic guarded by
# MESSENGER_PAGE_ACCESS_TOKEN and MESSENGER_VERIFY_TOKEN.


# Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(100))
    daily_reminder_enabled = db.Column(db.Boolean, default=True)
    reminder_time = db.Column(db.String(5), default='19:17')
    created_at = db.Column(db.DateTime, default=now)
    meters = db.relationship('Meter', backref='user', lazy=True, cascade='all, delete-orphan')


class Meter(db.Model):
    __tablename__ = 'meters'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    meter_number = db.Column(db.String(20), nullable=False)
    meter_name = db.Column(db.String(100), nullable=False)
    min_balance = db.Column(db.Float, default=50.0)
    last_balance = db.Column(db.Float)
    last_checked = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)
    history = db.relationship('BalanceHistory', backref='meter', lazy=True, cascade='all, delete-orphan')


class BalanceHistory(db.Model):
    __tablename__ = 'balance_history'
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    balance = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=now)


# MessengerProfile model removed (Messenger integration disabled)


def get_or_create_user(telegram_user_id: int) -> User:
    if telegram_user_id is None:
        raise ValueError('telegram_user_id is required')
    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if not user:
        user = User(telegram_user_id=telegram_user_id)
        db.session.add(user)
        db.session.commit()
    return user


def _serialize_meter(meter: Meter) -> Dict[str, Any]:
    return {
        'id': meter.id,
        'name': meter.meter_name,
        'number': meter.meter_number,
        'min_balance': meter.min_balance,
        'last_balance': meter.last_balance,
        'last_checked': meter.last_checked.isoformat() if meter.last_checked else None,
    }


def add_meter_for_user(user: User, meter_number: str, meter_name: str) -> Dict[str, Any]:
    if not meter_number or not meter_name:
        return {'success': False, 'error': 'Missing required fields'}

    existing = Meter.query.filter_by(user_id=user.id, meter_number=meter_number).first()
    if existing:
        return {'success': False, 'error': 'Meter already exists'}

    result = scrape_nesco_balance(meter_number)
    if not result['success']:
        return {'success': False, 'error': f"Cannot verify meter: {result['error']}"}

    meter = Meter(
        user_id=user.id,
        meter_number=meter_number,
        meter_name=meter_name,
        last_balance=result['balance'],
    last_checked=now(),
    )
    db.session.add(meter)

    history = BalanceHistory(meter=meter, balance=result['balance'])
    db.session.add(history)
    db.session.commit()

    return {
        'success': True,
        'message': f"✅ Added meter: {meter_name} ({meter_number})\nCurrent balance: {result['balance']} BDT",
    }


def list_meters_for_user(user: User) -> Dict[str, Any]:
    if not user or not user.meters:
        return {
            'success': True,
            'meters': [],
            'message': 'No meters added yet. Use /add to add one.',
        }

    meters_list = [_serialize_meter(meter) for meter in user.meters]
    return {'success': True, 'meters': meters_list}


def check_balances_for_user(user: User) -> Dict[str, Any]:
    if not user or not user.meters:
        return {'success': False, 'error': 'No meters found'}

    results: List[Dict[str, Any]] = []
    yesterday = now() - timedelta(days=1)

    for meter in user.meters:
        scrape_result = scrape_nesco_balance(meter.meter_number)

        if scrape_result['success']:
            current_balance = scrape_result['balance']

            # Find the most recent record since yesterday (if any)
            yesterday_record = (
                BalanceHistory.query
                .filter(
                    BalanceHistory.meter_id == meter.id,
                    BalanceHistory.recorded_at >= yesterday,
                )
                .order_by(BalanceHistory.recorded_at.desc())
                .first()
            )

            yesterday_balance = None
            delta = None
            delta_percent = None
            if yesterday_record:
                yesterday_balance = yesterday_record.balance
                # delta = current - yesterday_balance (positive => increase, negative => decrease)
                delta = float(current_balance) - float(yesterday_balance)
                try:
                    if yesterday_balance:
                        delta_percent = (delta / float(yesterday_balance)) * 100.0
                except Exception:
                    delta_percent = None

            meter.last_balance = current_balance
            meter.last_checked = now()

            history = BalanceHistory(meter_id=meter.id, balance=current_balance)
            db.session.add(history)

            alert = current_balance < meter.min_balance

            results.append({
                'name': meter.meter_name,
                'number': meter.meter_number,
                'balance': current_balance,
                'yesterday_balance': yesterday_balance,
                'delta': delta,
                'delta_percent': delta_percent,
                'alert': alert,
                'min_balance': meter.min_balance,
            })
        else:
            results.append({
                'name': meter.meter_name,
                'number': meter.meter_number,
                'error': scrape_result['error'],
            })

    db.session.commit()

    return {
        'success': True,
        'results': results,
    'timestamp': now().isoformat(),
    }


def cached_check_balances_for_user(user: User) -> Dict[str, Any]:
    """Return a fast, DB-only snapshot of the last known balances for a user.
    This does NOT perform live scraping — it's intended for quick replies.
    """
    if not user or not user.meters:
        return {'success': False, 'error': 'No meters found'}

    results: List[Dict[str, Any]] = []
    yesterday = now() - timedelta(days=1)

    for meter in user.meters:
        try:
            current_balance = meter.last_balance
            yesterday_record = (
                BalanceHistory.query
                .filter(
                    BalanceHistory.meter_id == meter.id,
                    BalanceHistory.recorded_at >= yesterday,
                )
                .order_by(BalanceHistory.recorded_at.desc())
                .first()
            )

            yesterday_balance = None
            delta = None
            delta_percent = None
            if yesterday_record:
                yesterday_balance = yesterday_record.balance
                if current_balance is not None:
                    try:
                        delta = float(current_balance) - float(yesterday_balance)
                        if yesterday_balance:
                            delta_percent = (delta / float(yesterday_balance)) * 100.0
                    except Exception:
                        delta = None

            alert = False
            if current_balance is not None:
                alert = float(current_balance) < float(meter.min_balance or 0)

            results.append({
                'name': meter.meter_name,
                'number': meter.meter_number,
                'balance': current_balance,
                'yesterday_balance': yesterday_balance,
                'delta': delta,
                'delta_percent': delta_percent,
                'alert': alert,
                'min_balance': meter.min_balance,
                'last_checked': meter.last_checked.isoformat() if meter.last_checked else None,
            })
        except Exception as exc:  # defensive
            logger.exception('Error reading cached balance for meter %s: %s', getattr(meter, 'id', None), exc)
            results.append({'name': meter.meter_name, 'number': meter.meter_number, 'error': 'Failed to read cached balance'})

    return {'success': True, 'results': results, 'timestamp': now().isoformat()}


def remove_meter_for_user(user: User, meter_id: int) -> Dict[str, Any]:
    if not user:
        return {'success': False, 'error': 'User not found'}

    meter = Meter.query.filter_by(id=meter_id, user_id=user.id).first()
    if not meter:
        return {'success': False, 'error': 'Meter not found'}

    meter_name = meter.meter_name
    db.session.delete(meter)
    db.session.commit()

    return {'success': True, 'message': f'✅ Removed meter: {meter_name}'}


def set_min_balance_for_user(user: User, meter_id: int, min_balance: float) -> Dict[str, Any]:
    if not user:
        return {'success': False, 'error': 'User not found'}

    meter = Meter.query.filter_by(id=meter_id, user_id=user.id).first()
    if not meter:
        return {'success': False, 'error': 'Meter not found'}

    meter.min_balance = float(min_balance)
    db.session.commit()

    return {'success': True, 'message': f'✅ Min balance set to {min_balance} BDT for {meter.meter_name}'}


def toggle_reminder_for_user(user: User) -> Dict[str, Any]:
    if not user:
        return {'success': False, 'error': 'User not found'}

    user.daily_reminder_enabled = not user.daily_reminder_enabled
    db.session.commit()

    status = 'enabled' if user.daily_reminder_enabled else 'disabled'
    return {'success': True, 'message': f'✅ Daily reminder {status}'}


def build_usage_report_for_user(user: User) -> Dict[str, Any]:
    if not user or not user.meters:
        return {'success': False, 'error': 'No meters found for this account.'}

    current_time = now()
    month_start = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    usage_by_date = defaultdict(float)
    total_usage = 0.0

    for meter in user.meters:
        prev_entry = (
            BalanceHistory.query
            .filter(
                BalanceHistory.meter_id == meter.id,
                BalanceHistory.recorded_at < month_start,
            )
            .order_by(BalanceHistory.recorded_at.desc())
            .first()
        )
        prev_balance = prev_entry.balance if prev_entry else None

        daily_records = (
            BalanceHistory.query
            .filter(
                BalanceHistory.meter_id == meter.id,
                BalanceHistory.recorded_at >= month_start,
            )
            .order_by(BalanceHistory.recorded_at.asc())
            .all()
        )

        last_balance = prev_balance
        last_date = month_start

        for record in daily_records:
            if last_balance is not None:
                usage = last_balance - record.balance
                if usage > 0:
                    day_key = record.recorded_at.strftime('%Y-%m-%d')
                    usage_by_date[day_key] += usage
                    total_usage += usage
            last_balance = record.balance
            last_date = record.recorded_at

    report_rows = [
        {'date': day, 'usage': usage}
        for day, usage in sorted(usage_by_date.items())
    ]

    return {
        'success': True,
        'report': report_rows,
        'total_usage': total_usage,
        'month_label': current_time.strftime('%B %Y'),
        'month_start': month_start.isoformat(),
    }


# Messenger helper functions removed


def _format_meter_list_message(meters: List[Dict[str, Any]]) -> str:
    message_lines = ['📊 Your meters:']
    for idx, meter in enumerate(meters, start=1):
        line = [f"{idx}. {meter['name']} ({meter['number']})"]
        if meter.get('last_balance') is not None:
            line.append(f"Last balance: {meter['last_balance']} BDT")
        line.append(f"Min balance: {meter['min_balance']} BDT")
        message_lines.append('\n'.join(line))
    return '\n\n'.join(message_lines)


def _format_balance_results(results: List[Dict[str, Any]]) -> str:
    lines = ['💰 Balance report:']
    total_delta = 0.0
    total_prev = 0.0

    for idx, result in enumerate(results, start=1):
        if result.get('error'):
            lines.append(f"{idx}. {result['name']} ({result['number']}): ❌ {result['error']}")
            continue

        alert = '⚠️' if result.get('alert') else '✅'
        meter_line = [f"{idx}. {alert} {result['name']} ({result['number']})"]

        balance = result.get('balance')
        delta = result.get('delta')
        delta_percent = result.get('delta_percent')

        # Build delta display
        if delta is not None:
            arrow = '↑' if delta > 0 else ('↓' if delta < 0 else '→')
            pct_text = f" ({delta_percent:+.2f}%)" if delta_percent is not None else ''
            meter_line.append(f"Balance: {float(balance):.2f} BDT ({arrow}{abs(delta):.2f} BDT since yesterday{pct_text})")
            total_delta += float(delta)
            if result.get('yesterday_balance') is not None:
                try:
                    total_prev += float(result.get('yesterday_balance') or 0)
                except Exception:
                    pass
        else:
            meter_line.append(f"Balance: {float(balance):.2f} BDT (Yesterday: Not available)")

        if result.get('alert'):
            meter_line.append(f"🚨 Below minimum ({result.get('min_balance')} BDT)!")

        lines.append('\n'.join(meter_line))

    # Insert total change summary if we have any meters
    if total_prev:
        try:
            total_pct = (total_delta / total_prev) * 100.0
            lines.insert(1, f"Total change since yesterday: {total_delta:+.2f} BDT ({total_pct:+.2f}%)")
        except Exception:
            lines.insert(1, f"Total change since yesterday: {total_delta:+.2f} BDT")
    else:
        lines.insert(1, f"Total change since yesterday: {total_delta:+.2f} BDT")

    return '\n\n'.join(lines)


def _format_usage_table(report_rows: List[Dict[str, Any]], total_usage: float, month_label: str) -> str:
    if not report_rows:
        return 'No usage data available yet for this month. Try running a balance check first.'
    header = [f"📅 Usage report for {month_label}", 'Date         Usage (BDT)', '------------------------']
    for row in report_rows:
        header.append(f"{row['date']}   {float(row['usage']):.2f}")
    header.append(f"\nTotal: {float(total_usage):.2f} BDT")
    return '\n'.join(header)


# Messenger state handling removed


# Messenger command handling removed


# Messenger event handler removed


def _admin_unauthorized():
    response = jsonify({'success': False, 'error': 'Unauthorized'})
    response.status_code = 401
    response.headers['WWW-Authenticate'] = 'Basic realm="Admin"'
    return response


def require_admin_auth(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not ADMIN_AUTH_ENABLED:
            return view_func(*args, **kwargs)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.lower().startswith('basic '):
            return _admin_unauthorized()
        try:
            encoded = auth_header.split(' ', 1)[1]
            decoded = base64.b64decode(encoded).decode('utf-8')
            username, _, password = decoded.partition(':')
        except Exception:  # noqa: BLE001
            return _admin_unauthorized()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return view_func(*args, **kwargs)
        return _admin_unauthorized()

    return wrapper

# NESCO scraping configuration
NESCO_PANEL_URL = os.getenv('NESCO_PANEL_URL', 'https://customer.nesco.gov.bd/pre/panel')
BALANCE_INPUT_INDEX = int(os.getenv('NESCO_BALANCE_INPUT_INDEX', '14'))


def fetch_nesco_balance(meter_number: str) -> float:
    """Fetch the prepaid balance using the official NESCO customer panel."""
    session = requests.Session()

    response_panel = session.get(NESCO_PANEL_URL, timeout=15)
    response_panel.raise_for_status()
    soup_panel = BeautifulSoup(response_panel.text, 'html.parser')

    token_input = soup_panel.find('input', {'name': '_token'})
    if not token_input:
        raise RuntimeError('CSRF _token input not found')
    csrf_token = (token_input.get('value') or '').strip()
    if not csrf_token:
        raise RuntimeError('CSRF token value missing')

    payload = {
        '_token': csrf_token,
        'cust_no': meter_number.strip(),
        'submit': 'রিচার্জ হিস্ট্রি',
    }

    response_result = session.post(NESCO_PANEL_URL, data=payload, timeout=15)
    response_result.raise_for_status()
    soup_result = BeautifulSoup(response_result.text, 'html.parser')

    disabled_inputs = soup_result.find_all('input', {'type': 'text', 'disabled': True})
    if not disabled_inputs:
        raise RuntimeError('No disabled text inputs found in response')

    if BALANCE_INPUT_INDEX >= len(disabled_inputs):
        raise RuntimeError(
            f'BALANCE_INPUT_INDEX {BALANCE_INPUT_INDEX} out of range; found {len(disabled_inputs)} inputs'
        )

    balance_raw = (disabled_inputs[BALANCE_INPUT_INDEX].get('value') or '').strip()
    if not balance_raw:
        raise RuntimeError('Balance field empty or missing')

    return float(balance_raw.replace(',', ''))


def scrape_nesco_balance(meter_number):
    """Wrapper that returns success/error dictionaries for downstream callers."""
    try:
        balance = fetch_nesco_balance(meter_number)
        return {'success': True, 'balance': balance}
    except requests.RequestException as exc:
        logger.error('NESCO request error for %s: %s', meter_number, exc)
        return {'success': False, 'error': f'NESCO request failed: {exc}'}
    except Exception as exc:  # noqa: BLE001
        logger.error('Balance extraction failed for %s: %s', meter_number, exc)
        return {'success': False, 'error': str(exc)}

# API Endpoints
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'timestamp': now().isoformat()})

@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Main webhook for Telegram bot commands"""
    data = request.json
    command = data.get('command')
    telegram_user_id = data.get('telegram_user_id')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400
    
    if command == 'start':
        get_or_create_user(telegram_user_id)
        
        welcome_message = (
            "Welcome to NESCO Prepaid Meter Monitor 👋\n\n"
            "I help you track your NESCO prepaid meter balances right from Telegram.\n\n"
            "This bot is developed by Shahariar Shuvo.\n\n"
            "Commands:\n"
            "/add - Add a meter\n"
            "/list - List your meters\n"
            "/check - Check all balances\n"
            "/remove - Remove a meter\n"
            "/minbalance - Set minimum balance alert\n"
            "/reminder - Toggle daily reminder\n"
        )
        return jsonify({
            'success': True,
            'message': welcome_message
        })
    
    return jsonify({'success': False, 'error': 'Unknown command'})


# Messenger webhook route removed

@app.route('/api/add-meter', methods=['POST'])
def add_meter():
    """Add a new meter for a user"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')
    meter_number = data.get('meter_number')
    meter_name = data.get('meter_name')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = get_or_create_user(telegram_user_id)
    result = add_meter_for_user(user, meter_number, meter_name)
    status = 200 if result.get('success') else 400
    return jsonify(result), status

@app.route('/api/list-meters', methods=['POST'])
def list_meters():
    """List all meters for a user"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    result = list_meters_for_user(user)
    return jsonify(result)

@app.route('/api/check-balances', methods=['POST'])
def check_balances():
    """Check balances for all user meters"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    result = check_balances_for_user(user)
    status = 200 if result.get('success') else 404
    return jsonify(result), status


@app.route('/api/check-balances-nlp', methods=['POST'])
def check_balances_nlp():
    """Fetch balances and return both structured results and an LLM-generated personalized reply.
    Request JSON: { "telegram_user_id": <int>, "language": "bn" }
    """
    data = request.json or {}
    telegram_user_id = data.get('telegram_user_id')
    language = data.get('language', 'bn')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # get structured results
    structured = check_balances_for_user(user)
    if not structured.get('success'):
        return jsonify(structured), 500

    results = structured.get('results', [])

    # Check cache for a recent NLP reply for this user+language
    cache_key = f"nlp:{telegram_user_id}:{language}"
    nlp_reply = None
    now_ts = time.time()
    try:
        with NLP_CACHE_LOCK:
            entry = NLP_CACHE.get(cache_key)
            if entry:
                reply_text, expires_at = entry
                if expires_at > now_ts:
                    logger.info('NLP cache hit for %s', cache_key)
                    nlp_reply = reply_text
                else:
                    # expired
                    NLP_CACHE.pop(cache_key, None)
                    logger.info('NLP cache expired for %s', cache_key)
    except Exception:
        logger.exception('Error reading NLP cache')

    # generate NLP reply using ai_agent (best-effort) if not cached
    if nlp_reply is None:
        try:
            from ai_agent import generate_nlp_reply

            user_display = user.username or f"User {user.telegram_user_id}"
            nlp_reply = generate_nlp_reply(user_display, results, language=language)

            # store in cache (if we got a reply)
            if nlp_reply:
                safe_reply = (nlp_reply[:1000]) if isinstance(nlp_reply, str) else None
                expires_at = time.time() + NLP_CACHE_TTL
                try:
                    with NLP_CACHE_LOCK:
                        NLP_CACHE[cache_key] = (safe_reply, expires_at)
                        logger.info('Stored NLP reply in cache for %s (ttl=%ds)', cache_key, NLP_CACHE_TTL)
                except Exception:
                    logger.exception('Error writing NLP cache')
        except Exception as exc:  # noqa: BLE001
            logger.exception('Failed to generate nlp reply: %s', exc)
            nlp_reply = None

    response = {
        'success': True,
        'results': results,
        'timestamp': structured.get('timestamp'),
        'nlp_reply': nlp_reply,
    }

    return jsonify(response)


@app.route('/api/check-balances-cached', methods=['POST'])
def check_balances_cached():
    """Return cached (DB-only) balances for fast replies.
    Request JSON: { "telegram_user_id": <int> }
    """
    data = request.json or {}
    telegram_user_id = data.get('telegram_user_id')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    result = cached_check_balances_for_user(user)
    status = 200 if result.get('success') else 404
    return jsonify(result), status

@app.route('/api/remove-meter', methods=['POST'])
def remove_meter():
    """Remove a meter"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')
    meter_id = data.get('meter_id')

    if telegram_user_id is None or meter_id is None:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    result = remove_meter_for_user(user, meter_id)
    status = 200 if result.get('success') else 404
    return jsonify(result), status

@app.route('/api/set-min-balance', methods=['POST'])
def set_min_balance():
    """Set minimum balance threshold"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')
    meter_id = data.get('meter_id')
    min_balance = data.get('min_balance')

    if telegram_user_id is None or meter_id is None or min_balance is None:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    result = set_min_balance_for_user(user, meter_id, min_balance)
    status = 200 if result.get('success') else 404
    return jsonify(result), status

@app.route('/api/toggle-reminder', methods=['POST'])
def toggle_reminder():
    """Toggle daily reminder"""
    data = request.json
    telegram_user_id = data.get('telegram_user_id')

    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = get_or_create_user(telegram_user_id)
    result = toggle_reminder_for_user(user)
    return jsonify(result)


@app.route('/api/usage-report', methods=['POST'])
def usage_report():
    """Return current month's per-day usage summary for a user."""
    data = request.json or {}
    telegram_user_id = data.get('telegram_user_id')
    if telegram_user_id is None:
        return jsonify({'success': False, 'error': 'telegram_user_id is required'}), 400

    user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    result = build_usage_report_for_user(user)
    status = 200 if result.get('success') else 404
    return jsonify(result), status

@app.route('/api/daily-reminder', methods=['GET'])
def daily_reminder():
    """Cron endpoint for daily reminders"""
    users_with_reminders = User.query.filter_by(daily_reminder_enabled=True).all()
    
    reminders_sent = 0
    for user in users_with_reminders:
        if not user.meters:
            continue

        # Build balance message
        try:
            result = check_balances_for_user(user)
            if result.get('success'):
                results = result.get('results', [])

                # Compute total used since yesterday: sum of decreases (yesterday - current) across meters
                used_since_yesterday = 0.0
                for r in results:
                    d = r.get('delta')
                    if d is not None and float(d) < 0:
                        used_since_yesterday += -float(d)

                # Customer display name
                customer_name = user.username or f"User {user.telegram_user_id}"

                # Determine a low balance threshold to display (use smallest min_balance across meters or default)
                thresholds = [float(r.get('min_balance')) for r in results if r.get('min_balance') is not None]
                low_balance_threshold = int(min(thresholds)) if thresholds else int(50)

                # Build the reminder message using the requested template
                date_str = now().strftime('%Y-%m-%d')
                lines = []
                lines.append('🔔 Daily Meter Balance Reminder')
                lines.append('')
                lines.append(f'📅 Date: {date_str}')
                lines.append('')
                lines.append(f'🧾 Total used since yesterday: {used_since_yesterday:.2f} BDT')
                lines.append('')

                for idx, r in enumerate(results, start=1):
                    if r.get('error'):
                        lines.append(f"{idx}) ❌ {r.get('name')} ({r.get('number')}): {r.get('error')}")
                        continue

                    status_icon = '✅' if not r.get('alert') else '⚠️'
                    lines.append(f"{idx}) {status_icon} {customer_name} ({r.get('number')})")
                    lines.append(f"   Current balance: {float(r.get('balance')):.2f} BDT")
                    lines.append('')

    

                message = '\n'.join(lines)
            else:
                message = result.get('error', 'Unable to fetch balances right now.')
        except Exception as exc:  # defensive
            logger.exception('Error preparing reminder for user %s: %s', user.telegram_user_id, exc)
            message = 'Unable to fetch your balances right now.'

        sent_any = False

        # Send via Telegram if telegram_user_id available
        try:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if bot_token and user.telegram_user_id:
                payload = {
                    'chat_id': user.telegram_user_id,
                    'text': message,
                }
                resp = requests.post(f'https://api.telegram.org/bot{bot_token}/sendMessage', json=payload, timeout=10)
                if resp.ok:
                    sent_any = True
                else:
                    logger.warning('Failed to send Telegram reminder to %s: %s', user.telegram_user_id, resp.text[:200])
        except requests.RequestException as exc:  # noqa: BLE001
            logger.exception('Telegram send error for user %s: %s', user.telegram_user_id, exc)

        # Messenger integration removed: only Telegram reminder sending is performed

        if sent_any:
            reminders_sent += 1
            logger.info('Reminder sent for user %s', user.telegram_user_id)
    
    return jsonify({'success': True, 'reminders_sent': reminders_sent})

@app.route('/api/scrape-nesco', methods=['POST'])
def scrape_endpoint():
    """Direct scraping endpoint for testing"""
    data = request.json
    meter_number = data.get('meter_number')
    
    if not meter_number:
        return jsonify({'success': False, 'error': 'meter_number required'}), 400
    
    result = scrape_nesco_balance(meter_number)
    return jsonify(result)


@app.route('/admin/api/stats', methods=['GET'])
@require_admin_auth
def admin_stats():
    """Return aggregated metrics for the admin dashboard."""
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_meters = db.session.query(func.count(Meter.id)).scalar() or 0
    reminders_enabled = db.session.query(func.count(User.id)).filter(User.daily_reminder_enabled.is_(True)).scalar() or 0
    active_since = now() - timedelta(days=1)
    active_users_24h = (
        db.session.query(func.count(func.distinct(Meter.user_id)))
        .join(BalanceHistory, BalanceHistory.meter_id == Meter.id)
        .filter(BalanceHistory.recorded_at >= active_since)
        .scalar()
        or 0
    )

    latest_users = (
        User.query.order_by(User.created_at.desc()).limit(5).all()
    )
    latest_meters = (
        Meter.query.order_by(Meter.created_at.desc()).limit(5).all()
    )
    recent_activity = (
        BalanceHistory.query.order_by(BalanceHistory.recorded_at.desc()).limit(5).all()
    )

    total_storage_bytes = 0
    try:
        size_result = db.session.execute(text("SELECT pg_database_size(current_database())")).scalar()
        if size_result is not None:
            total_storage_bytes = int(size_result)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Unable to compute database size: %s', exc)

    def serialize_user(user: User):
        return {
            'id': user.id,
            'username': user.username,
            'telegram_user_id': user.telegram_user_id,
            'created_at': user.created_at.isoformat() if user.created_at else None,
        }

    def serialize_meter(meter: Meter):
        owner = meter.user.username if meter.user and meter.user.username else f"User {meter.user.telegram_user_id}" if meter.user else 'Unknown'
        return {
            'id': meter.id,
            'name': meter.meter_name,
            'number': meter.meter_number,
            'owner': owner,
            'created_at': meter.created_at.isoformat() if meter.created_at else None,
        }

    def serialize_activity(entry: BalanceHistory):
        meter = Meter.query.get(entry.meter_id)
        user_label = meter.user.username if meter and meter.user and meter.user.username else f"User {meter.user.telegram_user_id}" if meter and meter.user else 'Unknown'
        return {
            'id': entry.id,
            'meter_name': meter.meter_name if meter else 'Unknown',
            'meter_number': meter.meter_number if meter else 'N/A',
            'user': user_label,
            'balance': entry.balance,
            'recorded_at': entry.recorded_at.isoformat() if entry.recorded_at else None,
        }

    return jsonify({
        'success': True,
        'stats': {
            'total_users': total_users,
            'total_meters': total_meters,
            'reminders_enabled': reminders_enabled,
            'active_users_24h': active_users_24h,
            'total_storage_bytes': total_storage_bytes,
            'latest_users': [serialize_user(u) for u in latest_users],
            'latest_meters': [serialize_meter(m) for m in latest_meters],
            'recent_activity': [serialize_activity(a) for a in recent_activity],
        }
    })


@app.route('/admin/api/broadcast', methods=['POST'])
@require_admin_auth
def admin_broadcast():
    data = request.json or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'error': 'Message is required.'}), 400

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot token not configured.'}), 500

    users = User.query.with_entities(User.telegram_user_id).all()
    total_targets = len(users)
    sent = 0
    failures = 0
    errors: list[dict[str, str | int]] = []

    for (telegram_user_id,) in users:
        if not telegram_user_id:
            continue
        payload = {
            'chat_id': telegram_user_id,
            'text': message,
        }
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json=payload,
                timeout=10,
            )
            if resp.ok:
                sent += 1
            else:
                failures += 1
                errors.append({'user': telegram_user_id, 'error': resp.text[:200]})
        except requests.RequestException as exc:  # noqa: BLE001
            failures += 1
            errors.append({'user': telegram_user_id, 'error': str(exc)[:200]})

    return jsonify({
        'success': True,
        'requested': total_targets,
        'sent': sent,
        'failed': failures,
        'errors': errors[:10],
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Start internal scheduler to dispatch daily reminders (if enabled)
    if ENABLE_INTERNAL_SCHEDULER:
        try:
            hour, minute = DAILY_REMINDER_TIME.split(':')
            hour = int(hour)
            minute = int(minute)
        except Exception:
            hour, minute = 19, 50

        scheduler = BackgroundScheduler(timezone=TZ)

        def _scheduled_trigger():
            """Wrapper to call the reminder endpoint inside app context."""
            with app.app_context():
                try:
                    logger.info('Scheduled reminder job triggered at %s', now().isoformat())
                    # reuse the same logic as the route
                    daily_reminder()
                except Exception as exc:  # defensive
                    logger.exception('Scheduled reminder job failed: %s', exc)

    # Schedule the job at configured local time daily
    logger.info('Scheduling daily reminders at %02d:%02d %s', hour, minute, TIMEZONE)
    scheduler.add_job(_scheduled_trigger, 'cron', hour=hour, minute=minute)
    scheduler.start()
    logger.info('Internal scheduler started')

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
