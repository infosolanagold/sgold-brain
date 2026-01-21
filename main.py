from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime

app = Flask(__name__)
# Autorise les requêtes de partout
CORS(app, resources={r"/*": {"origins": "*"}})

# --- SÉCURITÉ ADMIN ---
# Récupère le mot de passe depuis Render. 
# Si tu ne le configures pas, le mot de passe par défaut est "SOLANA_ADMIN"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
# On crée un token secret basé sur ce mot de passe
ADMIN_TOKEN = f"SECURE_SESSION_{hash(ADMIN_PASSWORD)}"

# --- CONFIGURATION FICHIERS ---
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
else:
    BASE_PATH = "."

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")

def load_json(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"Error saving {filepath}: {e}")

global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- ROUTES PUBLIQUES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ONLINE", "reports": len(global_reports)})

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0}), 400

        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=5)
        
        if res.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new."})

        rc = res.json()
        score = max(0, min(100, 100 - int(rc.get('score', 0) / 100)))
        risk = "SAFE" if score >= 80 else "WARNING" if score >= 50 else "CRITICAL"
        
        return jsonify({"score": score, "risk": risk, "summary": "Scan complete."})
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
        return jsonify({"status": "success"})
    except: return jsonify({"error": "Failed"}), 500

@app.route('/report/list', methods=['GET'])
def get_reports():
    return jsonify(global_reports)

# --- NOUVELLES ROUTES SÉCURISÉES (ADMIN) ---

# 1. LOGIN SÉCURISÉ
@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    # Le serveur vérifie le mot de passe ici (invisible pour les hackers)
    if data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    else:
        return jsonify({"success": False, "error": "Invalid Password"}), 401

# 2. ACTIONS SÉCURISÉES (Nécessite le token)
@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
    # VÉRIFICATION DU TOKEN
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403

    action = data.get('action')
    r_id = data.get('id')
    global global_reports
    
    if action == 'delete':
        global_reports = [r for r in global_reports if r['id'] != r_id]
    elif action == 'approve':
        for r in global_reports:
            if r['id'] == r_id: r['status'] = 'approved'
            
    save_json(DB_FILE, global_reports)
    return jsonify({"status": "updated"})

# 3. PAIEMENT REFERRAL SÉCURISÉ
@app.route('/referral/pay', methods=['POST'])
def pay_referral():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
        
    target = data.get('referrerWallet')
    for ref in global_referrals:
        if ref.get('referrerWallet') == target:
            ref['paid'] = True
            
    save_json(REF_FILE, global_referrals)
    return jsonify({"status": "paid"})

@app.route('/referral/list', methods=['GET'])
def list_referrals():
    return jsonify(global_referrals)

@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
        data['server_time'] = datetime.now().isoformat()
        if 'paid' not in data: data['paid'] = False
        global_referrals.append(data)
        save_json(REF_FILE, global_referrals)
        return jsonify({"status": "tracked"})
    except: return jsonify({"error": "Failed"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
