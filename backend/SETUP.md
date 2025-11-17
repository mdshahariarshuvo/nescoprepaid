# NESCO Telegram Bot Setup Guide

This guide will help you connect the Telegram bot to the backend and get everything running.

## Overview

The system consists of two main components:
1. **Backend API** (`app.py`) - Flask server that handles meter data and scraping
2. **Telegram Bot** (`bot.py`) - Bot that interacts with users and calls the backend API

## Prerequisites

- Python 3.11+ installed
- PostgreSQL database (local or Heroku)
- Telegram account
- Git installed

## Step 1: Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow the prompts to:
   - Choose a name for your bot (e.g., "NESCO Meter Helper")
   - Choose a username (must end with 'bot', e.g., "nesco_meter_bot")
4. BotFather will give you a **Bot Token** - save this, you'll need it!
   - Example: `6234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789`

## Step 2: Set Up Environment Variables

Create a `.env` file in the `backend` directory:

```bash
cd backend
cp .env.example .env
```

Edit the `.env` file with your configuration:

```env
# Required: Your Telegram Bot Token from BotFather
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional: Facebook Messenger tokens
MESSENGER_PAGE_ACCESS_TOKEN=your_page_token
MESSENGER_VERIFY_TOKEN=some_random_string
# MESSENGER_APP_SECRET=optional_signature_secret

# Backend URL (use appropriate URL for your setup)
# For local development:
BACKEND_URL=http://localhost:5000

# For Heroku deployment:
# BACKEND_URL=https://your-app-name.herokuapp.com

# Database URL (automatically set by Heroku, or configure for local)
# For local PostgreSQL:
DATABASE_URL=postgresql://localhost/nesco_bot
# For Heroku: This is automatically set by the PostgreSQL add-on

# Flask environment
FLASK_APP=app.py
FLASK_ENV=development
```

## Step 3: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

## Step 4: Set Up Database

### Verify Setup (Optional but Recommended)

Before proceeding, you can verify your configuration:

```bash
python test_connection.py
```

This script will check:
- ✓ Environment variables are set correctly
- ✓ Python dependencies are installed
- ✓ Backend is accessible
- ✓ Telegram bot token is valid
- ✓ Database connection works

### Local Development

If using local PostgreSQL:

```bash
# Create database
createdb nesco_bot

# Initialize tables
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### Heroku Deployment

```bash
# PostgreSQL is automatically provisioned
heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

## Step 5: Running the System

You have three options for running the system:

### Option A: Local Development (Recommended for Testing)

Run both components in separate terminals:

**Terminal 1 - Backend API:**
```bash
cd backend
python app.py
```
The backend will start at `http://localhost:5000`

**Terminal 2 - Telegram Bot:**
```bash
cd backend
export TELEGRAM_BOT_TOKEN=your_token_here
export BACKEND_URL=http://localhost:5000
python bot.py
```

### Option B: Heroku Deployment (Single Dyno)

1. Deploy the backend:
```bash
cd backend
heroku create your-nesco-app
heroku addons:create heroku-postgresql:essential-0
git init
git add .
git commit -m "Deploy NESCO backend"
heroku git:remote -a your-nesco-app
git push heroku main
```

2. Set bot token:
```bash
heroku config:set TELEGRAM_BOT_TOKEN=your_token_here
```

3. Update Procfile to run both web and worker:
```
web: gunicorn app:app
worker: python bot.py
```

4. Scale up the worker:
```bash
heroku ps:scale web=1 worker=1
```

### Option C: Separate Heroku Apps (For Production)

**Backend App:**
```bash
heroku create nesco-backend
heroku addons:create heroku-postgresql:essential-0
git push heroku main
```

**Bot App:**
```bash
heroku create nesco-bot
heroku config:set TELEGRAM_BOT_TOKEN=your_token_here
heroku config:set BACKEND_URL=https://nesco-backend.herokuapp.com
# Deploy only bot.py and requirements.txt
```

## Step 6: Test Your Bot

1. Open Telegram
2. Search for your bot using the username you created
3. Send `/start` command
4. Try these commands:
   - `/add` - Add a meter
   - `/list` - List your meters
   - `/check` - Check balances
   - `/help` - See all commands

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather | `6234567890:ABC...` |
| `BACKEND_URL` | Yes | URL of your backend API | `http://localhost:5000` |
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://localhost/nesco_bot` |
| `FLASK_ENV` | No | Flask environment | `development` or `production` |
| `PORT` | No | Backend port (auto-set by Heroku) | `5000` |
| `MESSENGER_PAGE_ACCESS_TOKEN` | No | Facebook Page token used to send Messenger replies | `EAA...` |
| `MESSENGER_VERIFY_TOKEN` | No | Shared secret to validate webhook subscription | `my-secret-token` |

## Bot Commands

Once your bot is running, users can use these commands:

- `/start` - Initialize the bot and create user account
- `/add` - Add a new meter (conversational flow)
- `/list` - List all registered meters
- `/check` - Check balances for all meters
- `/remove` - Remove a meter
- `/minbalance` - Set minimum balance alert threshold
- `/reminder` - Toggle daily reminder (11 AM)
- `/help` - Show help message

## Optional: Facebook Messenger Bot

Want the same experience on Messenger? Follow these steps after deploying the backend:

1. Create a Facebook App + Page and enable the **Messenger** product.
2. Generate a Page Access Token and add it to `MESSENGER_PAGE_ACCESS_TOKEN` (in `.env` or platform config vars).
3. Pick any random string for `MESSENGER_VERIFY_TOKEN`; Meta will send it back when you subscribe the webhook.
4. Expose your backend over HTTPS and set the callback URL to `https://your-domain/webhook/messenger`.
5. Subscribe to the `messages` and `messaging_postbacks` events for your page.
6. Click the "Get Started" button in the page's Messenger thread to initialize the guided onboarding.

The backend reuses the same database and scraping logic; each Messenger PSID is mapped to a deterministic virtual `telegram_user_id`, so no additional bot code is needed beyond enabling the webhook.

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Telegram  │ ◄─────► │   bot.py     │ ◄─────► │   app.py    │
│   Servers   │         │ (Bot Client) │  HTTP   │  (Backend)  │
└─────────────┘         └──────────────┘         └─────────────┘
                                                        │
                                                        ▼
                                                  ┌─────────────┐
                                                  │ PostgreSQL  │
                                                  │  Database   │
                                                  └─────────────┘
                                                        │
                                                        ▼
                                                  ┌─────────────┐
                                                  │    NESCO    │
                                                  │   Website   │
                                                  └─────────────┘
```

## Troubleshooting

### Using the Connection Test Script

Run the diagnostic script to identify issues:

```bash
python test_connection.py
```

This will show you exactly what's working and what needs to be fixed.

### Bot Not Responding

**Check if bot is running:**
```bash
# For local
ps aux | grep bot.py

# For Heroku
heroku ps --app your-bot-app
heroku logs --tail --app your-bot-app
```

**Solution:**
- Verify `TELEGRAM_BOT_TOKEN` is set correctly
- Check bot.py logs for errors
- Ensure backend URL is accessible from bot

### Backend Connection Failed

**Check backend health:**
```bash
# Local
curl http://localhost:5000/health

# Heroku
curl https://your-app.herokuapp.com/health
```

**Solution:**
- Verify backend is running
- Check `BACKEND_URL` environment variable
- Ensure no firewall blocking the connection

### Database Connection Error

**For Heroku:**
```bash
heroku config:get DATABASE_URL
heroku pg:info
```

**Solution:**
- Verify DATABASE_URL is set
- Check PostgreSQL addon is provisioned
- Run database initialization script

### Meter Not Found / Scraping Error

**Solution:**
- Verify meter number is correct (check NESCO website)
- Check if NESCO website is accessible
- Look for error messages in logs

### Bot Commands Not Working

**Solution:**
- Send `/start` first to initialize
- Check if user is registered in database
- Verify all dependencies are installed

## Daily Reminders Setup

To enable automatic daily reminders at 11 AM:

### Option 1: Heroku Scheduler (Free)

```bash
heroku addons:create scheduler:standard
heroku addons:open scheduler
```

Add this job:
- **Command:** `curl https://your-app.herokuapp.com/api/daily-reminder`
- **Frequency:** Daily at 11:00 AM
- **Timezone:** Your timezone

### Option 2: External Cron Service

Use [cron-job.org](https://cron-job.org):
1. Create free account
2. Add new cron job
3. URL: `https://your-app.herokuapp.com/api/daily-reminder`
4. Schedule: `0 11 * * *` (11 AM daily)

## Security Best Practices

1. **Never commit `.env` file** - Already in `.gitignore`
2. **Keep bot token private** - Don't share or commit
3. **Use HTTPS in production** - Heroku provides this automatically
4. **Secure database** - Use strong passwords, enable SSL
5. **Monitor logs** - Watch for suspicious activity

## Need Help?

- Check the logs: `heroku logs --tail`
- Test API endpoints manually with curl
- Verify environment variables: `heroku config`
- Check database status: `heroku pg:info`

## Next Steps

After setup:
1. Test all bot commands
2. Set up daily reminders
3. Monitor for a few days
4. Add more users
5. Consider adding webhooks for instant updates

---

**You're all set!** Your Telegram bot is now connected to the backend. 🎉
