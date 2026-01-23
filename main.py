from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging
import hashlib

# --- GESTION DES IMPORTS À RISQUE (Crash-Proof) ---
try:
    from solana.rpc.api import Client
    try:
        from solana.publickey import PublicKey
    except ImportError:
        from solders.pubkey import Pubkey as PublicKey
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    print("⚠️ WARNING: Solana/Solders libs missing. RPC features disabled.")

try:
    import torch
    import torch.nn as nn
    import numpy as np
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️ WARNING: Torch/Numpy missing. AI features disabled.")

app = Flask(__name__)
# Autorise CORS pour tout (important pour le dev/prod)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)

# --- SÉCURITÉ ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
# Utilisation de SHA256 pour un token stable (hash() change à chaque restart en Python)
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# --- CONFIGURATION FICHIERS ---
# Sur Render, utilise /var/data si tu as un disque persistant, sinon /tmp (effacé au redémarrage)
BASE_PATH = "/var/data" if os.path.exists("/var/data") else os.getcwd()

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")
MODEL_FILE = os.path.join(BASE_PATH, "rug_model.pth")

def load_json(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving JSON: {e}")

# Chargement en mémoire
global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- CONFIG RPC ---
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
client = Client(SOLANA_RPC) if SOLANA_AVAILABLE else None

# --- AI MODEL (SAFE MODE) ---
model = None
if AI_AVAILABLE:
    class RugPullClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc1 = nn.Linear(5, 64)
            self.fc2 = nn.Linear(64, 1)
            self.sigmoid = nn.Sigmoid()
        def forward(self, x):
            return self.sigmoid(self.fc2(torch.relu(self.fc1(x))))
    
    if os.path.exists(MODEL_FILE):
        try:
            model = RugPullClassifier()
            model.load_state_dict(torch.load(MODEL_FILE, map_location=torch.device('cpu')))
            model.eval()
        except: model = None

# --- ROUTES GÉNÉRALES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE", 
        "reports": len(global_reports),
        "referrals_tracked": len(global_referrals),
        "solana_active": SOLANA_AVAILABLE,
        "ai_active": model is not None
    })

# PING pour réveiller le serveur (utilisé par le frontend)
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "pong"})

# --- ROUTES REPORTS (SCAMS) ---

@app.route('/report/list', methods=['GET'])
def list_reports():
    return jsonify(global_reports)

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        data['submitted_at'] = datetime.now().isoformat()
        
        # On ajoute au début de la liste
        global_reports.insert(0, data)
        save_json(DB_FILE, global_reports)
        return jsonify({"status": "success"})
    except: return jsonify({"error": "failed"}), 500

@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    action = data.get('action')
    r_id = data.get('id')
    global global_reports
    
    if action == 'delete':
        global_reports = [r for r in global_reports if r.get('id') != r_id]
    elif action == 'approve':
        for r in global_reports:
            if r.get('id') == r_id: r['status'] = 'approved'
            
    save_json(DB_FILE, global_reports)
    return jsonify({"status": "updated"})

# --- ROUTES REFERRAL (MANQUANTES DANS TON CODE INITIAL) ---

@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
        # On évite les doublons simples (même visiteur, même référant dans la même heure)
        # Ceci est une implémentation basique
        entry = {
            "id": int(time.time() * 1000),
            "visitorWallet": data.get('visitorWallet'),
            "referrerWallet": data.get('referrerWallet'),
            "action": data.get('action'),
            "server_time": datetime.now().isoformat(),
            "paid": False
        }
        global_referrals.append(entry)
        save_json(REF_FILE, global_referrals)
        return jsonify({"status": "tracked"})
    except Exception as e:
        print(e)
        return jsonify({"error": "failed"}), 500

@app.route('/referral/list', methods=['GET'])
def list_referrals():
    # Optionnel : Filtrer pour n'afficher que les non payés ou les récents
    return jsonify(global_referrals)

@app.route('/referral/pay', methods=['POST'])
def pay_referral():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    target_wallet = data.get('referrerWallet')
    
    # Marquer toutes les entrées de ce wallet comme "paid"
    count = 0
    for ref in global_referrals:
        if ref.get('referrerWallet') == target_wallet and not ref.get('paid'):
            ref['paid'] = True
            count += 1
            
    save_json(REF_FILE, global_referrals)
    return jsonify({"status": "paid", "count": count})

# --- ADMIN LOGIN ---

@app.route('/admin/login', methods=['POST'])
def login():
    # Comparaison sécurisée
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

# --- SCANNER ---

@app.route('/scan', methods=['POST'])
def scan():
    try:
        addr = request.json.get('address')
        if not addr: return jsonify({"score": 0, "risk": "ERROR"}), 400

        # 1. Check DB interne
        for r in global_reports:
            if r.get('target') == addr and r.get('status') == 'approved':
                return jsonify({"score": 0, "risk": "CRITICAL", "summary": "BLACKLISTED by Community"})

        # 2. Check RugCheck API
        # On met un User-Agent pour ne pas se faire bloquer
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GoldGuard/1.0)"}
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{addr}/report/summary", headers=headers, timeout=5)
        
        score = 0
        summary = "Scan Complete"
        risk = "UNKNOWN"
        
        if res.status_code == 200:
            data = res.json()
            # RugCheck donne un score de risque (0 = sûr, 10000+ = dangereux)
            # On convertit en score de confiance sur 100
            raw_score = data.get('score', 0)
            score = max(0, min(100, 100 - int(raw_score / 100)))
            
            if data.get('risks'): 
                summary = data['risks'][0].get('name')
            
            risk = "SAFE" if score > 80 else "WARNING" if score > 40 else "CRITICAL"
        else:
            # Fallback si RugCheck ne connait pas le token
            risk = "WARNING"
            summary = "New Token / No Data"
            score = 50

        # 3. Phishing Check (Simple)
        # On vérifie si le nom contient des mots clés suspects
        if res.status_code == 200:
            token_meta = res.json().get('tokenMeta', {})
            name = token_meta.get('name', '').lower()
            symbol = token_meta.get('symbol', '').lower()
            
            suspicious = ['claim', 'reward', 'stakin', 'gift', 'free', 'airdrop']
            if any(x in name for x in suspicious) or any(x in symbol for x in suspicious):
                score = min(score, 10)
                summary = "Suspicious Name Detected"
                risk = "CRITICAL"

        return jsonify({"score": score, "risk": risk, "summary": summary})
    except Exception as e:
        print(f"Scan Error: {e}")
        return jsonify({"score": 0, "risk": "ERROR", "summary": "Scan Failed"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    # Threaded=True permet de gérer plusieurs requêtes en même temps
    app.run(host='0.0.0.0', port=port, threaded=True)
