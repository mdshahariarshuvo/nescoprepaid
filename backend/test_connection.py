#!/usr/bin/env python3
"""
Test script to verify the connection between Telegram bot and backend.
This script checks if all components are configured correctly.
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_status(check_name, status, message=""):
    """Print colored status messages"""
    colors = {
        'pass': '\033[92m',  # Green
        'fail': '\033[91m',  # Red
        'warn': '\033[93m',  # Yellow
        'info': '\033[94m',  # Blue
        'reset': '\033[0m'
    }
    
    symbol = "✓" if status == 'pass' else "✗" if status == 'fail' else "⚠" if status == 'warn' else "ℹ"
    color = colors.get(status, colors['reset'])
    print(f"{color}{symbol} {check_name}{colors['reset']}")
    if message:
        print(f"  {message}")

def check_environment_variables():
    """Check if required environment variables are set"""
    print("\n=== Checking Environment Variables ===")
    
    checks = {
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
        'BACKEND_URL': os.getenv('BACKEND_URL'),
        'DATABASE_URL': os.getenv('DATABASE_URL'),
    }
    
    all_good = True
    for var, value in checks.items():
        if value:
            # Mask sensitive values
            if 'TOKEN' in var:
                display_value = value[:10] + '...' + value[-5:]
            elif 'DATABASE_URL' in var:
                display_value = value.split('@')[-1] if '@' in value else value[:20] + '...'
            else:
                display_value = value
            print_status(f"{var}", 'pass', f"Set to: {display_value}")
        else:
            print_status(f"{var}", 'fail', "Not set!")
            all_good = False
    
    return all_good

def check_backend_health():
    """Check if backend is accessible and healthy"""
    print("\n=== Checking Backend Health ===")
    
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:5000')
    
    try:
        response = requests.get(f"{backend_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print_status("Backend Health", 'pass', f"Status: {data.get('status')}")
            print_status("Backend URL", 'pass', backend_url)
            return True
        else:
            print_status("Backend Health", 'fail', f"HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_status("Backend Health", 'fail', "Cannot connect to backend")
        print_status("Info", 'warn', "Make sure backend is running: python app.py")
        return False
    except Exception as e:
        print_status("Backend Health", 'fail', str(e))
        return False

def check_telegram_bot_token():
    """Verify Telegram bot token is valid"""
    print("\n=== Checking Telegram Bot Token ===")
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print_status("Bot Token", 'fail', "TELEGRAM_BOT_TOKEN not set")
        return False
    
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                print_status("Bot Token", 'pass', f"Valid token")
                print_status("Bot Name", 'pass', f"@{bot_info.get('username')}")
                print_status("Bot ID", 'info', f"{bot_info.get('id')}")
                return True
            else:
                print_status("Bot Token", 'fail', "Invalid response from Telegram")
                return False
        else:
            print_status("Bot Token", 'fail', f"HTTP {response.status_code} - Invalid token")
            print_status("Info", 'warn', "Get a new token from @BotFather on Telegram")
            return False
    except Exception as e:
        print_status("Bot Token", 'fail', str(e))
        return False

def check_dependencies():
    """Check if required Python packages are installed"""
    print("\n=== Checking Python Dependencies ===")
    
    required_packages = [
        'flask',
        'flask_sqlalchemy',
        'requests',
        'beautifulsoup4',
        'telegram',
        'psycopg2',
    ]
    
    all_installed = True
    for package in required_packages:
        try:
            __import__(package)
            print_status(package, 'pass', "Installed")
        except ImportError:
            print_status(package, 'fail', "Not installed")
            all_installed = False
    
    if not all_installed:
        print_status("Fix", 'warn', "Run: pip install -r requirements.txt")
    
    return all_installed

def check_database_connection():
    """Check if database is accessible"""
    print("\n=== Checking Database Connection ===")
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print_status("Database URL", 'fail', "DATABASE_URL not set")
        return False
    
    try:
        from app import app, db
        with app.app_context():
            # Try to query the database
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            print_status("Database Connection", 'pass', "Connected successfully")
            
            # Check if tables exist
            from app import User, Meter, BalanceHistory
            if db.inspect(db.engine).has_table('users'):
                print_status("Database Tables", 'pass', "Tables initialized")
            else:
                print_status("Database Tables", 'warn', "Tables not initialized")
                print_status("Fix", 'info', 'Run: python -c "from app import app, db; app.app_context().push(); db.create_all()"')
            
            return True
    except Exception as e:
        print_status("Database Connection", 'fail', str(e))
        print_status("Info", 'warn', "Check DATABASE_URL and ensure PostgreSQL is running")
        return False

def print_summary(results):
    """Print summary of all checks"""
    print("\n" + "="*50)
    print("=== SUMMARY ===")
    print("="*50)
    
    passed = sum(results.values())
    total = len(results)
    
    for check, result in results.items():
        status = 'pass' if result else 'fail'
        print_status(check, status)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print_status("Overall Status", 'pass', "All checks passed! You're ready to run the bot.")
        print("\nNext steps:")
        print("1. Start backend:  python app.py")
        print("2. Start bot:      python bot.py")
        print("3. Open Telegram and send /start to your bot")
    else:
        print_status("Overall Status", 'fail', "Some checks failed. Please fix the issues above.")
        print("\nRefer to SETUP.md for detailed instructions.")

def main():
    """Run all checks"""
    print("="*50)
    print("NESCO Telegram Bot - Connection Test")
    print("="*50)
    
    results = {
        'Environment Variables': check_environment_variables(),
        'Python Dependencies': check_dependencies(),
        'Backend Health': check_backend_health(),
        'Telegram Bot Token': check_telegram_bot_token(),
        'Database Connection': check_database_connection(),
    }
    
    print_summary(results)
    
    # Exit with appropriate code
    sys.exit(0 if all(results.values()) else 1)

if __name__ == '__main__':
    main()
