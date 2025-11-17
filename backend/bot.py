import os
import logging
import requests
import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from dotenv import load_dotenv

from ai_agent import ai_enabled, interpret_message

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')
AI_AGENT_ACTIVE = ai_enabled()

# Conversation states
ADD_METER_NUMBER, ADD_METER_NAME, SET_MIN_METER, SET_MIN_AMOUNT = range(4)

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def format_report_timestamp(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        # fromisoformat handles YYYY-MM-DDTHH:MM:SS.sss
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d   T    %H:%M:%S")
    except ValueError:
        return raw


def build_usage_table(rows):
    header = "Date         Usage (BDT)"
    separator = "-----------------------"
    lines = [header, separator]
    for row in rows:
        date = row.get('date', '—')
        usage = row.get('usage', 0)
        lines.append(f"{date}   {float(usage):.2f}")
    return "\n".join(lines)


# Helper function to call backend
def call_backend(endpoint, data=None, method='POST'):
    try:
        url = f"{BACKEND_URL}{endpoint}"
        logger.info('Calling backend %s %s', method, url)
        if method == 'POST':
            response = requests.post(url, json=data, timeout=30)
        else:
            response = requests.get(url, params=data, timeout=30)
        logger.info('Backend responded %s for %s', response.status_code, url)
        try:
            return response.json()
        except Exception as exc:
            logger.exception('Failed to decode JSON from backend %s: %s', url, exc)
            return {'success': False, 'error': 'Invalid JSON from backend'}
    except Exception as e:
        logger.exception('Backend call failed: %s', e)
        return {'success': False, 'error': str(e)}

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = call_backend('/webhook/telegram', {
        'command': 'start',
        'telegram_user_id': user_id
    })
    
    await update.message.reply_text(result.get('message', 'Welcome to NESCO Meter Bot!'))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 *Available Commands:*

/start - Start the bot
/add - Add a new meter
/list - List all your meters
/check - Check balances for all meters
/remove - Remove a meter
/minbalance - Set minimum balance alert
/reminder - Toggle daily reminder (11 AM)
/report - Monthly usage report for current month
/about - Learn about the creator
/help - Show this help message

💡 *How it works:*
1. Add your meter(s) with /add
2. Check balances anytime with /check
3. Get alerts when balance is low
4. Receive daily reminders at 11 AM
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Add meter conversation
async def add_meter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Let's add a new meter!\n\n"
        "Please send your meter number (e.g., 31041051783)\n"
        "Send /cancel to abort."
    )
    return ADD_METER_NUMBER

async def add_meter_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meter_number = update.message.text.strip()
    
    if not meter_number.isdigit():
        await update.message.reply_text("❌ Please send a valid meter number (only digits)")
        return ADD_METER_NUMBER
    
    context.user_data['meter_number'] = meter_number
    await update.message.reply_text("Great! Now send a name for this meter (e.g., Home, Shop, Office)")
    return ADD_METER_NAME

async def add_meter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meter_name = update.message.text.strip()
    meter_number = context.user_data['meter_number']
    user_id = update.effective_user.id
    
    await update.message.reply_text("⏳ Adding meter and verifying with NESCO...")
    
    result = call_backend('/api/add-meter', {
        'telegram_user_id': user_id,
        'meter_number': meter_number,
        'meter_name': meter_name
    })
    
    if result.get('success'):
        await update.message.reply_text(result['message'])
    else:
        await update.message.reply_text(f"❌ Error: {result.get('error', 'Unknown error')}")
    
    context.user_data.clear()
    return ConversationHandler.END

async def list_meters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = call_backend('/api/list-meters', {'telegram_user_id': user_id})
    
    if not result.get('success'):
        await update.message.reply_text(f"❌ Error: {result.get('error')}")
        return
    
    meters = result.get('meters', [])
    if not meters:
        await update.message.reply_text(result.get('message', 'No meters found'))
        return
    
    message = "📊 *Your Meters:*\n\n"
    for i, meter in enumerate(meters, 1):
        message += f"{i}. *{meter['name']}*\n"
        message += f"   Number: `{meter['number']}`\n"
        message += f"   Min Balance: {meter['min_balance']} BDT\n"
        if meter['last_balance']:
            message += f"   Last Balance: {meter['last_balance']} BDT\n"
        message += "\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def check_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # First: try to fetch a fast DB-only cached snapshot and send it immediately.
    loop = asyncio.get_running_loop()
    try:
        cached = await loop.run_in_executor(None, call_backend, '/api/check-balances-cached', {'telegram_user_id': user_id})
    except Exception as exc:
        logger.exception('Cached call failed: %s', exc)
        cached = None

    if cached and cached.get('success') and cached.get('results'):
        results = cached.get('results', [])
        header_ts = cached.get('timestamp') or ''
        snapshot_lines = []
        snapshot_lines.append('🔎 Quick (cached) balances:')
        if header_ts:
            snapshot_lines.append(f'Last snapshot: {format_report_timestamp(header_ts)}')

        for r in results[:6]:
            if r.get('error'):
                snapshot_lines.append(f"• {r.get('name')} ({r.get('number')}): ❌ {r.get('error')}")
                continue
            bal = r.get('balance')
            try:
                bal_text = f"{float(bal):.2f} BDT"
            except Exception:
                bal_text = str(bal)
            emoji = '⚠️' if r.get('alert') else '✅'
            snapshot_lines.append(f"• {emoji} {r.get('name')}: {bal_text}")

        snapshot_text = '\n'.join(snapshot_lines)
        try:
            await context.bot.send_message(chat_id=chat_id, text=snapshot_text)
        except Exception:
            logger.exception('Failed to send cached snapshot to %s', chat_id)
    else:
        # no cached snapshot available; send a short acknowledgement so the user sees activity
        try:
            await update.message.reply_text("⏳ Checking balances... I'll send the full result here shortly.")
        except Exception:
            logger.exception('Failed to send ack to %s', chat_id)

    # Schedule the long-running backend call in background so we don't block the handler
    async def _bg_check_and_send(user_id: int, chat_id: int, language: str = 'bn'):
        loop = asyncio.get_running_loop()
        try:
            if AI_AGENT_ACTIVE:
                result = await loop.run_in_executor(None, call_backend, '/api/check-balances-nlp', {'telegram_user_id': user_id, 'language': language})
                # send NLP reply first if available
                if result and result.get('nlp_reply'):
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=result.get('nlp_reply'))
                    except Exception:
                        logger.exception('Failed to send nlp_reply to %s', chat_id)
                if result and result.get('results'):
                    results = result.get('results')
                    timestamp = result.get('timestamp')
                else:
                    result = await loop.run_in_executor(None, call_backend, '/api/check-balances', {'telegram_user_id': user_id})
                    timestamp = result.get('timestamp')
                    results = result.get('results', [])
            else:
                result = await loop.run_in_executor(None, call_backend, '/api/check-balances', {'telegram_user_id': user_id})
                results = result.get('results', [])
                timestamp = result.get('timestamp')

            if not result.get('success'):
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {result.get('error')}")
                return

            # build human-friendly message
            header_timestamp = format_report_timestamp(timestamp) if timestamp else result.get('timestamp', '')
            message = "💰 *Balance Report*\n"
            if header_timestamp:
                message += f"_{header_timestamp}_\n\n"
            else:
                message += "\n"

            for i, meter in enumerate(results, 1):
                if 'error' in meter:
                    message += f"{i}. *{meter['name']}* ({meter['number']})\n"
                    message += f"   ❌ Error: {meter['error']}\n\n"
                else:
                    alert_emoji = "⚠️" if meter.get('alert') else "✅"
                    message += f"{i}. {alert_emoji} *{meter['name']}* ({meter['number']})\n"
                    try:
                        balance_val = float(meter.get('balance', 0))
                    except Exception:
                        balance_val = meter.get('balance')

                    delta = meter.get('delta')
                    delta_pct = meter.get('delta_percent')

                    if delta is not None:
                        arrow = '↑' if delta > 0 else ('↓' if delta < 0 else '→')
                        pct_text = f" ({delta_pct:+.2f}%)" if delta_pct is not None else ''
                        message += f"   Current: *{balance_val:.2f} BDT* ({arrow}{abs(delta):.2f} BDT since yesterday{pct_text})\n"
                    else:
                        message += f"   Current: *{balance_val:.2f} BDT*\n"
                        message += f"   Yesterday: Not available yet\n"

                    if meter.get('alert'):
                        message += f"   🚨 Below minimum ({meter['min_balance']} BDT)!\n"

                    message += "\n"

            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as exc:
            logger.exception('Background check failed for %s: %s', user_id, exc)
            try:
                await context.bot.send_message(chat_id=chat_id, text='❌ Failed to fetch balances. Please try again later.')
            except Exception:
                pass

    # fire-and-forget
    asyncio.create_task(_bg_check_and_send(user_id, chat_id, 'bn'))

async def usage_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("📈 Fetching this month's usage...")

    result = call_backend('/api/usage-report', {'telegram_user_id': user_id})

    if not result.get('success'):
        await update.message.reply_text(f"❌ Error: {result.get('error', 'Unable to generate report')}")
        return

    rows = result.get('report', [])
    if not rows:
        await update.message.reply_text("No usage recorded yet for this month. Try again after a balance check.")
        return

    month_label = result.get('month_label') or result.get('month_start', '')
    table = build_usage_table(rows)
    total_usage = result.get('total_usage', 0.0)

    message = "📅 *Monthly Usage Report*\n"
    if month_label:
        message += f"_{month_label}_\n\n"
    else:
        message += "\n"
    message += f"{table}\n\nTotal: *{float(total_usage):.2f} BDT*"

    await update.message.reply_text(message, parse_mode='Markdown')

async def remove_meter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = call_backend('/api/list-meters', {'telegram_user_id': user_id})
    
    if not result.get('success') or not result.get('meters'):
        await update.message.reply_text("No meters to remove. Add one with /add")
        return
    
    meters = result['meters']
    keyboard = [[f"{i}. {m['name']} ({m['number']})"] for i, m in enumerate(meters, 1)]
    keyboard.append(["Cancel"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    context.user_data['remove_meters'] = meters
    
    await update.message.reply_text(
        "Select a meter to remove:",
        reply_markup=reply_markup
    )

async def remove_meter_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "Cancel":
        await update.message.reply_text("Cancelled", reply_markup=ReplyKeyboardRemove())
        return
    
    try:
        index = int(text.split('.')[0]) - 1
        meters = context.user_data.get('remove_meters', [])
        meter = meters[index]
        
        user_id = update.effective_user.id
        result = call_backend('/api/remove-meter', {
            'telegram_user_id': user_id,
            'meter_id': meter['id']
        })
        
        if result.get('success'):
            await update.message.reply_text(result['message'], reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(f"❌ Error: {result.get('error')}", reply_markup=ReplyKeyboardRemove())
    except:
        await update.message.reply_text("Invalid selection", reply_markup=ReplyKeyboardRemove())


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    text = update.message.text.strip()
    if not text:
        return

    if context.user_data.get('remove_meters'):
        await remove_meter_confirm(update, context)
        return

    logger.info('Received free-text from %s: %s', update.effective_user.id if update.effective_user else 'unknown', text)

    # Quick heuristic: handle common Bangla (বাংলা) phrases locally to avoid depending on the AI
    text_lower = text.lower()
    bangla_check_triggers = [
        'ব্যালেন্স', 'ব্যালান্স', 'ব্যালেন্স কতো', 'ব্যালেন্স কেমন', 'বাতিল ব্যালেন্স', 'ব্যালেন্সটা',
        'ব্যালেন্স এখন', 'ব্যালান্স কতো', 'বলুন ব্যালেন্স', 'কি ব্যালেন্স', 'এখন ব্যালেন্স'
    ]
    # romanized common phrases
    roman_triggers = ['balance', 'balans', 'balence', 'balans koto']

    for trig in bangla_check_triggers:
        if trig in text_lower:
            logger.info('Bangla trigger matched (%s) for user %s', trig, update.effective_user.id if update.effective_user else 'unknown')
            # direct trigger: call check_balances and return
            await update.message.reply_text("⏳ ব্যালেন্স চেক করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন...")
            await check_balances(update, context)
            return

    for trig in roman_triggers:
        if trig in text_lower:
            logger.info('Roman trigger matched (%s) for user %s', trig, update.effective_user.id if update.effective_user else 'unknown')
            await update.message.reply_text("⏳ Checking balances... This may take a moment...")
            await check_balances(update, context)
            return

    if not AI_AGENT_ACTIVE:
        await update.message.reply_text(
            "Please use the available commands. Send /help to see them.")
        return

    user_id = update.effective_user.id
    meter_context = []
    meter_resp = call_backend('/api/list-meters', {'telegram_user_id': user_id})
    if meter_resp.get('success'):
        meter_context = meter_resp.get('meters', [])

    ai_result = interpret_message(text, meter_context)
    if not ai_result:
        await update.message.reply_text(
            "🤖 I didn't catch that. Try using /help for the list of commands.")
        return

    intent = (ai_result.get('intent') or '').upper()
    response_text = ai_result.get('response')

    if intent == 'CHECK_BALANCES':
        if response_text:
            await update.message.reply_text(response_text)
        await check_balances(update, context)
    elif intent == 'LIST_METERS':
        await list_meters(update, context)
    elif intent == 'START':
        await start(update, context)
    elif intent == 'HELP':
        await help_command(update, context)
    elif intent == 'TOGGLE_REMINDER':
        await toggle_reminder(update, context)
    elif intent == 'USAGE_REPORT':
        await usage_report(update, context)
    elif intent == 'SMALL_TALK':
        if response_text:
            await update.message.reply_text(response_text)
        else:
            await update.message.reply_text("Hi! Send /help to see what I can do.")
    elif intent == 'ADD_METER':
        if response_text:
            await update.message.reply_text(response_text)
        else:
            await update.message.reply_text("Please send your meter number to add it.")
    else:
        if response_text:
            await update.message.reply_text(response_text)
        else:
            await update.message.reply_text(
                "Sorry, I don't understand that yet. Send /help to see available actions.")

# Min balance conversation
async def minbalance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = call_backend('/api/list-meters', {'telegram_user_id': user_id})
    
    if not result.get('success') or not result.get('meters'):
        await update.message.reply_text("No meters found. Add one with /add")
        return ConversationHandler.END
    
    meters = result['meters']
    keyboard = [[f"{i}. {m['name']}"] for i, m in enumerate(meters, 1)]
    keyboard.append(["Cancel"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    context.user_data['minbalance_meters'] = meters
    
    await update.message.reply_text("Select a meter:", reply_markup=reply_markup)
    return SET_MIN_METER

async def minbalance_meter_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "Cancel":
        await update.message.reply_text("Cancelled", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    try:
        index = int(text.split('.')[0]) - 1
        meters = context.user_data.get('minbalance_meters', [])
        meter = meters[index]
        
        context.user_data['selected_meter'] = meter
        await update.message.reply_text(
            f"Send minimum balance amount for *{meter['name']}* (in BDT):",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return SET_MIN_AMOUNT
    except:
        await update.message.reply_text("Invalid selection", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

async def minbalance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        meter = context.user_data['selected_meter']
        user_id = update.effective_user.id
        
        result = call_backend('/api/set-min-balance', {
            'telegram_user_id': user_id,
            'meter_id': meter['id'],
            'min_balance': amount
        })
        
        if result.get('success'):
            await update.message.reply_text(result['message'])
        else:
            await update.message.reply_text(f"❌ Error: {result.get('error')}")
    except ValueError:
        await update.message.reply_text("❌ Please send a valid number")
    
    context.user_data.clear()
    return ConversationHandler.END

async def toggle_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = call_backend('/api/toggle-reminder', {'telegram_user_id': user_id})
    
    if result.get('success'):
        await update.message.reply_text(result['message'])
    else:
        await update.message.reply_text(f"❌ Error: {result.get('error')}")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = (
        "This project is developed by Shahariar Shuvo.\n"
        "To learn more, visit https://shahariarshuvo.me"
    )
    await update.message.reply_text(about_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("list", list_meters))
    application.add_handler(CommandHandler("check", check_balances))
    application.add_handler(CommandHandler("reminder", toggle_reminder))
    application.add_handler(CommandHandler("report", usage_report))
    
    # Add meter conversation
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_meter_start)],
        states={
            ADD_METER_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_meter_number)],
            ADD_METER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_meter_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(add_conv)
    
    # Min balance conversation
    minbalance_conv = ConversationHandler(
        entry_points=[CommandHandler("minbalance", minbalance_start)],
        states={
            SET_MIN_METER: [MessageHandler(filters.TEXT & ~filters.COMMAND, minbalance_meter_selected)],
            SET_MIN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, minbalance_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(minbalance_conv)
    
    # Remove meter (simplified, can be conversation if needed)
    application.add_handler(CommandHandler("remove", remove_meter_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
