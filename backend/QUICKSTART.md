# Quick Reference Card

## 🚀 First Time Setup

```bash
# 1. Create Telegram bot with @BotFather
# 2. Copy .env.example to .env and fill in values
cd backend
cp .env.example .env
nano .env  # or use your favorite editor

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 5. Test configuration
python test_connection.py

# 6. Run the app
python app.py        # Terminal 1
python bot.py        # Terminal 2
```

## 🔄 Daily Usage

```bash
# Start backend
cd backend
python app.py

# Start bot (in another terminal)
cd backend
python bot.py

# Test connection
python test_connection.py

# Check logs (Heroku)
heroku logs --tail
```

## 🛠️ Common Commands

### Local Development
```bash
# Install/update dependencies
pip install -r requirements.txt

# Reset database
python -c "from app import app, db; app.app_context().push(); db.drop_all(); db.create_all()"

# Run with debug mode
FLASK_ENV=development python app.py
```

### Heroku Deployment
```bash
# Initial deployment
heroku create your-app-name
heroku addons:create heroku-postgresql:essential-0
git push heroku main

# Set environment variables
heroku config:set TELEGRAM_BOT_TOKEN=your_token

# Initialize database
heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Scale dynos
heroku ps:scale web=1 worker=1

# View logs
heroku logs --tail

# Restart app
heroku restart

# Open app
heroku open
```

### Database Commands
```bash
# Local PostgreSQL
createdb nesco_bot                    # Create database
dropdb nesco_bot                      # Delete database
psql nesco_bot                        # Connect to database

# Heroku PostgreSQL
heroku pg:info                        # Database info
heroku pg:psql                        # Connect to database
heroku pg:reset DATABASE_URL          # Reset database (careful!)
```

### Git Commands
```bash
# Check status
git status

# Commit changes
git add .
git commit -m "Your message"

# Push to Heroku
git push heroku main

# Push to GitHub
git push origin main
```

## 🧪 Testing

```bash
# Test backend health
curl http://localhost:5000/health

# Test scraping endpoint
curl -X POST http://localhost:5000/api/scrape-nesco \
  -H "Content-Type: application/json" \
  -d '{"meter_number": "31041051783"}'

# Run connection tests
python test_connection.py
```

## 📝 Bot Commands (in Telegram)

- `/start` - Start the bot
- `/add` - Add a new meter
- `/list` - List all your meters
- `/check` - Check all balances
- `/remove` - Remove a meter
- `/minbalance` - Set minimum balance alert
- `/reminder` - Toggle daily reminder
- `/help` - Show help message

## 💬 Messenger Quick Actions (Optional)

1. Deploy the backend so `https://your-domain/webhook/messenger` is reachable.
2. Set `MESSENGER_PAGE_ACCESS_TOKEN` and `MESSENGER_VERIFY_TOKEN` in your environment.
3. In the Meta App dashboard, subscribe the webhook (events: `messages`, `messaging_postbacks`).
4. Click "Get Started" in Messenger to see quick replies for **Add**, **List**, **Check**, and **Report** actions.

## 🐛 Troubleshooting Quick Fixes

```bash
# Bot not responding?
1. Check TELEGRAM_BOT_TOKEN is set correctly
2. Verify backend is running: curl http://localhost:5000/health
3. Check bot logs for errors

# Backend connection error?
1. Verify BACKEND_URL in bot environment
2. Check if backend is accessible
3. Look for firewall/network issues

# Database error?
1. Check DATABASE_URL is set
2. Verify PostgreSQL is running
3. Initialize tables: python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Dependencies error?
pip install -r requirements.txt --upgrade
```

## 📚 Documentation

- **Full Setup Guide**: [SETUP.md](SETUP.md)
- **Backend API**: [README.md](README.md)
- **Main README**: [../README.md](../README.md)

## 🔗 Useful Links

- Telegram Bot API: https://core.telegram.org/bots/api
- Heroku Python: https://devcenter.heroku.com/articles/getting-started-with-python
- Flask Documentation: https://flask.palletsprojects.com/
- python-telegram-bot: https://docs.python-telegram-bot.org/

---

**Need more help?** Run `python test_connection.py` to diagnose issues!
