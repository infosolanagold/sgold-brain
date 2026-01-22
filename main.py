from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging

# --- GESTION DES IMPORTS À RISQUE (Crash-Proof) ---
# On tente d'importer les librairies lourdes. Si ça échoue, le serveur démarre quand même.
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
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)

# --- SÉCURITÉ ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
ADMIN_TOKEN = f"SECURE_SESSION_{hash(ADMIN_PASSWORD)}"

# --- CONFIGURATION FICHIERS ---
# Utilise /tmp si /var/data n'existe pas (évite les erreurs de permission)
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
    except: pass

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

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE", 
        "reports": len(global_reports),
        "solana_active": SOLANA_AVAILABLE,
        "ai_active": model is not None
    })

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

@app.route('/admin/login', methods=['POST'])
def login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/scan', methods=['POST'])
def scan():
    # SCANNER V4 (Simplifié pour garantir le fonctionnement)
    try:
        addr = request.json.get('address')
        if not addr: return jsonify({"score": 0, "risk": "ERROR"}), 400

        # 1. Check DB
        for r in global_reports:
            if r.get('target') == addr and r.get('status') == 'approved':
                return jsonify({"score": 0, "risk": "CRITICAL", "summary": "BLACKLISTED by Community"})

        # 2. Check RugCheck
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{addr}/report/summary", headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        score = 0
        summary = "Scan Complete"
        
        if res.status_code == 200:
            data = res.json()
            score = max(0, min(100, 100 - int(data.get('score', 0)/100)))
            if data.get('risks'): summary = data['risks'][0].get('name')
        
        # 3. Phishing Check
        meta = res.json().get('tokenMeta', {}) if res.status_code == 200 else {}
        name = meta.get('name', '').lower()
        if any(x in name for x in ['claim', 'reward', 'stakin', 'gift']):
            score = min(score, 40)
            summary = "Suspicious Name Detected"

        risk = "SAFE" if score > 80 else "WARNING" if score > 40 else "CRITICAL"
        
        return jsonify({"score": score, "risk": risk, "summary": summary})
    except Exception as e:
        print(e)
        return jsonify({"score": 0, "risk": "ERROR"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
