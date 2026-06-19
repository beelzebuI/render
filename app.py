import os
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# =========================
# IN-MEMORY STORAGE
# =========================
POINTS_CACHE = {}

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

    if not account:
        return jsonify({"error": "missing account"}), 400

    POINTS_CACHE[account] = {
        "channels": channels,
        "updated": updated
    }

    return jsonify({"ok": True})


# =========================
# FRONTEND READS DATA HERE
# =========================
@app.route("/api/points")
def points():
    return jsonify(POINTS_CACHE)


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
