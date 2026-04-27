# APPs 监控 — Process Monitor Dashboard

A local dashboard to monitor, start, stop and restart your Python/batch scripts — with a real-time status display.

---

## 📁 Files

| File | Purpose |
|---|---|
| `server.py` | Python Flask backend (process manager + API) |
| `dashboard.html` | Browser-based dashboard UI |
| `startup.bat` | One-click launcher (opens backend + dashboard) |
| `apps.json` | Auto-created — saves your registered apps |
| `requirements.txt` | Python dependencies |

---

## 🚀 First-Time Setup

1. **Install Python 3.8+** from https://python.org (check "Add to PATH" during install)

2. **Install dependencies:**
   ```
   pip install flask flask-cors
   ```

3. **Double-click `startup.bat`** — it will:
   - Install dependencies automatically
   - Start the Flask backend on `localhost:5000`
   - Open `dashboard.html` in your browser

---

## 🔄 Auto-start on Windows Login

To have the dashboard launch automatically every time you start your laptop:

1. Press `Win + R`, type: `shell:startup`, press Enter
2. Copy a **shortcut** of `startup.bat` into that folder
3. Done — it will run silently at every login

---

## 🖥️ How to Use

### Add a script
- **Drag & drop** a `.py`, `.bat`, or `.exe` file into the drop zone
- Or **paste the full path** (e.g. `C:\scripts\ping.py`) and click Add

### Monitor
- 🟢 **Green dot** = running | ⚫ **Grey dot** = stopped or crashed
- Status auto-refreshes every **2 seconds**
- If a script crashes on its own, it turns grey automatically

### Controls
| Button | Action |
|---|---|
| Toggle (ON/OFF) | Start or stop the script |
| ↺ | Restart the script |
| ✎ | Rename the display name |
| ✕ | Remove from dashboard |
| Click the name | Opens a new CMD window running that script |

### Start/Stop All
Use the **▶ Start All** and **■ Stop All** buttons in the toolbar.

---

## ⚙️ Backend API (for reference)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/apps` | List all apps + status |
| GET | `/apps/status` | Quick status poll |
| POST | `/apps/add` | Register new app `{"path": "..."}` |
| POST | `/apps/start/:id` | Start an app |
| POST | `/apps/stop/:id` | Stop an app |
| POST | `/apps/restart/:id` | Restart an app |
| POST | `/apps/rename/:id` | Rename `{"name": "..."}` |
| POST | `/apps/open/:id` | Open new CMD window for app |
| DELETE | `/apps/remove/:id` | Remove from dashboard |

---

## ❓ Troubleshooting

**"BACKEND OFFLINE" shown in dashboard**
→ The Flask server isn't running. Double-click `startup.bat` again.

**App stays grey after clicking ON**
→ Check the script path is correct. Click the name to open a CMD window and see the error.

**Port 5000 already in use**
→ Change `port=5000` in `server.py` to another number (e.g. 5050), and update `const API = "http://localhost:5050"` in `dashboard.html`.
