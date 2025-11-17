# NESCO Chat Bots - Backend

Complete Flask backend for NESCO prepaid meter monitoring via Telegram and Facebook Messenger.

## 🚀 Quick Start

**New to this project? Start here:**

👉 **[Complete Setup Guide](SETUP.md)** - Step-by-step instructions to connect the Telegram bot to the backend

### TL;DR - Fast Setup

1. **Create a Telegram bot** with [@BotFather](https://t.me/BotFather)
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your bot token and database URL
   ```
4. **Initialize database:**
   ```bash
   python -c "from app import app, db; app.app_context().push(); db.create_all()"
   ```
5. **Run backend:**
   ```bash
   python app.py
   ```
6. **Run bot (in another terminal):**
   ```bash
   python bot.py
   ```

That's it! Open Telegram and test your bot with `/start`

## 📚 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Command reference and common tasks
- **[SETUP.md](SETUP.md)** - Complete setup instructions
- **[README.md](#)** (this file) - Quick reference and API documentation

## 🚀 Quick Deploy to Heroku

### Prerequisites
1. Heroku account
2. Heroku CLI installed
3. PostgreSQL add-on (automatically provisioned)

### Deployment Steps

```bash
# 1. Clone/navigate to project
cd backend

# 2. Login to Heroku
heroku login

# 3. Create Heroku app
heroku create your-nesco-bot

# 4. Add PostgreSQL
heroku addons:create heroku-postgresql:essential-0

# 5. Deploy
git init
git add .
git commit -m "Initial commit"
heroku git:remote -a your-nesco-bot
git push heroku main

# 6. Initialize database
heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 7. Check logs
heroku logs --tail
```

### Environment Variables

Set these in Heroku dashboard or CLI:

```bash
# Database URL (auto-set by Heroku PostgreSQL)
DATABASE_URL=postgresql://...

# Optional: For bot script
TELEGRAM_BOT_TOKEN=your_token_here

# Optional: Facebook Messenger bot
MESSENGER_PAGE_ACCESS_TOKEN=your_page_token
MESSENGER_VERIFY_TOKEN=your_verify_token
# MESSENGER_APP_SECRET=optional_signature_secret
```

## 🤖 Running the Telegram Bot

### Option 1: Run on Same Heroku Dyno (Recommended for testing)

Add to `Procfile`:
```
web: gunicorn app:app
worker: python bot.py
```

Then scale worker:
```bash
heroku ps:scale worker=1
```

### Option 2: Run Locally

```bash
pip install -r requirements.txt
export BACKEND_URL=https://your-app.herokuapp.com
export TELEGRAM_BOT_TOKEN=your_token
python bot.py
```

### Option 3: Separate Heroku App for Bot

```bash
heroku create your-nesco-bot-worker
# Add bot.py and requirements.txt
# Set BACKEND_URL to your API dyno
```

## 💬 Facebook Messenger Webhook: Quick Setup & Testing

You can test the Messenger webhook locally using ngrok. Example below uses:

**Webhook URL:** `https://unbet-unhomogenized-marita.ngrok-free.dev/webhook/messenger`

### 1. Prepare Environment

Edit your `.env` (or `.env.example`) and set:

```
MESSENGER_PAGE_ACCESS_TOKEN=your_facebook_page_access_token
MESSENGER_VERIFY_TOKEN=choose_a_random_verify_token
# Optional for signature validation:
# MESSENGER_APP_SECRET=your_meta_app_secret
```

### 2. Start the Backend

```bash
cd backend
python app.py
```

### 3. Expose with ngrok

```bash
ngrok http 5000
# Use the HTTPS URL shown (e.g. https://unbet-unhomogenized-marita.ngrok-free.dev)
```

### 4. Configure Facebook App Webhook

- Go to your Meta App dashboard → Messenger → Webhooks
- Callback URL: `https://unbet-unhomogenized-marita.ngrok-free.dev/webhook/messenger`
- Verify Token: (must match your `MESSENGER_VERIFY_TOKEN`)
- Subscribe to `messages` and `messaging_postbacks`

### 5. Test Webhook Verification (GET)

```bash
curl "https://unbet-unhomogenized-marita.ngrok-free.dev/webhook/messenger?hub.mode=subscribe&hub.verify_token=choose_a_random_verify_token&hub.challenge=12345"
# Should return: 12345
```

### 6. Test Webhook Delivery (POST)

Create a file `payload.json`:
```json
{
  "object": "page",
  "entry": [
    {
      "id": "PAGE_ID",
      "time": 1234567890,
      "messaging": [
        {
          "sender": {"id": "TEST_PSID"},
          "recipient": {"id": "PAGE_ID"},
          "timestamp": 1234567890,
          "message": {"text": "hello from curl test"}
        }
      ]
    }
  ]
}
```

Send the POST (no signature, works if MESSENGER_APP_SECRET is not set):
```bash
curl -X POST "https://unbet-unhomogenized-marita.ngrok-free.dev/webhook/messenger" \
  -H "Content-Type: application/json" \
  --data-binary @payload.json
```

If you set `MESSENGER_APP_SECRET`, you must add a valid `X-Hub-Signature-256` header:
```bash
# Compute signature in Python:
python -c "import hmac,hashlib; s=b'your_meta_app_secret'; d=open('payload.json','rb').read(); print('sha256='+hmac.new(s,d,hashlib.sha256).hexdigest())"
# Use the output in the header below:
curl -X POST "https://unbet-unhomogenized-marita.ngrok-free.dev/webhook/messenger" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  --data-binary @payload.json
```

### 7. See logs and debug

Check your Flask server output for delivery and handler logs. If signature is missing/invalid, you'll see a warning and a 403 error.

---

You can run the same NESCO assistant on Facebook Messenger. The Flask backend now exposes `/webhook/messenger` supporting verification and message delivery.

### Prerequisites

1. Facebook Page + Facebook App with Messenger product enabled.
2. Configure **Page Access Token** and **Verify Token** in `.env` (see variables above).
3. Publicly accessible HTTPS endpoint (Heroku, Render, etc.) so Meta can reach your webhook.

### Setup Steps

1. Deploy the backend so `https://your-domain/webhook/messenger` is reachable.
2. In Meta App dashboard → **Messenger** → **Webhooks**, subscribe your page:
  - Callback URL: `https://your-domain/webhook/messenger`
  - Verify Token: the same string you set in `MESSENGER_VERIFY_TOKEN`
  - Subscriptions: `messages` and `messaging_postbacks`
3. Add the generated **Page Access Token** to `MESSENGER_PAGE_ACCESS_TOKEN`.
4. (Optional) Set `MESSENGER_APP_SECRET` if you plan to validate signatures.
5. Click **Add Subscriptions** and send yourself a "Get Started" message in Messenger to initialize the profile.

### Features

- Quick replies for `Check Balances`, `Add Meter`, `List Meters`, and `Usage Report`.
- Guided flow to collect meter number & nickname.
- Reuses the same scraping, reminders, and usage report logic as the Telegram bot.
- Users are mapped to virtual IDs derived from their PSID, so no extra schema changes are required beyond the `messenger_profiles` table (auto-created by `db.create_all()`).

## 💬 Facebook Messenger Bot (Optional)

Messenger support is built into `app.py`, so you only need to provide Meta credentials.

1. **Create a Meta App & Page**
  - In [Meta for Developers](https://developers.facebook.com/), create an app and add the *Messenger* product.
  - Connect the app to the Facebook Page you want to respond from.
2. **Generate credentials**
  - Create a Page Access Token and paste it into `MESSENGER_PAGE_ACCESS_TOKEN`.
  - Define any string for `MESSENGER_VERIFY_TOKEN` (you will reuse it during webhook setup).
  - (Optional) Add `MESSENGER_APP_SECRET` to enable request signature validation.
3. **Expose the webhook**
  - Deploy the backend (or run locally with a tunnel such as `ngrok`) so that `https://<host>/webhook/messenger` is reachable.
  - In the Messenger settings, configure the webhook URL and use the same verify token from step 2. Subscribe to `messages` and `messaging_postbacks` events.
4. **Test it**
  - Open the Messenger conversation with your Page and send commands such as `start`, `add`, `list`, `check`, `reminder`, or `report`.

Messenger users get the same meter management experience as Telegram users, including guided meter onboarding and daily reminder toggles.

## 📡 API Endpoints

### Health Check
```bash
GET /health
```

### Messenger Webhook
- **GET `/webhook/messenger`** – Meta verification endpoint (requires `hub.verify_token`)
- **POST `/webhook/messenger`** – Receives Messenger events (`messages`, `messaging_postbacks`)

> ⚠️ Returns `503` when Messenger credentials are not configured.

### Add Meter
```bash
POST /api/add-meter
{
  "telegram_user_id": 123456789,
  "meter_number": "31041051783",
  "meter_name": "Home"
}
```

### Check Balances
```bash
POST /api/check-balances
{
  "telegram_user_id": 123456789
}
```

### List Meters
```bash
POST /api/list-meters
{
  "telegram_user_id": 123456789
}
```

### Remove Meter
```bash
POST /api/remove-meter
{
  "telegram_user_id": 123456789,
  "meter_id": 1
}
```

### Set Minimum Balance
```bash
POST /api/set-min-balance
{
  "telegram_user_id": 123456789,
  "meter_id": 1,
  "min_balance": 50.0
}
```

### Toggle Daily Reminder
```bash
POST /api/toggle-reminder
{
  "telegram_user_id": 123456789
}
```

### Daily Reminder (Cron)
```bash
GET /api/daily-reminder
```

### Direct NESCO Scraping (Testing)
```bash
POST /api/scrape-nesco
{
  "meter_number": "31041051783"
}
```

## 🕐 Setting Up Daily Reminders (11 AM)

### Option 1: Heroku Scheduler (Free Add-on)

```bash
heroku addons:create scheduler:standard
heroku addons:open scheduler
```

Add job:
- Command: `curl https://your-app.herokuapp.com/api/daily-reminder`
- Frequency: Daily at 11:00 AM (your timezone)

### Option 2: External Cron (cron-job.org)

1. Go to cron-job.org
2. Create free account
3. Add cron job:
   - URL: `https://your-app.herokuapp.com/api/daily-reminder`
   - Schedule: `0 11 * * *`
   - Timezone: Your timezone

## 🧪 Testing

### Test API locally
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export DATABASE_URL=postgresql://localhost/nesco_bot
export FLASK_APP=app.py

# Run migrations
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run server
python app.py
```

### Test scraping
```bash
curl -X POST https://your-app.herokuapp.com/api/scrape-nesco \
  -H "Content-Type: application/json" \
  -d '{"meter_number": "31041051783"}'
```

### Test bot locally
```bash
export BACKEND_URL=http://localhost:5000
export TELEGRAM_BOT_TOKEN=your_token
python bot.py
```

## 📊 Database Schema

### users
- id (PK)
- telegram_user_id (unique)
- username
- daily_reminder_enabled
- reminder_time
- created_at

### meters
- id (PK)
- user_id (FK)
- meter_number
- meter_name
- min_balance
- last_balance
- last_checked
- created_at

### balance_history
- id (PK)
- meter_id (FK)
- balance
- recorded_at

## 🐛 Troubleshooting

### Database connection error
```bash
# Check DATABASE_URL
heroku config:get DATABASE_URL

# Reset database
heroku pg:reset DATABASE_URL
heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### Bot not responding
```bash
# Check logs
heroku logs --tail --app your-bot-app

# Restart
heroku restart
```

### Scraping fails
- Check NESCO website is accessible
- Verify meter number format
- Check response in logs

## 📝 Telegram Bot Commands

- `/start` - Welcome message
- `/add` - Add new meter (conversational)
- `/list` - List all your meters
- `/check` - Check balances + yesterday usage
- `/remove` - Remove a meter
- `/minbalance` - Set minimum balance alert
- `/reminder` - Toggle daily reminder (11 AM)
- `/help` - Show help

## 💰 Cost Estimate

- **Heroku Eco Dyno**: $5/month (or free 1000 hours/month)
- **PostgreSQL**: Included with Essential-0
- **Scheduler**: Free add-on
- **Total**: $0-5/month

## 🎓 GitHub Student Pack

With student pack, you get:
- **$13/month Heroku credits** = Free hosting
- **DigitalOcean** = Alternative hosting
- Deploy to either platform at no cost!

## 📚 Resources

- [Heroku Python Docs](https://devcenter.heroku.com/articles/getting-started-with-python)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [NESCO Prepaid Portal](https://prepaid.nescopower.com)

## 🔒 Security Notes

- Never commit `.env` file
- Use Heroku config vars for secrets
- DATABASE_URL is auto-managed by Heroku
- Bot token should be kept private

## ✅ Deployment Checklist

- [ ] Create Heroku app
- [ ] Add PostgreSQL addon
- [ ] Deploy code
- [ ] Initialize database
- [ ] Set environment variables
- [ ] Create Telegram bot with @BotFather
- [ ] Configure bot token
- [ ] Test all commands
- [ ] Set up daily reminder (Scheduler or cron-job.org)
- [ ] Monitor logs

---

**Ready to deploy!** Follow the steps above and your bot will be live in 15 minutes.
