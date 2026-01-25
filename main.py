from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging
import hashlib

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
# Autoriser toutes les origines pour éviter les erreurs CORS sur ton site
CORS(app, resources={r"/*": {"origins": "*"}})

# --- SÉCURITÉ ADMIN ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# --- DISQUE PERSISTANT (RENDER) ---
# Si le disque est monté sur Render, on l'utilise. Sinon, dossier local.
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
    logging.info(f"✅ MODE PRODUCTION : Disque persistant trouvé sur {BASE_PATH}")
else:
    BASE_PATH = os.getcwd()
    logging.warning("⚠️ MODE TEMPORAIRE : Aucun disque trouvé. Les données seront perdues au redémarrage.")

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")

# --- FONCTIONS DE BASE DE DONNÉES ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erreur lecture DB: {e}")
            return []
    return []

def save_data(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Erreur sauvegarde DB: {e}")

# Chargement au démarrage
global_reports = load_data()
global_referrals = []
if os.path.exists(REF_FILE):
    try:
        with open(REF_FILE, 'r') as f: global_referrals = json.load(f)
    except: pass

# --- ROUTES PRINCIPALES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE",
        "reports_count": len(global_reports),
        "storage_mode": "PERSISTENT" if BASE_PATH == "/var/data" else "TEMPORARY",
        "scan_engine": "ACTIVE"
    })

# --- GESTION DES RAPPORTS (DATABASE) ---

@app.route('/report/list', methods=['GET'])
def list_reports():
    return jsonify(global_reports)

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        new_report = {
            "id": int(time.time() * 1000),
            "target": data.get('target'),
            "desc": data.get('desc'),
            "contact": data.get('contact', ''),
            "img": data.get('img'),
            "status": 'pending', # En attente de validation admin
            "submitted_at": datetime.now().isoformat()
        }
        
        # On ajoute au début de la liste
        global_reports.insert(0, new_report)
        # SAUVEGARDE IMMÉDIATE SUR LE DISQUE
        save_data(global_reports)
        
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Submit error: {e}")
        return jsonify({"error": "failed"}), 500

@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    action = data.get('action')
    r_id = data.get('id')
    global global_reports
    
    modified = False
    if action == 'delete':
        global_reports = [r for r in global_reports if r.get('id') != r_id]
        modified = True
    elif action == 'approve':
        for r in global_reports:
            if r.get('id') == r_id: 
                r['status'] = 'approved'
                modified = True
    
    if modified:
        save_data(global_reports) # Sauvegarde après action admin
        
    return jsonify({"status": "updated"})

# --- MOTEUR DE SCAN (SCANNER LOGIC) ---

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address provided"}), 400

        # ÉTAPE 1 : Vérifier dans NOTRE base de données locale
        # Si c'est déjà signalé comme scam chez nous, on alerte direct.
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0,
                    "risk": "CRITICAL",
                    "summary": "🚨 BLACKLISTED: Known Scam in Database.",
                    "reasons": ["Signalé par la communauté Gold Guard"]
                })

        # ÉTAPE 2 : Interroger l'API RugCheck (La référence sur Solana)
        # C'est ce qui rend le scanner intelligent et fonctionnel
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            api_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
            res = requests.get(api_url, headers=headers, timeout=5)
            
            if res.status_code == 200:
                rc_data = res.json()
                danger_score = rc_data.get('score', 0) # RugCheck donne un score de danger (0 = safe, 100 = scam)
                
                # On inverse pour avoir un score de sécurité (100 = safe)
                safety_score = max(0, 100 - danger_score)
                
                risks = rc_data.get('risks', [])
                risk_list = [r.get('name') for r in risks]
                
                # Logique de Label
                if safety_score < 40:
                    risk_label = "CRITICAL"
                    summary = "High Risk Detected. Do not buy."
                elif safety_score < 75:
                    risk_label = "WARNING"
                    summary = "Medium Risk. DYOR carefully."
                else:
                    risk_label = "SAFE"
                    summary = "Token looks clean."

                return jsonify({
                    "score": safety_score,
                    "risk": risk_label,
                    "summary": summary,
                    "reasons": risk_list[:3] # Top 3 raisons
                })
            else:
                # Si le token est trop nouveau ou erreur API
                return jsonify({
                    "score": 50,
                    "risk": "UNKNOWN",
                    "summary": "New token or analysis pending.",
                    "reasons": ["Manual check required"]
                })

        except Exception as e:
            logging.error(f"External API Error: {e}")
            return jsonify({
                "score": 50, 
                "risk": "UNKNOWN", 
                "summary": "Connection to scan engine failed."
            })

    except Exception as e:
        logging.error(f"Scan Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0}), 500

# --- REFERRALS & ADMIN LOGIN ---

@app.route('/admin/login', methods=['POST'])
def login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
        entry = {
            "id": int(time.time() * 1000),
            "visitorWallet": data.get('visitorWallet'),
            "referrerWallet": data.get('referrerWallet'),
            "server_time": datetime.now().isoformat(),
            "paid": False
        }
        global_referrals.append(entry)
        
        # On sauvegarde les referrals sur le disque aussi !
        try:
            with open(REF_FILE, 'w') as f: json.dump(global_referrals, f, indent=4)
        except: pass
        
        return jsonify({"status": "tracked"})
    except: return jsonify({"error": "failed"}), 500

@app.route('/referral/list', methods=['GET'])
def list_ref():
    return jsonify(global_referrals)

@app.route('/referral/pay', methods=['POST'])
def pay_ref():
    data = request.json
    if data.get('token') != ADMIN_TOKEN: return jsonify({"error": "Unauthorized"}), 403
    
    target = data.get('referrerWallet')
    for ref in global_referrals:
        if ref.get('referrerWallet') == target: ref['paid'] = True
        
    try:
        with open(REF_FILE, 'w') as f: json.dump(global_referrals, f, indent=4)
    except: pass
    return jsonify({"status": "paid"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
