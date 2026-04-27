import time
from datetime import datetime

print("=" * 40)
print("  test_crash.py - STARTED")
print("  (will stop after 20 seconds)")
print("=" * 40)

count = 1
while True:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] Working... step #{count}")
    count += 1
    time.sleep(4)

    if count > 5:
        print()
        print("[ERROR] Something went wrong! Process stopping...")
        print("[ERROR] ConnectionRefusedError: target unreachable")
        break

print("=" * 40)
print("  test_crash.py - STOPPED")
print("=" * 40)
