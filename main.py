from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging
import hashlib

# --- SETUP LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION FICHIERS (SYSTEME ROBUSTE) ---
# On cherche le disque persistant
BASE_PATH = os.getcwd() # Par défaut : dossier actuel
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
    logging.info(f"✅ Disque persistant trouvé : {BASE_PATH}")
else:
    logging.warning("⚠️ Aucun disque persistant trouvé. Utilisation du dossier temporaire.")

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")
MODEL_FILE = os.path.join(BASE_PATH, "rug_model.pth")
MEAN_FILE = os.path.join(BASE_PATH, "mean.npy")
STD_FILE = os.path.join(BASE_PATH, "std.npy")

# --- SÉCURITÉ ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
# Token stable basé sur le mot de passe
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# --- IMPORTATION CONDITIONNELLE (ANTI-CRASH) ---
try:
    from solana.rpc.api import Client
    SOLANA_RPC = "https://api.mainnet-beta.solana.com"
    client = Client(SOLANA_RPC)
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    logging.warning("Solana/Solders manquant. Mode hors ligne.")

try:
    import torch
    import torch.nn as nn
    import numpy as np
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    logging.warning("PyTorch manquant. Mode AI désactivé.")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- FONCTIONS UTILITAIRES ---
def load_json(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: logging.error(f"Error saving {filepath}: {e}")

# Chargement en mémoire au démarrage
global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- AI MODEL DEFINITION ---
model = None
mean = None
std = None

if AI_AVAILABLE:
    class RugPullClassifier(nn.Module):
        def __init__(self, input_size=5):
            super(RugPullClassifier, self).__init__()
            self.fc1 = nn.Linear(input_size, 64)
            self.fc2 = nn.Linear(64, 32)
            self.fc3 = nn.Linear(32, 1)
            self.sigmoid = nn.Sigmoid()
        def forward(self, x):
            x = torch.relu(self.fc1(x))
            x = torch.relu(self.fc2(x))
            x = self.sigmoid(self.fc3(x))
            return x

    # Tentative de chargement du modèle
    if os.path.exists(MODEL_FILE) and os.path.exists(MEAN_FILE):
        try:
            model = RugPullClassifier()
            model.load_state_dict(torch.load(MODEL_FILE, map_location=torch.device('cpu')))
            model.eval()
            mean = np.load(MEAN_FILE)
            std = np.load(STD_FILE)
            logging.info("🧠 Grok AI Model chargé avec succès !")
        except Exception as e:
            logging.error(f"Erreur chargement modèle: {e}")
            model = None
    else:
        logging.info("ℹ️ Pas de fichiers modèle trouvés. Utilisation du mode heuristique.")

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE", 
        "reports": len(global_reports),
        "ai_active": model is not None,
        "disk_path": BASE_PATH
    })

# --- GESTION DES RAPPORTS ---

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
        
        # Ajout en haut de la liste
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

# --- GESTION DES REFERRALS ---

@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
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
    except: return jsonify({"error": "failed"}), 500

@app.route('/referral/list', methods=['GET'])
def list_referrals():
    return jsonify(global_referrals)

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

# --- ADMIN LOGIN ---

@app.route('/admin/login', methods=['POST'])
def login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

# --- SCANNER CORE ---

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0}), 400

        # 1. CHECK DATABASE
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0,
                    "risk": "CRITICAL",
                    "summary": "🚨 BLACKLISTED: Reported by Community.",
                    "reasons": ["Blacklisté par la communauté"]
                })

        # 2. RUGCHECK API (Base fiable)
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=4)
            if res.status_code == 200:
                rc_data = res.json()
                danger_score = rc_data.get('score', 0)
                safety_score = max(0, min(100, 100 - int(danger_score / 100)))
                token_meta = rc_data.get('tokenMeta', {})
                risks = rc_data.get('risks', [])
            else:
                safety_score = 50
                token_meta = {}
                risks = []
        except:
            safety_score = 50
            token_meta = {}
            risks = []

        summary = "Clean Analysis."
        reasons = []
        if risks:
            summary = f"ALERT: {risks[0].get('name')}."
            reasons.append(f"Risque détecté: {risks[0].get('name')}")

        # 3. HEURISTIQUE (Noms suspects)
        token_name = token_meta.get('name', '').lower()
        suspicious_keywords = ['claim', 'reward', 'airdrop', 'stakin', 'migrat', 'gift', 'ledger', 'wallet']
        if any(word in token_name for word in suspicious_keywords):
            safety_score = min(safety_score, 20)
            summary = f"SUSPICIOUS NAME ('{token_name}'). Possible Drainer."
            reasons.append("Nom suspect détecté (Phishing probable)")

        # 4. ON-CHAIN DATA (Si disponible)
        tx_count = 0
        if SOLANA_AVAILABLE:
            try:
                # On limite à 10 pour la rapidité
                signatures = client.get_signatures_for_address(PublicKey(token_address), limit=10)
                tx_history = signatures.value if signatures.value else []
                tx_count = len(tx_history)
                if tx_count < 5:
                    safety_score -= 30
                    reasons.append("Très peu de transactions récentes")
            except Exception as e:
                logging.warning(f"RPC Error: {e}")

        # 5. GROK AI PREDICTION (Si modèle chargé)
        if model and mean is not None and std is not None:
            try:
                # Simulation des features (car extraire la liquidité temps réel est lent)
                number_adds = tx_count * 0.5 
                number_removes = tx_count * 0.1
                ratio = number_adds / (number_removes + 1e-6)
                lifespan = 5.0 # Valeur moyenne
                holders = 100.0 # Valeur moyenne
                
                features_np = np.array([[number_adds, number_removes, ratio, lifespan, holders]])
                features_np = (features_np - mean) / std # Normalisation
                features_tensor = torch.tensor(features_np, dtype=torch.float32)
                
                with torch.no_grad():
                    risk_prob = model(features_tensor).item() * 100
                
                safety_score = int((safety_score + (100 - risk_prob)) / 2)
                reasons.append(f"Grok AI Risk Assessment: {risk_prob:.1f}%")
            except Exception as e:
                logging.error(f"AI Error: {e}")

        # Label final
        if safety_score < 40:
            risk_label = "CRITICAL"
            prediction = "Haut risque – avoid! 🔥"
        elif safety_score < 75:
            risk_label = "WARNING"
            prediction = "Risque modéré ⚠️"
        else:
            risk_label = "SAFE"
            prediction = "Semble sûr 🚀"

        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary,
            "prediction": prediction,
            "reasons": reasons
        })
        
    except Exception as e:
        logging.error(f"Global Scan Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
