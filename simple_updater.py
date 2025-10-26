import os
import subprocess
import time
from datetime import datetime

def update_news():
    print(f"[{datetime.now()}] Updating news...")
    try:
        # Run the Django management command
        result = subprocess.run(['python', 'manage.py', 'fetch_and_verify_news'], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[{datetime.now()}] ✅ News updated successfully!")
        else:
            print(f"[{datetime.now()}] ❌ Error: {result.stderr}")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Exception: {e}")

def main():
    print("🚀 Simple News Updater Started!")
    
    # Update immediately
    update_news()
    
    # Then update every 2 hours (7200 seconds)
    while True:
        time.sleep(7200)  # 2 hours
        update_news()

if __name__ == "__main__":
    main()
