import os
import time
from collections import deque
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# =========================
# IN-MEMORY STORAGE
# =========================
POINTS_CACHE = {}

# History: { account -> deque of {ts, channels, streamer_status} }
# Keeps last 500 snapshots per account (~8 hours at 1/min)
HISTORY = {}
MAX_HISTORY = 500

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

    account = data.get("account")
    channels = data.get("channels", {})
    updated = data.get("updated")
    streamer_status = data.get("streamer_status", {})  # ← was missing before

    if not account:
        return jsonify({"error": "missing account"}), 400

    # update main cache
    POINTS_CACHE[account] = {
        "channels": channels,
        "streamer_status": streamer_status,
        "updated": updated
    }

    # store history snapshot
    if account not in HISTORY:
        HISTORY[account] = deque(maxlen=MAX_HISTORY)

    HISTORY[account].append({
        "ts": int(time.time() * 1000),  # ms timestamp
        "channels": dict(channels)
    })

    return jsonify({"ok": True})

# =========================
# FRONTEND READS CURRENT DATA
# =========================
@app.route("/api/points")
def points():
    return jsonify(POINTS_CACHE)

# =========================
# FRONTEND READS HISTORY
# =========================
@app.route("/api/history/<account>")
def history(account):
    if account not in HISTORY:
        return jsonify([])
    return jsonify(list(HISTORY[account]))

# =========================
# QUICK STATS SUMMARY
# =========================
@app.route("/api/stats")
def stats():
    now = int(time.time())
    total_accounts = len(POINTS_CACHE)
    silent_accounts = []
    total_points = 0
    streamer_totals = {}

    for acc, info in POINTS_CACHE.items():
        age = now - info.get("updated", 0)
        if age > 180:
            silent_accounts.append(acc)
        for ch, pts in info.get("channels", {}).items():
            total_points += pts
            streamer_totals[ch] = streamer_totals.get(ch, 0) + pts

    return jsonify({
        "total_accounts": total_accounts,
        "silent_accounts": silent_accounts,
        "silent_count": len(silent_accounts),
        "total_points": total_points,
        "streamer_totals": streamer_totals
    })

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
