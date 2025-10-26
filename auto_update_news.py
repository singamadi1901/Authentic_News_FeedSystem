import os
import sys
import django
import time
import schedule
from datetime import datetime

# Add your project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'news_project.settings')  # CORRECT NAME

django.setup()

from django.core.management import call_command

def update_news():
    try:
        print(f"[{datetime.now()}] Starting news update...")
        call_command('fetch_and_verify_news')
        print(f"[{datetime.now()}] News update completed successfully!")
    except Exception as e:
        print(f"[{datetime.now()}] Error updating news: {e}")

def main():
    print("News Auto-Updater Started!")
    print("Will update news every 2 hours...")
    
    # Schedule the job
    schedule.every(2).hours.do(update_news)
    
    # Run once immediately
    update_news()
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()
