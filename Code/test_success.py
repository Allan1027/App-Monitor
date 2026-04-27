import time
 
print("Starting task...")
 
for i in range(1, 21):
    time.sleep(1)
    print(f"[{i:02d}/20] Working... {i * 5}%")
 
print("Task completed successfully!")