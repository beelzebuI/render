import os
import requests
from flask import Flask, jsonify, send_from_directory

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
        try:
            r = requests.get('https://api.render.com/v1/services?limit=100', headers={
                'Authorization': f'Bearer {key}',
                'Accept': 'application/json'
            })
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    svc = item.get('service') or item
                    if svc.get('id') and svc.get('name'):
                        all_services.append({'id': svc['id'], 'name': svc['name']})
        except Exception as e:
            print(f'Error fetching services: {e}')
    return jsonify(all_services)

@app.route('/api/logs/<service_id>')
def get_logs(service_id):
    for key in RENDER_API_KEYS:
        key = key.strip()
        if not key:
            continue
        try:
            r = requests.get(f'https://api.render.com/v1/services/{service_id}/logs?limit=200', headers={
                'Authorization': f'Bearer {key}',
                'Accept': 'application/json'
            })
            if r.status_code == 200:
                return jsonify(r.json())
        except Exception as e:
            print(f'Error fetching logs: {e}')
    return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
