from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DB_FILE = "/var/data/database.json"

# --- GESTION PERSISTANCE (Fichier JSON) ---
def load_db():
    if not os.path.exists(DB_FILE): return []
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return []

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f: json.dump(data, f)
    except Exception as e: print(f"Save error: {e}")

# Charge la mémoire au démarrage
global_reports = load_db()

@app.route('/', methods=['GET'])
def home():
    return f"SERVER ONLINE. {len(global_reports)} stored reports."

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        headers = {"User-Agent": "Mozilla/5.0"}
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, headers=headers, timeout=5)

        if response.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new."})

        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        risks = rc_data.get('risks', [])
        summary = "Clean Analysis." if not risks else f"ALERT: {risks[0].get('name')}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})
    except:
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Scan failed."}), 500

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        
        global_reports.insert(0, data)
        save_db(global_reports) # Sauvegarde immédiate
        
        return jsonify({"status": "success", "id": data['id']})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/report/list', methods=['GET'])
def get_reports():
    return jsonify(global_reports)

@app.route('/report/action', methods=['POST'])
def action_report():
    try:
        req = request.json
        action = req.get('action')
        report_id = req.get('id')
        global global_reports
        
        if action == 'delete':
            global_reports = [r for r in global_reports if r['id'] != report_id]
        elif action == 'approve':
            for r in global_reports:
                if r['id'] == report_id: r['status'] = 'approved'
        
        save_db(global_reports) # Sauvegarde après modif
        return jsonify({"status": "updated"})
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
