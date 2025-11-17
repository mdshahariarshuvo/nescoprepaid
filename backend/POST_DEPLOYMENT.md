# Post-Deployment Checklist for Heroku

After deploying your NESCO bot to Heroku, follow these steps to get everything running:

## ✅ Step 1: Set Environment Variables

Your app needs these environment variables. Set them in Heroku:

```bash
# Required: Your Telegram Bot Token (get from @BotFather)
heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional: Backend URL (usually auto-detected, but you can set it)
heroku config:set BACKEND_URL=https://your-app-name.herokuapp.com

# Optional: Admin credentials for admin dashboard
heroku config:set ADMIN_USERNAME=shuvo
heroku config:set ADMIN_PASSWORD=your_secure_password

# Optional: Timezone (defaults to Asia/Dhaka)
heroku config:set TIMEZONE=Asia/Dhaka

# Optional: Daily reminder time (defaults to 20:00)
heroku config:set DAILY_REMINDER_TIME=20:00

# Optional: Enable/disable internal scheduler (defaults to true)
heroku config:set ENABLE_INTERNAL_SCHEDULER=true
```

**Note:** `DATABASE_URL` is automatically set by Heroku when you add the PostgreSQL addon.

## ✅ Step 2: Initialize the Database

Create the database tables:

```bash
heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

## ✅ Step 3: Scale Your Dynos

Make sure both web and worker dynos are running:

```bash
# Check current dyno status
heroku ps

# Scale up both dynos (if not already running)
heroku ps:scale web=1 worker=1
```

The `web` dyno runs your Flask API, and the `worker` dyno runs your Telegram bot.

## ✅ Step 4: Verify Deployment

### Check Logs

```bash
# View real-time logs
heroku logs --tail

# View logs for specific dyno
heroku logs --tail --dyno web
heroku logs --tail --dyno worker
```

### Test Health Endpoint

```bash
# Test if your API is running
curl https://your-app-name.herokuapp.com/health
```

You should see: `{"status":"healthy","timestamp":"..."}`

### Test Telegram Bot

1. Open Telegram and search for your bot
2. Send `/start` command
3. You should receive a welcome message

## ✅ Step 5: Set Up Telegram Webhook (Optional)

If you want to use webhooks instead of polling, set the webhook:

```bash
# Get your webhook URL
WEBHOOK_URL=https://your-app-name.herokuapp.com/webhook/telegram

# Set webhook via Telegram API (replace YOUR_BOT_TOKEN)
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=$WEBHOOK_URL"
```

**Note:** Your current setup uses polling (bot.py), so webhooks are optional.

## ✅ Step 6: Monitor Your App

### View App Info

```bash
# Open your app in browser
heroku open

# View app info
heroku info
```

### Check Database

```bash
# Connect to PostgreSQL
heroku pg:psql

# In psql, you can run queries:
# SELECT * FROM users;
# SELECT * FROM meters;
# \q to exit
```

## 🔧 Troubleshooting

### Bot Not Responding?

1. **Check worker dyno is running:**
   ```bash
   heroku ps
   ```
   If worker is not running, scale it up:
   ```bash
   heroku ps:scale worker=1
   ```

2. **Check logs for errors:**
   ```bash
   heroku logs --tail --dyno worker
   ```

3. **Verify bot token is set:**
   ```bash
   heroku config:get TELEGRAM_BOT_TOKEN
   ```

### API Not Working?

1. **Check web dyno is running:**
   ```bash
   heroku ps
   heroku ps:scale web=1
   ```

2. **Check logs:**
   ```bash
   heroku logs --tail --dyno web
   ```

3. **Test health endpoint:**
   ```bash
   curl https://your-app-name.herokuapp.com/health
   ```

### Database Issues?

1. **Check PostgreSQL addon:**
   ```bash
   heroku addons
   ```

2. **Verify DATABASE_URL:**
   ```bash
   heroku config:get DATABASE_URL
   ```

3. **Reinitialize database (WARNING: This deletes all data):**
   ```bash
   heroku pg:reset DATABASE_URL
   heroku run python -c "from app import app, db; app.app_context().push(); db.create_all()"
   ```

## 📊 Quick Commands Reference

```bash
# View all config variables
heroku config

# Set a config variable
heroku config:set KEY=value

# Get a config variable
heroku config:get KEY

# Restart all dynos
heroku restart

# Restart specific dyno
heroku restart web
heroku restart worker

# Run a one-off command
heroku run python bot.py

# View recent logs
heroku logs --tail -n 100

# Scale dynos
heroku ps:scale web=1 worker=1

# Open app
heroku open
```

## 🎉 You're Done!

Your bot should now be:
- ✅ Running on Heroku
- ✅ Connected to PostgreSQL
- ✅ Responding to Telegram commands
- ✅ Ready to monitor NESCO meters

## 📝 Next Steps

1. **Test all bot commands:**
   - `/start` - Initialize bot
   - `/add` - Add a meter
   - `/list` - List meters
   - `/check` - Check balances
   - `/report` - View usage report

2. **Set up daily reminders:**
   - The internal scheduler should automatically send daily reminders
   - Or use an external cron service like cron-job.org to call `/api/daily-reminder`

3. **Monitor usage:**
   - Check Heroku dashboard for dyno hours
   - Monitor database size
   - Review logs regularly

4. **Deploy frontend (optional):**
   - Your React frontend can be deployed separately
   - Consider deploying to Vercel, Netlify, or another static hosting service
   - Update the frontend API URL to point to your Heroku backend

---

**Need help?** Check the logs first: `heroku logs --tail`

