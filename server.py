import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

APPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps.json")

# { app_id: Popen }
processes = {}
# { app_id: deque of log lines }
logs = {}
# { app_id: "running" | "success" | "error" | "offline" }
states = {}
# { app_id: True } — marks apps whose watcher should stop (user clicked Stop)
stop_flags = {}

lock = threading.Lock()
MAX_LOG_LINES = 500

re_error = re.compile(
    r'\berror\b(?!\s*=\s*0)|exception|traceback|fatal|\bfailed\b|exit code [^0]',
    re.IGNORECASE
)


def load_apps():
    if os.path.exists(APPS_FILE):
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_apps(apps):
    with open(APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2, ensure_ascii=False)


def get_display_name(path):
    basename = os.path.basename(path)
    name, _ = os.path.splitext(basename)
    return name


def is_process_running_by_pid(app_id):
    """Check if the process we launched is still alive."""
    with lock:
        proc = processes.get(str(app_id))
        if proc is None:
            return False
        return proc.poll() is None


def detect_external_process(path):
    """
    Check if an external process matching the given path is already running
    on the OS (i.e. the user opened it manually outside this monitor).
    Returns True if found running externally, False otherwise.
    Works on Windows (tasklist/wmic) and Linux/Mac (ps).
    """
    try:
        basename = os.path.basename(path).lower()
        if sys.platform == "win32":
            result = subprocess.run(
                ["wmic", "process", "get", "ProcessId,ExecutablePath,CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.lower()
            norm_path = os.path.normpath(path).lower()
            if norm_path in output or basename in output:
                return True
            ext = os.path.splitext(basename)[1]
            if ext == ".exe":
                result2 = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {basename}", "/NH"],
                    capture_output=True, text=True, timeout=5
                )
                if basename in result2.stdout.lower():
                    return True
        else:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            norm_path = path.lower()
            if norm_path in result.stdout.lower() or basename in result.stdout.lower():
                return True
    except Exception:
        pass
    return False


def detect_external_process_name(process_name):
    """
    Check if a process with the given executable name is running.
    e.g. detect_external_process_name("EXCEL.EXE")
    """
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            return process_name.lower() in result.stdout.lower()
        else:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            return process_name.lower() in result.stdout.lower()
    except Exception:
        return False


def is_process_running(app_id):
    """Returns True if the process is running (either launched by us, or detected externally)."""
    app_id_str = str(app_id)
    with lock:
        proc = processes.get(app_id_str)
        if proc is not None:
            if proc.poll() is None:
                return True
            else:
                del processes[app_id_str]

    # Also consider "running" if the watcher is still actively monitoring Excel
    with lock:
        state = states.get(app_id_str)
    if state == "running":
        return True

    apps = load_apps()
    app_entry = next((a for a in apps if str(a["id"]) == app_id_str), None)
    if app_entry:
        if detect_external_process(app_entry["path"]):
            return True
    return False


def watch_process(app_id, proc):
    """Background thread that waits for process to finish then finalizes state."""
    app_id_str = str(app_id)
    proc.wait()
    time.sleep(0.3)

    exit_code = proc.returncode

    # --- Excel / GUI launcher handling ---
    # If the launcher .exe exited cleanly (exit code 0), it may have just
    # opened Excel and returned immediately. Switch to polling Excel.EXE
    # so the light stays green while Excel is open and turns red when it closes.
    apps = load_apps()
    app_entry = next((a for a in apps if str(a["id"]) == app_id_str), None)

    if exit_code == 0 and app_entry:
        ext = os.path.splitext(app_entry["path"])[1].lower()
        if ext == ".exe":
            # Give Excel a moment to fully open
            time.sleep(2)

            # Poll until Excel is gone or user manually stopped the app
            while True:
                # Check if user clicked Stop — bail out cleanly
                with lock:
                    stopped = stop_flags.get(app_id_str, False)
                if stopped:
                    with lock:
                        stop_flags.pop(app_id_str, None)
                    break

                if detect_external_process_name("EXCEL.EXE"):
                    with lock:
                        states[app_id_str] = "running"
                    time.sleep(3)
                else:
                    # Excel has closed or crashed
                    with lock:
                        current_state = states.get(app_id_str)
                    if current_state == "running":
                        with lock:
                            states[app_id_str] = "error"
                    break

            with lock:
                processes.pop(app_id_str, None)
            return

    # --- Original logic for .py / scripts / non-zero exit ---
    state = "success"
    if exit_code != 0:
        state = "error"
    else:
        with lock:
            lines = list(logs.get(app_id_str, []))
        alltext = "\n".join(lines)
        if re_error.search(alltext):
            state = "error"

    with lock:
        states[app_id_str] = state
        if processes.get(app_id_str) is proc:
            del processes[app_id_str]


def read_output(app_id, proc):
    app_id_str = str(app_id)

    def read_stream(stream, prefix=""):
        try:
            for line in iter(stream.readline, b''):
                text = line.decode("utf-8", errors="replace").rstrip()
                if prefix:
                    text = prefix + text
                with lock:
                    if app_id_str in logs:
                        logs[app_id_str].append(text)
        except Exception:
            pass

    t_out = threading.Thread(target=read_stream, args=(proc.stdout,), daemon=True)
    t_err = threading.Thread(target=read_stream, args=(proc.stderr, "[ERR] "), daemon=True)
    t_out.start()
    t_err.start()

    t_watch = threading.Thread(target=watch_process, args=(app_id, proc), daemon=True)
    t_watch.start()


def start_process(app_entry):
    app_id = str(app_entry["id"])
    path = app_entry["path"]
    ext = os.path.splitext(path)[1].lower()

    with lock:
        if app_id in processes:
            try:
                processes[app_id].terminate()
            except Exception:
                pass
            del processes[app_id]
        logs[app_id] = deque(maxlen=MAX_LOG_LINES)
        states[app_id] = "running"
        stop_flags.pop(app_id, None)  # clear any leftover stop flag

    if ext == ".py":
        cmd = ["python", "-u", path]
    elif ext in (".bat", ".cmd"):
        cmd = ["cmd", "/c", path]
    elif ext == ".vbs":
        cmd = ["cscript", "//Nologo", path]
    elif ext == ".ps1":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", path]
    elif ext in (".sh",):
        cmd = ["bash", path]
    elif ext in (".js", ".mjs"):
        cmd = ["node", path]
    elif ext == ".rb":
        cmd = ["ruby", path]
    elif ext == ".lua":
        cmd = ["lua", path]
    elif ext == ".ahk":
        cmd = ["AutoHotkey", path]
    elif ext == ".jar":
        cmd = ["java", "-jar", path]
    else:
        cmd = [path]

    try:
        kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(path)),
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(cmd, **kwargs)
        with lock:
            processes[app_id] = proc

        read_output(app_id, proc)
        return True
    except Exception as e:
        with lock:
            states[app_id] = "error"
        print(f"Error starting process: {e}")
        return False


def stop_process(app_id):
    app_id_str = str(app_id)

    # Signal the Excel watcher thread to stop cleanly
    with lock:
        stop_flags[app_id_str] = True

    with lock:
        proc = processes.get(app_id_str)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            del processes[app_id_str]
            states[app_id_str] = "offline"

    # Kill Excel if it was opened by this app
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "EXCEL.EXE"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

    with lock:
        states[app_id_str] = "offline"

    return True


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/apps", methods=["GET"])
def list_apps():
    apps = load_apps()
    result = []
    for a in apps:
        app_id_str = str(a["id"])
        running = is_process_running(a["id"])
        with lock:
            state = states.get(app_id_str, None)
        if running:
            state = "running"
        elif state is None:
            state = "offline"
        result.append({
            "id": a["id"],
            "name": a.get("name", get_display_name(a["path"])),
            "path": a["path"],
            "running": running,
            "state": state,
        })
    return jsonify(result)


@app.route("/apps/status", methods=["GET"])
def status():
    apps = load_apps()
    result = []
    for a in apps:
        app_id_str = str(a["id"])
        running = is_process_running(a["id"])
        with lock:
            state = states.get(app_id_str, None)
        if running:
            state = "running"
        elif state is None:
            state = "offline"
        result.append({"id": a["id"], "running": running, "state": state})
    return jsonify(result)


@app.route("/apps/add", methods=["POST"])
def add_app():
    data = request.get_json()
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "No path provided"}), 400

    path = os.path.normpath(path)
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Code", path)
    apps = load_apps()

    for a in apps:
        if os.path.normpath(a["path"]) == path:
            return jsonify({"error": "App already registered"}), 409

    new_id = int(time.time() * 1000)
    new_app = {"id": new_id, "name": get_display_name(path), "path": path}
    apps.append(new_app)
    save_apps(apps)
    return jsonify({"success": True, "app": new_app})


@app.route("/apps/start/<int:app_id>", methods=["POST"])
def start_app(app_id):
    apps = load_apps()
    app_entry = next((a for a in apps if a["id"] == app_id), None)
    if not app_entry:
        return jsonify({"error": "App not found"}), 404
    success = start_process(app_entry)
    return jsonify({"success": success, "running": success})


@app.route("/apps/stop/<int:app_id>", methods=["POST"])
def stop_app(app_id):
    stop_process(app_id)
    return jsonify({"success": True, "running": False})


@app.route("/apps/restart/<int:app_id>", methods=["POST"])
def restart_app(app_id):
    stop_process(app_id)
    time.sleep(0.5)
    apps = load_apps()
    app_entry = next((a for a in apps if a["id"] == app_id), None)
    if not app_entry:
        return jsonify({"error": "App not found"}), 404
    success = start_process(app_entry)
    return jsonify({"success": success, "running": success})


@app.route("/apps/remove/<int:app_id>", methods=["DELETE"])
def remove_app(app_id):
    stop_process(app_id)
    apps = load_apps()
    apps = [a for a in apps if a["id"] != app_id]
    save_apps(apps)
    with lock:
        states.pop(str(app_id), None)
        logs.pop(str(app_id), None)
    return jsonify({"success": True})


@app.route("/apps/rename/<int:app_id>", methods=["POST"])
def rename_app(app_id):
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "No name provided"}), 400
    apps = load_apps()
    for a in apps:
        if a["id"] == app_id:
            a["name"] = name
            break
    save_apps(apps)
    return jsonify({"success": True})


@app.route("/apps/logs/<int:app_id>", methods=["GET"])
def get_logs(app_id):
    app_id_str = str(app_id)
    with lock:
        lines = list(logs.get(app_id_str, []))
        state = states.get(app_id_str, "offline")
    running = is_process_running(app_id)
    if running:
        state = "running"
    return jsonify({"lines": lines, "running": running, "state": state})


@app.route("/apps/detect/<int:app_id>", methods=["GET"])
def detect_app(app_id):
    """
    Check if an app is externally detected as running on the OS.
    Used by the frontend to auto-detect manually opened apps.
    """
    apps = load_apps()
    app_entry = next((a for a in apps if a["id"] == app_id), None)
    if not app_entry:
        return jsonify({"detected": False}), 404

    owned = is_process_running_by_pid(app_id)
    external = False
    if not owned:
        external = detect_external_process(app_entry["path"])

    return jsonify({
        "detected": owned or external,
        "owned": owned,
        "external": external
    })


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("=" * 50)
    print("  APPs 监控 Backend Server")
    print("  Running on http://localhost:5000")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)