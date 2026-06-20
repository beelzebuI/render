import os
import time
import json
import threading
from datetime import datetime, timezone
from collections import deque
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# =========================
# CONFIG
# =========================
MAX_HISTORY     = 500       # snapshots per account (~8hrs at 1/min)
SAVE_INTERVAL   = 60        # save to disk every 60 seconds
DATA_FILE       = "data.json"
DAILY_FILE      = "daily.json"

# =========================
# IN-MEMORY STORAGE
# =========================
POINTS_CACHE    = {}   # { account -> {channels, streamer_status, updated, first_seen} }
HISTORY         = {}   # { account -> [ {ts, channels} ] }
DAILY           = {}   # { "YYYY-MM-DD" -> { account -> { channel -> pts } } }
PEAK            = {}   # { account -> { channel -> int } }
STREAMER_LOG    = {}   # { streamer -> [ {ts, event:"online"|"offline"} ] }
UPTIME          = {}   # { account -> first_seen_ts }
_prev_status    = {}   # track previous streamer online state for logging

# =========================
# PERSIST TO DISK
# =========================
def save_data():
    try:
        payload = {
            "points_cache": POINTS_CACHE,
            "history": {acc: list(snaps) for acc, snaps in HISTORY.items()},
            "peak": PEAK,
            "streamer_log": STREAMER_LOG,
            "uptime": UPTIME,
        }
        with open(DATA_FILE, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        print("save error:", e)

def save_daily():
    try:
        with open(DAILY_FILE, "w") as f:
            json.dump(DAILY, f)
    except Exception as e:
        print("daily save error:", e)

def load_data():
    global POINTS_CACHE, HISTORY, PEAK, STREAMER_LOG, UPTIME
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                payload = json.load(f)
            POINTS_CACHE  = payload.get("points_cache", {})
            raw_history   = payload.get("history", {})
            HISTORY       = {acc: list(snaps) for acc, snaps in raw_history.items()}
            PEAK          = payload.get("peak", {})
            STREAMER_LOG  = payload.get("streamer_log", {})
            UPTIME        = payload.get("uptime", {})
            print(f"Loaded data for {len(POINTS_CACHE)} accounts")
        except Exception as e:
            print("load error:", e)
    if os.path.exists(DAILY_FILE):
        try:
            with open(DAILY_FILE) as f:
                data = json.load(f)
            DAILY.update(data)
        except Exception as e:
            print("daily load error:", e)

def periodic_save():
    while True:
        time.sleep(SAVE_INTERVAL)
        save_data()

# =========================
# MIDNIGHT DAILY SNAPSHOT
# =========================
def midnight_snapshot():
    """Runs in background, triggers a daily snapshot at midnight UTC."""
    while True:
        now = datetime.now(timezone.utc)
        # seconds until next midnight
        seconds_until_midnight = ((24 - now.hour - 1) * 3600
                                  + (60 - now.minute - 1) * 60
                                  + (60 - now.second))
        time.sleep(seconds_until_midnight + 1)
        take_daily_snapshot()

def take_daily_snapshot():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    DAILY[today] = {}
    for acc, info in POINTS_CACHE.items():
        DAILY[today][acc] = dict(info.get("channels", {}))
    save_daily()
    print(f"Daily snapshot taken for {today}")

# =========================
# STARTUP
# =========================
load_data()
threading.Thread(target=periodic_save, daemon=True).start()
threading.Thread(target=midnight_snapshot, daemon=True).start()

# =========================
# FRONTEND
# =========================
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# =========================
# MINER SENDS DATA HERE
# =========================
@app.route("/api/update", methods=["POST"])
def update():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    account         = data.get("account")
    channels        = data.get("channels", {})
    updated         = data.get("updated")
    streamer_status = data.get("streamer_status", {})

    if not account:
        return jsonify({"error": "missing account"}), 400

    now_ts = int(time.time())

    # --- uptime: record first seen ---
    if account not in UPTIME:
        UPTIME[account] = now_ts

    # --- update main cache ---
    POINTS_CACHE[account] = {
        "channels":        channels,
        "streamer_status": streamer_status,
        "updated":         updated,
        "first_seen":      UPTIME[account]
    }

    # --- history snapshot ---
    if account not in HISTORY:
        HISTORY[account] = []
    HISTORY[account].append({
        "ts":       int(time.time() * 1000),
        "channels": dict(channels)
    })
    if len(HISTORY[account]) > MAX_HISTORY:
        HISTORY[account] = HISTORY[account][-MAX_HISTORY:]

    # --- peak points ---
    if account not in PEAK:
        PEAK[account] = {}
    for ch, pts in channels.items():
        if pts > PEAK[account].get(ch, 0):
            PEAK[account][ch] = pts

    # --- streamer online/offline log ---
    prev = _prev_status.get(account, {})
    for streamer, is_online in streamer_status.items():
        was_online = prev.get(streamer)
        if was_online != is_online:
            if streamer not in STREAMER_LOG:
                STREAMER_LOG[streamer] = []
            STREAMER_LOG[streamer].append({
                "ts":    now_ts,
                "event": "online" if is_online else "offline"
            })
            # keep last 200 events per streamer
            if len(STREAMER_LOG[streamer]) > 200:
                STREAMER_LOG[streamer] = STREAMER_LOG[streamer][-200:]
    _prev_status[account] = dict(streamer_status)

    return jsonify({"ok": True})

# =========================
# CURRENT DATA
# =========================
@app.route("/api/points")
def points():
    return jsonify(POINTS_CACHE)

# =========================
# HISTORY FOR ONE ACCOUNT
# =========================
@app.route("/api/history/<account>")
def history(account):
    return jsonify(HISTORY.get(account, []))

# =========================
# STATS SUMMARY
# =========================
@app.route("/api/stats")
def stats():
    now = int(time.time())
    total_points    = 0
    silent_accounts = []
    streamer_totals = {}

    for acc, info in POINTS_CACHE.items():
        age = now - info.get("updated", 0)
        if age > 180:
            silent_accounts.append(acc)
        for ch, pts in info.get("channels", {}).items():
            total_points += pts
            streamer_totals[ch] = streamer_totals.get(ch, 0) + pts

    return jsonify({
        "total_accounts":  len(POINTS_CACHE),
        "silent_accounts": silent_accounts,
        "silent_count":    len(silent_accounts),
        "total_points":    total_points,
        "streamer_totals": streamer_totals
    })

# =========================
# DELTA (points gained)
# =========================
@app.route("/api/delta/<account>")
def delta(account):
    snaps = HISTORY.get(account, [])
    if not snaps:
        return jsonify({"1h": 0, "6h": 0, "24h": 0})

    now_ms = int(time.time() * 1000)

    def total_pts(snap):
        return sum(snap.get("channels", {}).values())

    def delta_for(minutes):
        cutoff = now_ms - minutes * 60 * 1000
        old = next((s for s in snaps if s["ts"] >= cutoff), None)
        if not old:
            old = snaps[0]
        current = snaps[-1]
        return total_pts(current) - total_pts(old)

    return jsonify({
        "1h":  delta_for(60),
        "6h":  delta_for(360),
        "24h": delta_for(1440)
    })

# =========================
# PEAK POINTS
# =========================
@app.route("/api/peak")
def peak():
    return jsonify(PEAK)

@app.route("/api/peak/<account>")
def peak_account(account):
    return jsonify(PEAK.get(account, {}))

# =========================
# STREAMER ONLINE LOG
# =========================
@app.route("/api/streamer-log")
def streamer_log():
    return jsonify(STREAMER_LOG)

@app.route("/api/streamer-log/<streamer>")
def streamer_log_single(streamer):
    return jsonify(STREAMER_LOG.get(streamer, []))

# =========================
# DAILY SNAPSHOTS
# =========================
@app.route("/api/daily")
def daily():
    return jsonify(DAILY)

@app.route("/api/daily/<account>")
def daily_account(account):
    result = {}
    for date, accounts in DAILY.items():
        if account in accounts:
            result[date] = accounts[account]
    return jsonify(result)

# =========================
# UPTIME
# =========================
@app.route("/api/uptime")
def uptime():
    now = int(time.time())
    result = {}
    for acc, first_seen in UPTIME.items():
        result[acc] = {
            "first_seen": first_seen,
            "uptime_seconds": now - first_seen
        }
    return jsonify(result)

# =========================
# HEALTH CHECK (Render)
# =========================
@app.route("/health")
def health():
    return "OK", 200

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
