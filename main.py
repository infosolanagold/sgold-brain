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

# --- SCANNER INTELLIGENT (ALGORITHME V4) ---
@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0}), 400

        # 1. CHECK DATABASE (BLACKLIST COMMUNAUTAIRE)
        # Si un utilisateur a rapporté ce token et que l'admin l'a approuvé, c'est SCAM direct.
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0, 
                    "risk": "CRITICAL", 
                    "summary": "🚨 BLACKLISTED: Reported by Solana Gold Guard Community as a SCAM."
                })

        # 2. APPEL API EXTERNE (RUGCHECK)
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=5)

        if res.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new or not found."})

        rc_data = res.json()
        
        # Calcul du score de base
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 3. ANALYSE HEURISTIQUE (DETECTION PHISHING)
        token_meta = rc_data.get('tokenMeta', {})
        token_name = token_meta.get('name', '').lower()
        
        # Mots-clés souvent utilisés par les drainers
        suspicious_keywords = ['claim', 'reward', 'airdrop', 'stakin', 'migrat', 'support', 'v2', 'gift', 'ledger', 'wallet']
        
        is_suspicious_name = any(word in token_name for word in suspicious_keywords)
        
        summary = "Clean Analysis."
        risks = rc_data.get('risks', [])
        
        if risks:
            summary = f"ALERT: {risks[0].get('name')}."
        
        # Si le nom est suspect, on force un score bas même si la liquidité est ok
        if is_suspicious_name:
            safety_score = min(safety_score, 40) # On cap le score à 40 max
            summary = f"SUSPICIOUS NAME DETECTED ('{token_name}'). Possible Phishing/Drainer."

        # Label final
        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})
        
    except Exception as e:
        print(f"Scan Error: {e}")
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

# --- ROUTES SÉCURISÉES (ADMIN) ---

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    else:
        return jsonify({"success": False, "error": "Invalid Password"}), 401

@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
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
