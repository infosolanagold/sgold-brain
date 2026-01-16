from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime

app = Flask(__name__)
# Autorise les requêtes de partout (Wix inclus)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- DETECTION INTELLIGENTE DU DISQUE (EVITE LES CRASHS) ---
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
    print("✅ DISQUE PERSISTANT DÉTECTÉ.")
else:
    BASE_PATH = "."
    print("⚠️ PAS DE DISQUE DÉTECTÉ. MODE MÉMOIRE TEMPORAIRE.")

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")

# --- GESTION DES FICHIERS ---
def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4) 
    except Exception as e:
        print(f"❌ ERREUR SAUVEGARDE {filepath}: {e}")

# Charge la mémoire au démarrage
global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE 🟢",
        "storage": BASE_PATH,
        "reports": len(global_reports),
        "referrals": len(global_referrals)
    }), 200

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0}), 400

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
        return jsonify({"risk": "ERROR", "score": 0}), 500

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        global_reports.insert(0, data)
        save_json(DB_FILE, global_reports) 
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
        updated = False
        
        if action == 'delete':
            global_reports = [r for r in global_reports if r['id'] != report_id]
            updated = True
        elif action == 'approve':
            for r in global_reports:
                if r['id'] == report_id: 
                    r['status'] = 'approved'
                    updated = True
        
        if updated: save_json(DB_FILE, global_reports) 
        return jsonify({"status": "updated"})
    except: return jsonify({"error": "Failed"}), 500

# --- ROUTES REFERRAL ---

# 1. Enregistrer un parrainage (Appelé par le site quand quelqu'un arrive)
@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
        data['server_time'] = datetime.now().isoformat()
        
        global_referrals.append(data)
        save_json(REF_FILE, global_referrals)
        
        return jsonify({"status": "tracked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. Lister les parrainages (NOUVEAU - Pour l'onglet Admin)
@app.route('/referral/list', methods=['GET'])
def get_referral_list():
    return jsonify(global_referrals), 200

if __name__ == '__main__':
    # Utilise le port défini par Render ou 10000 par défaut
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
