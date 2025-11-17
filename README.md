# NESCO Prepaid Meter Monitor

A Telegram bot and web application for monitoring NESCO (Nigeria Electricity Supply Corporation) prepaid meter balances.

## 🌟 Features

- 📊 Monitor multiple meters from one place
- 🤖 Telegram bot for easy access
- 📱 Daily balance reminders
- ⚠️ Low balance alerts
- 📈 Usage history tracking
- 🌐 Web dashboard (frontend)

## 🚀 Quick Start

### For Telegram Bot Users

1. Search for your bot on Telegram (the bot owner will provide the username)
2. Send `/start` to begin
3. Use `/add` to add your meter
4. Use `/check` to view balances

### For Developers - Setting Up the Bot

**Want to run your own instance?**

👉 **[Go to Backend Setup Guide](backend/SETUP.md)**

The setup guide covers:
- Creating a Telegram bot with BotFather
- Installing dependencies
- Configuring environment variables
- Running locally or deploying to Heroku
- Troubleshooting common issues

**Quick Setup Summary:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python test_connection.py  # Verify setup
python app.py              # Start backend
python bot.py              # Start bot (in another terminal)
```

## 📁 Project Structure

```
nesco/
├── backend/              # Flask API + Telegram Bot
│   ├── app.py           # Flask backend API
│   ├── bot.py           # Telegram bot client
│   ├── requirements.txt # Python dependencies
│   ├── SETUP.md         # Detailed setup instructions
│   ├── README.md        # Backend documentation
│   ├── .env.example     # Environment template
│   └── test_connection.py # Connection test script
├── src/                  # Frontend React application
└── public/              # Static assets
```

## 🤖 Bot Commands

- `/start` - Initialize bot
- `/add` - Add a new meter
- `/list` - List all your meters  
- `/check` - Check balances
- `/report` - View current month's usage summary
- `/remove` - Remove a meter
- `/minbalance` - Set low balance alert
- `/reminder` - Toggle daily reminders
- `/help` - Show help

## 🔧 Technology Stack

**Backend:**
- Python 3.11+
- Flask (API server)
- PostgreSQL (database)
- SQLAlchemy (ORM)
- python-telegram-bot (bot framework)
- BeautifulSoup4 (web scraping)

**Frontend:**
- React + TypeScript
- Vite (build tool)
- TailwindCSS (styling)

## 📖 Documentation

- **[Backend Setup Guide](backend/SETUP.md)** - Complete setup instructions for the Telegram bot
- **[Backend API Documentation](backend/README.md)** - API endpoints and reference
- **[Test Connection Script](backend/test_connection.py)** - Verify your setup

## 🚢 Deployment

### Heroku (Recommended)

The app is configured for easy Heroku deployment:

```bash
cd backend
heroku create your-app-name
heroku addons:create heroku-postgresql:essential-0
git push heroku main
heroku ps:scale web=1 worker=1
```

See [SETUP.md](backend/SETUP.md) for detailed deployment instructions.

### Other Platforms

The backend can run on any platform that supports Python and PostgreSQL:
- DigitalOcean App Platform
- Railway
- Render
- AWS/GCP/Azure

## 🔒 Security

- Never commit `.env` files
- Keep bot tokens private
- Use HTTPS in production
- Secure your database with strong passwords
- Monitor logs for suspicious activity

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

Having issues? Check out:
1. [Setup Guide](backend/SETUP.md) - Step-by-step instructions
2. Run `python test_connection.py` - Diagnose configuration issues
3. [Troubleshooting Section](backend/SETUP.md#troubleshooting) - Common problems and solutions

## ⭐ Acknowledgments

- NESCO for providing the prepaid meter service
- Telegram for the Bot API
- The open-source community

---

**Ready to get started?** Head over to the [Backend Setup Guide](backend/SETUP.md)!