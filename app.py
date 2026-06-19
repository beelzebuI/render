import os
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder='static')

RENDER_API_KEYS = os.environ.get('RENDER_API_KEYS', '').split(',')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/services')
def get_services():
    all_services = []
    for key in RENDER_API_KEYS:
        key = key.strip()
        if not key:
            continue
        cursor = None
        while True:
            params = {'limit': 100}
            if cursor:
                params['cursor'] = cursor
            try:
                r = requests.get('https://api.render.com/v1/services', headers={
                    'Authorization': f'Bearer {key}',
                    'Accept': 'application/json'
                }, params=params)
                data = r.json()
            except Exception as e:
                print(f'Error fetching services: {e}')
                break
            if not isinstance(data, list) or not data:
                break
            for item in data:
                svc = item.get('service') or item
                if svc.get('id') and svc.get('name'):
                    # ownerId is required so the logs endpoint knows which
                    # workspace to query - the old code dropped this.
                    all_services.append({
                        'id': svc['id'],
                        'name': svc['name'],
                        'ownerId': svc.get('ownerId')
                    })
            cursor = item.get('cursor')
            if not cursor or len(data) < 100:
                break
    return jsonify(all_services)

@app.route('/api/logs/<service_id>')
def get_logs(service_id):
    # The Render API has no /services/{id}/logs route - that was the bug.
    # Logs are queried from a single global endpoint, filtered by
    # ownerId (workspace) + resource (service id).
    owner_id = request.args.get('ownerId')
    if not owner_id:
        return jsonify([])

    # The points-miner only logs a streamer's line when its state changes
    # (e.g. going online/offline), so a quiet/offline streamer's last known
    # points can sit well outside a 1-page, 24-hour window. Render's free
    # plan keeps 7 days of logs, so search that whole range, paging back
    # through it as needed (capped to stay well under the API's 30/min
    # rate limit for GET /v1/logs).
    MAX_PAGES = 5
    window_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    window_end = datetime.now(timezone.utc).isoformat()

    for key in RENDER_API_KEYS:
        key = key.strip()
        if not key:
            continue

        all_logs = []
        cur_start, cur_end = window_start, window_end
        matched_key = False

        for _ in range(MAX_PAGES):
            try:
                r = requests.get('https://api.render.com/v1/logs', headers={
                    'Authorization': f'Bearer {key}',
                    'Accept': 'application/json'
                }, params={
                    'ownerId': owner_id,
                    'resource': [service_id],
                    'type': ['app'],
                    'direction': 'backward',  # most recent logs first
                    'startTime': cur_start,
                    'endTime': cur_end,
                    'limit': 100,
                })
            except Exception as e:
                print(f'Error fetching logs: {e}')
                break

            if r.status_code != 200:
                if r.status_code not in (401, 403, 404):
                    print(f'Logs request for {service_id} failed ({r.status_code}): {r.text[:300]}')
                break

            matched_key = True
            data = r.json()
            all_logs.extend(data.get('logs', []))

            if not data.get('hasMore'):
                break
            cur_start = data.get('nextStartTime') or cur_start
            cur_end = data.get('nextEndTime') or cur_end

        if matched_key:
            all_logs.reverse()  # oldest-first so the most recent line is last
            return jsonify(all_logs)

    return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
