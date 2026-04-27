import time
from datetime import datetime

print("=" * 40)
print("  test_ping.py - STARTED")
print("=" * 40)

count = 1
while True:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] Ping #{count} ... OK")
    count += 1
    time.sleep(3)
