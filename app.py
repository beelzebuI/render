import os
import requests
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder='static')

RENDER_API_KEYS = os.environ.get('RENDER_API_KEYS', '').split(',')

# =========================
# LIVE POINTS STORAGE
# =========================
POINTS_CACHE = {}


# =========================
# FRONTEND
# =========================
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


# =========================
# RECEIVE DATA FROM MINER
# =========================
@app.route('/api/update', methods=['POST'])
def update_points():
    data = request.json

    if not data:
        return jsonify({"error": "no data"}), 400

    account = data.get("account")
    channels = data.get("channels", {})
    updated = data.get("updated")

    if not account:
        return jsonify({"error": "no account"}), 400

    POINTS_CACHE[account] = {
        "channels": channels,
        "updated": updated
    }

    return jsonify({"ok": True})


# =========================
# FRONTEND API (LIVE DATA)
# =========================
@app.route('/api/points')
def points():
    return jsonify(POINTS_CACHE)


# =========================
# OPTIONAL: KEEP YOUR RENDER SERVICES LIST (NOT REQUIRED ANYMORE)
# =========================
@app.route('/api/services')
def get_services():
    all_services = []
    for key in RENDER_API_KEYS:
        key = key.strip()
        if not key:
            continue

        try:
            r = requests.get(
                'https://api.render.com/v1/services',
                headers={
                    'Authorization': f'Bearer {key}',
                    'Accept': 'application/json'
                }
            )
            data = r.json()
        except Exception as e:
            print(f'Error fetching services: {e}')
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            svc = item.get('service') or item
            if svc.get('id') and svc.get('name'):
                all_services.append({
                    'id': svc['id'],
                    'name': svc['name'],
                    'ownerId': svc.get('ownerId')
                })

    return jsonify(all_services)


# =========================
# REMOVE LOG SYSTEM (NOT USED ANYMORE)
# =========================
@app.route('/api/logs/<service_id>')
def get_logs(service_id):
    return jsonify([])


# =========================
# START SERVER
# =========================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
